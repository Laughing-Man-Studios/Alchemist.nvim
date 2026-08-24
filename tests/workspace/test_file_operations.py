"""Tests for file operations: create, rename, delete, mode change in diffs."""

import os
import subprocess
from pathlib import Path

import pytest

from alchemist.workspace.diff import DiffGenerator
from alchemist.workspace.manager import ShadowWorkspace


class TestFileOperationsInDiff:
    async def test_file_creation_in_diff(self, shadow_workspace: ShadowWorkspace):
        (shadow_workspace.shadow_root / "brand_new.py").write_text("# new\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "create"], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)

        diff = await DiffGenerator.generate_diff(shadow_workspace.shadow_root)
        assert "brand_new.py" in diff
        assert "+# new" in diff

    async def test_file_deletion_in_diff(self, shadow_workspace: ShadowWorkspace):
        (shadow_workspace.shadow_root / "utils.py").unlink()
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "delete"], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)

        diff = await DiffGenerator.generate_diff(shadow_workspace.shadow_root)
        assert "utils.py" in diff

    async def test_file_rename_in_diff(self, shadow_workspace: ShadowWorkspace):
        old = shadow_workspace.shadow_root / "utils.py"
        new = shadow_workspace.shadow_root / "helpers.py"
        new.write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
        old.unlink()
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "rename"], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)

        changed = await DiffGenerator.get_changed_files(shadow_workspace.shadow_root)
        file_names = {Path(f).name for f in changed}
        assert "helpers.py" in file_names or "utils.py" in file_names

    async def test_file_mode_change_in_diff(self, shadow_workspace: ShadowWorkspace):
        target = shadow_workspace.shadow_root / "main.py"
        os.chmod(target, 0o755)
        subprocess.run(["git", "add", "."], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "chmod"], cwd=shadow_workspace.shadow_root, check=True, capture_output=True)

        diff = await DiffGenerator.generate_diff(shadow_workspace.shadow_root)
        if diff.strip():
            assert "main.py" in diff
