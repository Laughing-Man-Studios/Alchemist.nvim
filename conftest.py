"""Shared pytest fixtures for Alchemist tests."""

import subprocess
from pathlib import Path

import pytest

from alchemist.workspace.manager import ShadowManager, ShadowWorkspace


def init_git_repo(path: Path, files: dict[str, str] | None = None) -> None:
    """Helper: create a git repo with optional initial files and commits."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@alchemist.local"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Alchemist Test"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    if files:
        for name, content in files.items():
            f_path = path / name
            f_path.parent.mkdir(parents=True, exist_ok=True)
            f_path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit", "--allow-empty"],
        cwd=path,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal git project with test files."""
    project = tmp_path / "project"
    init_git_repo(
        project,
        {
            "main.py": "print('hello')\n",
            "utils.py": "def add(a, b): return a + b\n",
            "src/lib.py": "class Foo: pass\n",
        },
    )
    return project


@pytest.fixture
async def shadow_workspace(project_dir: Path) -> ShadowWorkspace:
    """Create and return an initialized shadow workspace."""
    mgr = ShadowManager()
    ws = await mgr.initialize("test-project", str(project_dir))
    return ws
