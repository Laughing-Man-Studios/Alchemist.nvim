"""Tests for newly wired orchestrator RPC handlers."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from alchemist.daemon.active_job import ActiveJobTracker
from alchemist.daemon.broadcaster import Broadcaster
from alchemist.engine.interface import StubAssistantEngine
from alchemist.workspace.manager import ShadowManager
from alchemist.workspace.orchestrator import PromptOrchestrator


PARAMS_BASE = {
    "client_id": "00000000-0000-0000-0000-000000000001",
    "session_id": "00000000-0000-0000-0000-000000000002",
    "project_id": "00000000-0000-0000-0000-000000000003",
}


class TestAgentLifecycleHandlers:
    @pytest.fixture
    def orchestrator(self):
        return PromptOrchestrator(
            shadow_manager=ShadowManager(),
            engine=StubAssistantEngine(),
            job_tracker=ActiveJobTracker(),
            broadcaster=MagicMock(spec=Broadcaster),
        )

    async def test_cancel_no_active_task(self, orchestrator):
        result = await orchestrator.handle_cancel(PARAMS_BASE)
        assert result["cancelled"] is False
        assert result["state"] == "idle"

    async def test_cancel_active_task(self, orchestrator, project_dir: Path):
        params = {
            **PARAMS_BASE,
            "project_path": str(project_dir),
            "mode": "code",
            "prompt": "test",
            "active_files": [],
            "buffers": [],
        }
        await orchestrator.handle_submit_prompt(params)
        result = await orchestrator.handle_cancel(PARAMS_BASE)
        assert result["cancelled"] in (True, False)
        assert orchestrator.job_tracker.get_current_job() is None

    async def test_status_idle(self, orchestrator):
        result = await orchestrator.handle_status(PARAMS_BASE)
        assert result["status"] == "idle"
        assert result["active_job"] is None

    async def test_status_busy(self, orchestrator):
        orchestrator.job_tracker.start_job(
            session_id=PARAMS_BASE["session_id"],
            project_id=PARAMS_BASE["project_id"],
            task_description="Busy task",
        )
        result = await orchestrator.handle_status(PARAMS_BASE)
        assert result["status"] == "busy"
        assert result["active_job"] is not None
        assert result["active_job"]["session_id"] == PARAMS_BASE["session_id"]

    async def test_reset_clears_state(self, orchestrator):
        orchestrator.job_tracker.start_job(
            session_id=PARAMS_BASE["session_id"],
            project_id=PARAMS_BASE["project_id"],
            task_description="Test task",
        )
        result = await orchestrator.handle_reset(PARAMS_BASE)
        assert result == {}
        assert orchestrator.job_tracker.get_current_job() is None

    async def test_clear_returns_empty(self, orchestrator):
        result = await orchestrator.handle_clear(PARAMS_BASE)
        assert result == {}

    async def test_list_sessions(self, orchestrator):
        await orchestrator.handle_add_file({**PARAMS_BASE, "path": "main.py"})
        result = await orchestrator.handle_list_sessions({"client_id": PARAMS_BASE["client_id"]})
        assert "sessions" in result
        assert PARAMS_BASE["session_id"] in result["sessions"]


class TestFileContextHandlers:
    @pytest.fixture
    def orchestrator(self):
        return PromptOrchestrator(
            shadow_manager=ShadowManager(),
            engine=StubAssistantEngine(),
            job_tracker=ActiveJobTracker(),
            broadcaster=MagicMock(spec=Broadcaster),
        )

    async def test_add_file(self, orchestrator):
        result = await orchestrator.handle_add_file({**PARAMS_BASE, "path": "main.py"})
        assert result == {}

    async def test_add_then_list(self, orchestrator):
        await orchestrator.handle_add_file({**PARAMS_BASE, "path": "main.py"})
        await orchestrator.handle_add_file({**PARAMS_BASE, "path": "utils.py"})
        result = await orchestrator.handle_list_files(PARAMS_BASE)
        assert "main.py" in result["editable"]
        assert "utils.py" in result["editable"]
        assert result["read_only"] == []

    async def test_drop_file(self, orchestrator):
        await orchestrator.handle_add_file({**PARAMS_BASE, "path": "main.py"})
        await orchestrator.handle_drop_file({**PARAMS_BASE, "path": "main.py"})
        result = await orchestrator.handle_list_files(PARAMS_BASE)
        assert result["editable"] == []

    async def test_read_only_toggle(self, orchestrator):
        await orchestrator.handle_add_file({**PARAMS_BASE, "path": "main.py"})
        await orchestrator.handle_read_only({**PARAMS_BASE, "path": "main.py", "enabled": True})
        result = await orchestrator.handle_list_files(PARAMS_BASE)
        assert "main.py" in result["read_only"]
        assert "main.py" not in result["editable"]

        await orchestrator.handle_read_only({**PARAMS_BASE, "path": "main.py", "enabled": False})
        result = await orchestrator.handle_list_files(PARAMS_BASE)
        assert "main.py" in result["editable"]
        assert "main.py" not in result["read_only"]

    async def test_repo_map_no_workspace(self, orchestrator):
        result = await orchestrator.handle_repo_map(PARAMS_BASE)
        assert result["files"] == []
        assert result["map"] == ""

    async def test_repo_map_with_workspace(self, orchestrator, project_dir: Path):
        await orchestrator.shadow_manager.initialize(
            PARAMS_BASE["project_id"], str(project_dir)
        )
        result = await orchestrator.handle_repo_map(PARAMS_BASE)
        assert len(result["files"]) > 0
        assert "main.py" in result["files"]


class TestExecutionHandlers:
    @pytest.fixture
    def orchestrator(self):
        return PromptOrchestrator(
            shadow_manager=ShadowManager(),
            engine=StubAssistantEngine(),
            job_tracker=ActiveJobTracker(),
            broadcaster=MagicMock(spec=Broadcaster),
        )

    async def test_run_echo(self, orchestrator):
        result = await orchestrator.handle_run({**PARAMS_BASE, "command": "echo hello"})
        assert result["exit_code"] == 0

    async def test_run_non_zero(self, orchestrator):
        result = await orchestrator.handle_run({**PARAMS_BASE, "command": "exit 42"})
        assert result["exit_code"] == 42

    async def test_test_detection(self, orchestrator, project_dir: Path):
        await orchestrator.shadow_manager.initialize(
            PARAMS_BASE["project_id"], str(project_dir)
        )
        result = await orchestrator.handle_test(PARAMS_BASE)
        assert "exit_code" in result

    async def test_lint_detection(self, orchestrator, project_dir: Path):
        await orchestrator.shadow_manager.initialize(
            PARAMS_BASE["project_id"], str(project_dir)
        )
        result = await orchestrator.handle_lint(PARAMS_BASE)
        assert "exit_code" in result
