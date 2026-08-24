"""Tests for PreFlightSync: buffer overwrite and hash verification."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from alchemist.protocol.models.client_to_daemon import BufferSnapshot
from alchemist.workspace.manager import ShadowWorkspace
from alchemist.workspace.sync import PreFlightSync


class TestPreFlightSync:
    async def test_buffer_overwrites_shadow_file(self, shadow_workspace: ShadowWorkspace):
        buf = BufferSnapshot(
            path="main.py",
            content="print('modified')\n",
            sha256=hashlib.sha256(b"print('modified')\n").hexdigest(),
            modified=True,
        )

        hashes = await PreFlightSync.sync_buffers(shadow_workspace.shadow_root, [buf])
        assert (shadow_workspace.shadow_root / "main.py").read_text() == "print('modified')\n"
        assert "main.py" in hashes
        assert hashes["main.py"] == hashlib.sha256(b"print('modified')\n").hexdigest()

    async def test_creates_new_file_from_buffer(self, shadow_workspace: ShadowWorkspace):
        buf = BufferSnapshot(
            path="new_file.py",
            content="# new file\n",
            sha256=hashlib.sha256(b"# new file\n").hexdigest(),
            modified=True,
        )

        await PreFlightSync.sync_buffers(shadow_workspace.shadow_root, [buf])
        assert (shadow_workspace.shadow_root / "new_file.py").read_text() == "# new file\n"

    async def test_creates_nested_directory_from_buffer(self, shadow_workspace: ShadowWorkspace):
        buf = BufferSnapshot(
            path="nested/dir/deep.py",
            content="# deep file\n",
            sha256=hashlib.sha256(b"# deep file\n").hexdigest(),
            modified=True,
        )

        await PreFlightSync.sync_buffers(shadow_workspace.shadow_root, [buf])
        assert (shadow_workspace.shadow_root / "nested" / "dir" / "deep.py").read_text() == "# deep file\n"

    async def test_base_hashes_match_content(self, shadow_workspace: ShadowWorkspace):
        content = "def foo(): pass\n"
        buf = BufferSnapshot(
            path="foo.py",
            content=content,
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            modified=True,
        )

        hashes = await PreFlightSync.sync_buffers(shadow_workspace.shadow_root, [buf])
        assert hashes["foo.py"] == hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def test_commit_sync_creates_git_commit(self, shadow_workspace: ShadowWorkspace):
        buf = BufferSnapshot(
            path="main.py",
            content="changed\n",
            sha256=hashlib.sha256(b"changed\n").hexdigest(),
            modified=True,
        )

        await PreFlightSync.sync_buffers(shadow_workspace.shadow_root, [buf])
        await PreFlightSync.commit_sync(shadow_workspace.shadow_root)

        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=shadow_workspace.shadow_root,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "pre-flight sync" in result.stdout

    def test_compute_hash_deterministic(self):
        content = "hello world"
        h1 = PreFlightSync.compute_hash(content)
        h2 = PreFlightSync.compute_hash(content)
        assert h1 == h2
        assert len(h1) == 64
