"""Pre-flight sync: materialize NeoVim buffer contents into shadow workspace."""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

from alchemist.errors import ShadowSyncFailedError

if TYPE_CHECKING:
    from alchemist.protocol.models.client_to_daemon import BufferSnapshot

logger = logging.getLogger(__name__)


class PreFlightSync:
    """Synchronizes live NeoVim buffer state into the shadow workspace.

    Before each Aider execution, the daemon overwrites shadow workspace
    files with the client's in-memory buffer contents to ensure the
    agent sees the user's latest edits (including unsaved changes).
    """

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute SHA-256 hash of content string."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    async def sync_buffers(
        shadow_root: Path,
        buffers: List["BufferSnapshot"],
    ) -> Dict[str, str]:
        """Write buffer contents to shadow workspace and return base hashes.

        Args:
            shadow_root: Path to the shadow workspace root.
            buffers: List of BufferSnapshot objects from the client.

        Returns:
            Dictionary mapping relative file paths to their SHA-256 hashes
            at the time of sync (used for optimistic locking).

        Raises:
            ShadowSyncFailedError: If buffer write fails.
        """
        base_hashes: Dict[str, str] = {}

        for buf in buffers:
            rel_path = buf.path
            content = buf.content
            content_hash = buf.sha256

            # Validate the provided hash matches the content
            computed = PreFlightSync.compute_hash(content)
            if computed != content_hash:
                logger.warning(
                    "Hash mismatch for %s: client=%s computed=%s (using computed)",
                    rel_path,
                    content_hash,
                    computed,
                )
                content_hash = computed

            target = shadow_root / rel_path
            try:
                await asyncio.to_thread(
                    PreFlightSync._write_file, target, content
                )
            except OSError as e:
                raise ShadowSyncFailedError(
                    f"Failed to write buffer to shadow workspace: {rel_path}",
                    hint=f"Could not write {target}: {e}",
                ) from e

            base_hashes[rel_path] = content_hash
            logger.debug("Synced buffer: %s (hash=%s...)", rel_path, content_hash[:12])

        return base_hashes

    @staticmethod
    async def commit_sync(
        shadow_root: Path, message: str = "pre-flight sync"
    ) -> None:
        """Stage and commit the synchronized buffer state.

        This creates the commit that Aider will build upon,
        allowing `git diff HEAD~1` to capture Aider's changes.
        """
        # git add .
        proc = await asyncio.create_subprocess_exec(
            "git", "add", ".",
            cwd=shadow_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # git commit (allow empty in case buffers match filesystem)
        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", message, "--allow-empty",
            cwd=shadow_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ShadowSyncFailedError(
                f"Pre-flight sync commit failed: {stderr.decode().strip()}"
            )

    @staticmethod
    def _write_file(target: Path, content: str) -> None:
        """Write content to file, creating parent directories as needed."""
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
