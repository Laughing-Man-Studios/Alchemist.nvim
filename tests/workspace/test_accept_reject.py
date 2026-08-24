"""Tests for AcceptanceFlow and RejectionFlow."""

import subprocess
from pathlib import Path

import pytest

from alchemist.workspace.lifecycle import AcceptanceFlow, RejectionFlow
from alchemist.workspace.manager import ShadowWorkspace


class TestAcceptanceFlow:
    async def test_accept_clears_pending_diff(self, shadow_workspace: ShadowWorkspace):
        shadow_workspace.pending_diff = "some diff"
        shadow_workspace.base_hashes = {"main.py": "abc123"}

        await AcceptanceFlow.accept(shadow_workspace)

        assert shadow_workspace.pending_diff is None
        assert shadow_workspace.base_hashes == {}

    async def test_accept_preserves_aider_changes(self, shadow_workspace: ShadowWorkspace):
        (shadow_workspace.shadow_root / "main.py").write_text("aider version\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aider"], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)

        await AcceptanceFlow.accept(shadow_workspace)

        assert (shadow_workspace.shadow_root / "main.py").read_text() == "aider version\n"


class TestRejectionFlow:
    async def test_reject_reverts_aider_changes(self, shadow_workspace: ShadowWorkspace):
        original = (shadow_workspace.shadow_root / "main.py").read_text()

        # Pre-flight sync commit
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "pre-flight"],
            cwd=shadow_workspace.shadow_root,
            check=True,
            capture_output=True,
        )

        # Simulate Aider edit
        (shadow_workspace.shadow_root / "main.py").write_text("aider version\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "aider"], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)

        await RejectionFlow.reject(shadow_workspace)

        assert (shadow_workspace.shadow_root / "main.py").read_text() == original

    async def test_reject_clears_pending_state(self, shadow_workspace: ShadowWorkspace):
        shadow_workspace.pending_diff = "diff text"
        shadow_workspace.base_hashes = {"file.py": "hash"}

        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "pre-flight"],
            cwd=shadow_workspace.shadow_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "aider"],
            cwd=shadow_workspace.shadow_root,
            check=True,
            capture_output=True,
        )

        await RejectionFlow.reject(shadow_workspace)

        assert shadow_workspace.pending_diff is None
        assert shadow_workspace.base_hashes == {}
