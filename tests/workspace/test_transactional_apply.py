"""Tests for full orchestrator pipeline and transactional behavior."""

import asyncio
import hashlib
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from alchemist.daemon.active_job import ActiveJobTracker
from alchemist.daemon.broadcaster import Broadcaster
from alchemist.engine.interface import StubAssistantEngine
from alchemist.errors import AgentBusyError
from alchemist.workspace.manager import ShadowManager
from alchemist.workspace.orchestrator import PromptOrchestrator


class TestPromptOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        return PromptOrchestrator(
            shadow_manager=ShadowManager(),
            engine=StubAssistantEngine(),
            job_tracker=ActiveJobTracker(),
            broadcaster=MagicMock(spec=Broadcaster),
        )

    async def test_submit_prompt_returns_accepted(self, orchestrator: PromptOrchestrator, project_dir: Path):
        params = {
            "client_id": "00000000-0000-0000-0000-000000000001",
            "session_id": "00000000-0000-0000-0000-000000000002",
            "project_id": "00000000-0000-0000-0000-000000000003",
            "project_path": str(project_dir),
            "mode": "code",
            "prompt": "Refactor main.py",
            "active_files": ["main.py"],
            "buffers": [{
                "path": "main.py",
                "content": "print('hello')\n",
                "sha256": hashlib.sha256(b"print('hello')\n").hexdigest(),
                "modified": False,
            }],
        }
        result = await orchestrator.handle_submit_prompt(params)
        assert result["status"] == "accepted"
        assert result["job_id"] == "00000000-0000-0000-0000-000000000002"

        # Wait a moment for background task to run
        await asyncio.sleep(0.1)

    async def test_concurrent_submit_raises_busy(self, orchestrator: PromptOrchestrator, project_dir: Path):
        params = {
            "client_id": "00000000-0000-0000-0000-000000000001",
            "session_id": "00000000-0000-0000-0000-000000000002",
            "project_id": "00000000-0000-0000-0000-000000000003",
            "project_path": str(project_dir),
            "mode": "code",
            "prompt": "First job",
            "active_files": [],
            "buffers": [],
        }
        await orchestrator.handle_submit_prompt(params)

        params2 = {
            "client_id": "00000000-0000-0000-0000-000000000001",
            "session_id": "00000000-0000-0000-0000-000000000099",
            "project_id": "00000000-0000-0000-0000-000000000003",
            "project_path": str(project_dir),
            "mode": "code",
            "prompt": "Second job",
            "active_files": [],
            "buffers": [],
        }
        with pytest.raises(AgentBusyError):
            await orchestrator.handle_submit_prompt(params2)

    async def test_accept_diff_returns_applied(self, orchestrator: PromptOrchestrator, project_dir: Path):
        await orchestrator.shadow_manager.initialize(
            "00000000-0000-0000-0000-000000000003", str(project_dir)
        )
        params = {
            "client_id": "00000000-0000-0000-0000-000000000001",
            "session_id": "00000000-0000-0000-0000-000000000002",
            "project_id": "00000000-0000-0000-0000-000000000003",
        }
        orchestrator.job_tracker.start_job(
            params["session_id"], params["project_id"], "test"
        )
        result = await orchestrator.handle_accept_diff(params)
        assert result["status"] == "applied"
        assert orchestrator.job_tracker.get_current_job() is None

    async def test_reject_diff_returns_reverted(self, orchestrator: PromptOrchestrator, project_dir: Path):
        ws = await orchestrator.shadow_manager.initialize(
            "00000000-0000-0000-0000-000000000003", str(project_dir)
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "pre-flight"],
            cwd=ws.shadow_root, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "aider"],
            cwd=ws.shadow_root, check=True, capture_output=True,
        )

        params = {
            "client_id": "00000000-0000-0000-0000-000000000001",
            "session_id": "00000000-0000-0000-0000-000000000002",
            "project_id": "00000000-0000-0000-0000-000000000003",
        }
        orchestrator.job_tracker.start_job(
            params["session_id"], params["project_id"], "test"
        )
        result = await orchestrator.handle_reject_diff(params)
        assert result["status"] == "reverted"
        assert orchestrator.job_tracker.get_current_job() is None
