"""Diff generation from shadow workspace Git history."""

import asyncio
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class DiffGenerator:
    """Generates unified diffs from the shadow workspace Git repository.

    After Aider executes and commits changes in the shadow workspace,
    this class extracts the diff between the current HEAD and the
    pre-flight sync commit (HEAD~1).
    """

    @staticmethod
    async def generate_diff(shadow_root: Path, base_revision: str | None = None) -> str:
        """Generate a unified diff from git diff HEAD~1.

        Returns:
            Unified diff string. Empty string if no changes detected.

        Raises:
            RuntimeError: If git diff command fails.
        """
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", base_revision or "HEAD~1", "HEAD",
            cwd=shadow_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"git diff HEAD~1 failed: {stderr.decode().strip()}"
            )

        diff_text = stdout.decode("utf-8", errors="replace")
        logger.info(
            "Generated diff: %d bytes, %d lines",
            len(diff_text),
            diff_text.count("\n"),
        )
        return diff_text

    @staticmethod
    async def get_changed_files(shadow_root: Path, base_revision: str | None = None) -> List[str]:
        """Extract list of changed files from git diff --name-only HEAD~1.

        Returns:
            List of relative file paths that were changed.
        """
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--name-only", base_revision or "HEAD~1", "HEAD",
            cwd=shadow_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"git diff --name-only failed: {stderr.decode().strip()}"
            )

        return [
            line
            for line in stdout.decode("utf-8").splitlines()
            if line.strip()
        ]

    @staticmethod
    async def has_changes(shadow_root: Path, base_revision: str | None = None) -> bool:
        """Quick check whether the shadow workspace has uncommitted or
        committed changes relative to the pre-flight sync."""
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--quiet", base_revision or "HEAD~1", "HEAD",
            cwd=shadow_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        # Exit code 0 = no diff, 1 = differences exist
        return proc.returncode == 1
