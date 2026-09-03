"""Shadow workspace manager: creation, validation, and cleanup."""

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from alchemist.errors import ShadowSyncFailedError, ShadowWorkspaceNotInitializedError
from alchemist.workspace.ignore import collect_files_for_shadow

logger = logging.getLogger(__name__)


@dataclass
class ShadowWorkspace:
    """Represents an active shadow workspace for a project."""

    project_id: str
    project_path: Path
    shadow_root: Path
    initialized: bool = False
    pending_diff: Optional[str] = None
    base_hashes: Dict[str, str] = field(default_factory=dict)
    base_revision: Optional[str] = None


class ShadowManager:
    """Manages shadow workspace lifecycle for all active projects.

    Responsibilities:
    - Create and validate shadow workspace directories
    - Clone project files respecting ignore rules
    - Initialize shallow Git sandboxes
    - Track workspace state
    - Clean up on daemon shutdown
    """

    def __init__(self) -> None:
        self._workspaces: Dict[str, ShadowWorkspace] = {}

    async def initialize(
        self, project_id: str, project_path: str
    ) -> ShadowWorkspace:
        """Initialize or reinitialize a shadow workspace for a project.

        Creates .git/alchemist/shadow, copies eligible files,
        and initializes a fresh Git repository.
        """
        source = Path(project_path).resolve()
        git_dir = source / ".git"

        if not git_dir.is_dir():
            raise ShadowSyncFailedError(
                "Project is not a Git repository",
                hint=f"No .git directory found at {source}. "
                     "Aider requires a Git-tracked project.",
            )

        shadow_root = git_dir / "alchemist" / "shadow"

        # Clean existing workspace if present
        if shadow_root.exists():
            await asyncio.to_thread(shutil.rmtree, shadow_root)

        # Create shadow directory
        shadow_root.mkdir(parents=True, exist_ok=True)

        # Copy eligible files
        try:
            eligible_files = await asyncio.to_thread(
                collect_files_for_shadow, source
            )
        except RuntimeError as e:
            raise ShadowSyncFailedError(
                f"Failed to enumerate project files: {e}"
            ) from e

        await asyncio.to_thread(
            self._copy_files, source, shadow_root, eligible_files
        )

        # Initialize Git sandbox
        await self._git_init(shadow_root)
        await self._git_commit(shadow_root, "shadow workspace baseline")

        workspace = ShadowWorkspace(
            project_id=project_id,
            project_path=source,
            shadow_root=shadow_root,
            initialized=True,
        )
        self._workspaces[project_id] = workspace

        logger.info(
            "Shadow workspace initialized: %s -> %s",
            source,
            shadow_root,
        )
        return workspace

    def get_workspace(self, project_id: str) -> ShadowWorkspace:
        """Get the active workspace for a project, or raise."""
        ws = self._workspaces.get(project_id)
        if ws is None or not ws.initialized:
            raise ShadowWorkspaceNotInitializedError(
                f"No active shadow workspace for project {project_id}"
            )
        return ws

    def has_workspace(self, project_id: str) -> bool:
        """Check if a workspace exists for a project."""
        ws = self._workspaces.get(project_id)
        return ws is not None and ws.initialized

    async def cleanup(self, project_id: str) -> None:
        """Delete a specific project's shadow workspace."""
        ws = self._workspaces.pop(project_id, None)
        if ws and ws.shadow_root.exists():
            await asyncio.to_thread(shutil.rmtree, ws.shadow_root)
            logger.info("Cleaned up shadow workspace: %s", ws.shadow_root)

    async def cleanup_all(self) -> None:
        """Delete all shadow workspaces. Called on daemon shutdown."""
        for project_id in list(self._workspaces.keys()):
            await self.cleanup(project_id)
        logger.info("All shadow workspaces cleaned up")

    @staticmethod
    def _copy_files(
        source: Path, shadow_root: Path, eligible_files: List[Path]
    ) -> None:
        """Copy eligible files preserving directory structure."""
        for abs_path in eligible_files:
            rel_path = abs_path.relative_to(source)
            dest = shadow_root / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abs_path, dest)

    @staticmethod
    async def _git_init(shadow_root: Path) -> None:
        """Initialize a fresh Git repository in the shadow workspace."""
        proc = await asyncio.create_subprocess_exec(
            "git", "init",
            cwd=shadow_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ShadowSyncFailedError(
                f"git init failed in shadow workspace: {stderr.decode().strip()}"
            )
        # Configure git user for commits (required for git commit)
        for key, val in [
            ("user.email", "alchemist@local"),
            ("user.name", "Alchemist Shadow"),
        ]:
            cfg_proc = await asyncio.create_subprocess_exec(
                "git", "config", key, val,
                cwd=shadow_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await cfg_proc.communicate()

    @staticmethod
    async def _git_commit(
        shadow_root: Path, message: str
    ) -> None:
        """Stage all files and commit in the shadow workspace."""
        # git add .
        proc = await asyncio.create_subprocess_exec(
            "git", "add", ".",
            cwd=shadow_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # git commit (allow empty for baseline)
        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", message, "--allow-empty",
            cwd=shadow_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ShadowSyncFailedError(
                f"git commit failed: {stderr.decode().strip()}"
            )
