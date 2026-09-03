"""Accept/reject lifecycle handlers for shadow workspace diffs."""

import asyncio
import logging

from alchemist.errors import ShadowSyncFailedError
from alchemist.workspace.manager import ShadowWorkspace

logger = logging.getLogger(__name__)


class AcceptanceFlow:
    """Handles diff acceptance: updates the shadow workspace baseline.

    When the client confirms that the patch was successfully applied
    and written to disk, the shadow workspace's current HEAD (which
    includes Aider's changes) becomes the new baseline. No git
    operations are needed—the HEAD already reflects the accepted state.
    """

    @staticmethod
    async def accept(workspace: ShadowWorkspace) -> None:
        """Update shadow workspace baseline after successful patch application.

        The current HEAD already contains Aider's changes. We simply
        clear the pending diff metadata and mark the workspace as ready
        for the next operation.
        """
        workspace.pending_diff = None
        workspace.base_hashes.clear()
        workspace.base_revision = None

        logger.info(
            "Diff accepted for project %s. Shadow baseline updated.",
            workspace.project_id,
        )


class RejectionFlow:
    """Handles diff rejection: rewinds the shadow workspace.

    When the user rejects a diff, the shadow workspace is rewound
    to the pre-Aider state using `git reset --hard HEAD~1`.
    """

    @staticmethod
    async def reject(workspace: ShadowWorkspace) -> None:
        """Rewind shadow workspace to pre-Aider state.

        Executes `git reset --hard HEAD~1` in the shadow workspace
        to discard Aider's changes and restore the pre-flight sync state.
        """
        shadow_root = workspace.shadow_root

        proc = await asyncio.create_subprocess_exec(
            "git", "reset", "--hard", workspace.base_revision or "HEAD~1",
            cwd=shadow_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise ShadowSyncFailedError(
                f"Shadow workspace rewind failed: {stderr.decode().strip()}",
                hint="Try restarting the daemon to reset the shadow workspace.",
            )

        workspace.pending_diff = None
        workspace.base_hashes.clear()
        workspace.base_revision = None

        logger.info(
            "Diff rejected for project %s. Shadow workspace rewound.",
            workspace.project_id,
        )
