"""Tests for ShadowManager: workspace creation, validation, and cleanup."""

import subprocess
from pathlib import Path

import pytest

from alchemist.errors import ShadowSyncFailedError, ShadowWorkspaceNotInitializedError
from alchemist.workspace.manager import ShadowManager
from conftest import init_git_repo


class TestShadowManagerInitialization:
    async def test_creates_shadow_directory(self, project_dir: Path):
        mgr = ShadowManager()
        ws = await mgr.initialize("proj-1", str(project_dir))
        assert ws.shadow_root.exists()
        assert ws.shadow_root == project_dir / ".git" / "alchemist" / "shadow"

    async def test_copies_project_files(self, project_dir: Path):
        mgr = ShadowManager()
        ws = await mgr.initialize("proj-1", str(project_dir))
        assert (ws.shadow_root / "main.py").read_text() == "print('hello')\n"
        assert (ws.shadow_root / "utils.py").exists()
        assert (ws.shadow_root / "src" / "lib.py").exists()

    async def test_initializes_git_sandbox(self, project_dir: Path):
        mgr = ShadowManager()
        ws = await mgr.initialize("proj-1", str(project_dir))
        assert (ws.shadow_root / ".git").is_dir()
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=ws.shadow_root,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "shadow workspace baseline" in result.stdout

    async def test_shadow_git_isolated_from_parent(self, project_dir: Path):
        mgr = ShadowManager()
        ws = await mgr.initialize("proj-1", str(project_dir))
        parent_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        shadow_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=ws.shadow_root,
            capture_output=True,
            text=True,
            check=True,
        )
        assert parent_log.stdout != shadow_log.stdout

    async def test_fails_for_non_git_project(self, tmp_path: Path):
        non_git = tmp_path / "no_git"
        non_git.mkdir()
        (non_git / "file.txt").write_text("hello")
        mgr = ShadowManager()
        with pytest.raises(ShadowSyncFailedError, match="not a Git repository"):
            await mgr.initialize("proj-1", str(non_git))

    async def test_reinitialize_replaces_existing(self, project_dir: Path):
        mgr = ShadowManager()
        ws1 = await mgr.initialize("proj-1", str(project_dir))
        marker = ws1.shadow_root / "MARKER"
        marker.write_text("old")
        ws2 = await mgr.initialize("proj-1", str(project_dir))
        assert not (ws2.shadow_root / "MARKER").exists()


class TestShadowManagerIgnoreRules:
    async def test_respects_gitignore(self, tmp_path: Path):
        project = tmp_path / "proj"
        init_git_repo(
            project,
            {
                "main.py": "code",
                ".gitignore": "*.log\nbuild/\n",
            },
        )
        (project / "debug.log").write_text("log data")
        (project / "build").mkdir()
        (project / "build" / "out.js").write_text("built")

        mgr = ShadowManager()
        ws = await mgr.initialize("proj-1", str(project))
        assert (ws.shadow_root / "main.py").exists()
        assert not (ws.shadow_root / "debug.log").exists()
        assert not (ws.shadow_root / "build").exists()

    async def test_respects_aiderignore(self, tmp_path: Path):
        project = tmp_path / "proj"
        init_git_repo(
            project,
            {
                "main.py": "code",
                "docs/guide.md": "guide content",
                ".aiderignore": "docs/*\n",
            },
        )
        mgr = ShadowManager()
        ws = await mgr.initialize("proj-1", str(project))
        assert (ws.shadow_root / "main.py").exists()
        assert not (ws.shadow_root / "docs" / "guide.md").exists()

    async def test_skips_binary_files(self, tmp_path: Path):
        project = tmp_path / "proj"
        init_git_repo(project, {"main.py": "code"})
        binary = project / "image.png"
        binary.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        subprocess.run(["git", "add", "image.png"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add binary"], cwd=project, check=True, capture_output=True)

        mgr = ShadowManager()
        ws = await mgr.initialize("proj-1", str(project))
        assert (ws.shadow_root / "main.py").exists()
        assert not (ws.shadow_root / "image.png").exists()


class TestShadowManagerCleanup:
    async def test_cleanup_deletes_workspace(self, project_dir: Path):
        mgr = ShadowManager()
        ws = await mgr.initialize("proj-1", str(project_dir))
        assert ws.shadow_root.exists()
        await mgr.cleanup("proj-1")
        assert not ws.shadow_root.exists()

    async def test_cleanup_all_deletes_all(self, project_dir: Path):
        mgr = ShadowManager()
        ws = await mgr.initialize("proj-1", str(project_dir))
        await mgr.cleanup_all()
        assert not ws.shadow_root.exists()
        assert not mgr.has_workspace("proj-1")

    def test_get_workspace_raises_if_not_initialized(self):
        mgr = ShadowManager()
        with pytest.raises(ShadowWorkspaceNotInitializedError):
            mgr.get_workspace("nonexistent")
