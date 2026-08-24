"""Tests for DiffGenerator: diff extraction after file mutations."""

import subprocess
from pathlib import Path

import pytest

from alchemist.workspace.diff import DiffGenerator
from alchemist.workspace.manager import ShadowWorkspace


class TestDiffGenerator:
    async def test_generates_diff_for_modified_file(self, shadow_workspace: ShadowWorkspace):
        (shadow_workspace.shadow_root / "main.py").write_text("print('modified by aider')\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "aider edit"],
            cwd=shadow_workspace.shadow_root,
            check=True,
            capture_output=True,
        )

        diff = await DiffGenerator.generate_diff(shadow_workspace.shadow_root)
        assert "main.py" in diff
        assert "+print('modified by aider')" in diff

    async def test_generates_diff_for_new_file(self, shadow_workspace: ShadowWorkspace):
        (shadow_workspace.shadow_root / "new_module.py").write_text("class New: pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "aider new file"],
            cwd=shadow_workspace.shadow_root,
            check=True,
            capture_output=True,
        )

        diff = await DiffGenerator.generate_diff(shadow_workspace.shadow_root)
        assert "new_module.py" in diff
        changed = await DiffGenerator.get_changed_files(shadow_workspace.shadow_root)
        assert "new_module.py" in changed

    async def test_generates_diff_for_deleted_file(self, shadow_workspace: ShadowWorkspace):
        (shadow_workspace.shadow_root / "utils.py").unlink()
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "aider delete"],
            cwd=shadow_workspace.shadow_root,
            check=True,
            capture_output=True,
        )

        diff = await DiffGenerator.generate_diff(shadow_workspace.shadow_root)
        assert "utils.py" in diff
        changed = await DiffGenerator.get_changed_files(shadow_workspace.shadow_root)
        assert "utils.py" in changed

    async def test_multi_file_diff(self, shadow_workspace: ShadowWorkspace):
        (shadow_workspace.shadow_root / "main.py").write_text("# updated main\n", encoding="utf-8")
        (shadow_workspace.shadow_root / "utils.py").write_text("# updated utils\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "aider multi-file"],
            cwd=shadow_workspace.shadow_root,
            check=True,
            capture_output=True,
        )

        changed = await DiffGenerator.get_changed_files(shadow_workspace.shadow_root)
        assert len(changed) == 2
        assert "main.py" in changed
        assert "utils.py" in changed

    async def test_has_changes_detects_modifications(self, shadow_workspace: ShadowWorkspace):
        # Pre-flight commit
        subprocess.run(["git", "commit", "--allow-empty", "-m", "pre-flight"], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        # Without changes relative to HEAD~1
        assert not await DiffGenerator.has_changes(shadow_workspace.shadow_root)

        (shadow_workspace.shadow_root / "main.py").write_text("changed\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "edit"], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)

        assert await DiffGenerator.has_changes(shadow_workspace.shadow_root)

    async def test_empty_diff_when_no_changes(self, shadow_workspace: ShadowWorkspace):
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "pre-flight"],
            cwd=shadow_workspace.shadow_root,
            check=True,
            capture_output=True,
        )
        diff = await DiffGenerator.generate_diff(shadow_workspace.shadow_root)
        assert diff.strip() == ""

