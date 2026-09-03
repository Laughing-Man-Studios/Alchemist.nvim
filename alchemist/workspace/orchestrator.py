"""Prompt orchestrator: coordinates shadow workspace, engine, and diff lifecycle."""

import asyncio
import logging
from typing import Any, Dict

from alchemist.daemon.active_job import ActiveJobTracker
from alchemist.daemon.broadcaster import Broadcaster
from alchemist.engine.interface import AssistantEngine, PromptContext
from alchemist.errors import NoKeysConfiguredError, ShadowSyncFailedError
from alchemist.protocol.models.client_to_daemon import (
    AgentAcceptDiffParams,
    AgentRejectDiffParams,
    AgentSubmitPromptParams,
)
from alchemist.workspace.diff import DiffGenerator
from alchemist.workspace.lifecycle import AcceptanceFlow, RejectionFlow
from alchemist.workspace.manager import ShadowManager
from alchemist.workspace.sync import PreFlightSync

logger = logging.getLogger(__name__)


class PromptOrchestrator:
    """Coordinates the full agent prompt lifecycle:

    1. Acquire global job lock
    2. Initialize/validate shadow workspace
    3. Pre-flight sync buffers
    4. Execute engine in shadow workspace
    5. Generate diff
    6. Broadcast diff_ready to client
    7. Handle accept/reject
    """

    def __init__(
        self,
        shadow_manager: ShadowManager,
        engine: AssistantEngine,
        job_tracker: ActiveJobTracker,
        broadcaster: Broadcaster,
    ) -> None:
        self.shadow_manager = shadow_manager
        self.engine = engine
        self.job_tracker = job_tracker
        self.broadcaster = broadcaster

    async def handle_submit_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/submit_prompt: validate, launch background execution."""
        validated = AgentSubmitPromptParams(**params)
        session_id = str(validated.session_id)
        project_id = str(validated.project_id)

        can_submit = getattr(self.engine, "can_submit", None)
        if can_submit is not None and not can_submit(validated.mode):
            raise NoKeysConfiguredError("No API key is configured for this prompt mode.")

        # Acquire global job lock (raises AgentBusyError if busy)
        self.job_tracker.start_job(
            session_id=session_id,
            project_id=project_id,
            task_description=validated.prompt[:100],
        )

        # Launch background execution task
        asyncio.create_task(
            self._execute_prompt(validated),
            name=f"prompt-{session_id[:8]}",
        )

        return {"status": "accepted", "job_id": session_id}

    async def handle_accept_diff(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/accept_diff: update shadow baseline."""
        validated = AgentAcceptDiffParams(**params)
        project_id = str(validated.project_id)
        session_id = str(validated.session_id)

        workspace = self.shadow_manager.get_workspace(project_id)
        await AcceptanceFlow.accept(workspace)
        self.job_tracker.clear_job(session_id)

        return {"status": "applied"}

    async def handle_reject_diff(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/reject_diff: rewind shadow workspace."""
        validated = AgentRejectDiffParams(**params)
        project_id = str(validated.project_id)
        session_id = str(validated.session_id)

        workspace = self.shadow_manager.get_workspace(project_id)
        await RejectionFlow.reject(workspace)
        reject = getattr(self.engine, "reject", None)
        if reject:
            await reject(session_id)
        self.job_tracker.clear_job(session_id)

        return {"status": "reverted"}

    async def _execute_prompt(self, params: AgentSubmitPromptParams) -> None:
        """Background task: full prompt execution pipeline."""
        session_id = str(params.session_id)
        project_id = str(params.project_id)
        client_id = str(params.client_id)

        try:
            # 1. Initialize or get shadow workspace
            if not self.shadow_manager.has_workspace(project_id):
                workspace = await self.shadow_manager.initialize(
                    project_id, params.project_path
                )
            else:
                workspace = self.shadow_manager.get_workspace(project_id)

            # 2. Notify client: processing started
            self.broadcaster.notify_client(client_id, "ui/status_update", {
                "client_id": client_id,
                "session_id": session_id,
                "project_id": project_id,
                "status": "syncing",
                "model": "",
                "provider": "",
                "key_index": 0,
                "phase": "pre_flight_sync",
            })

            # 3. Pre-flight sync: write buffers to shadow workspace
            base_hashes = await PreFlightSync.sync_buffers(
                workspace.shadow_root, params.buffers, workspace.project_path
            )
            await PreFlightSync.commit_sync(workspace.shadow_root)
            workspace.base_revision = await self._git_revision(workspace.shadow_root)

            # Store base_hashes on workspace for later verification
            workspace.base_hashes = base_hashes

            # 4. Execute engine in shadow workspace. The engine emits its
            # provider/model-specific processing status before calling Aider.
            context = PromptContext(
                session_id=session_id,
                client_id=client_id,
                project_id=project_id,
                prompt=params.prompt,
                workspace_root=workspace.shadow_root,
                project_path=params.project_path,
                active_files=[PreFlightSync._relative_path(path, workspace.project_path)
                              for path in params.active_files],
                mode=params.mode,
            )
            await self.engine.submit_prompt(context)

            # 5. Generate diff
            diff_text = await DiffGenerator.generate_diff(workspace.shadow_root, workspace.base_revision)
            changed_files = await DiffGenerator.get_changed_files(
                workspace.shadow_root, workspace.base_revision
            )

            if not diff_text.strip():
                self.job_tracker.clear_job(session_id)
                self.broadcaster.notify_client(client_id, "ui/status_update", {
                    "client_id": client_id, "session_id": session_id, "project_id": project_id,
                    "status": "idle", "model": "", "provider": "", "key_index": 0,
                    "phase": "no_changes",
                })
                return

            # Store pending diff on workspace
            workspace.pending_diff = diff_text

            # 7. Send ui/diff_ready notification
            self.broadcaster.notify_client(client_id, "ui/diff_ready", {
                "client_id": client_id,
                "session_id": session_id,
                "project_id": project_id,
                "base_hashes": base_hashes,
                "diff": diff_text,
                "files_changed": changed_files,
            })

        except ShadowSyncFailedError:
            self.job_tracker.clear_job(session_id)
            self.broadcaster.notify_client(client_id, "daemon/error", {
                "code": "SHADOW_SYNC_FAILED",
                "message": "Shadow workspace synchronization failed.",
                "retryable": False,
                "hint": "Try restarting the daemon.",
            })
        except Exception as e:
            logger.exception("Prompt execution failed")
            self.job_tracker.clear_job(session_id)
            self.broadcaster.notify_client(client_id, "daemon/error", {
                "code": "AIDER_INTERNAL_ERROR",
                "message": "The assistant could not complete the request.",
                "retryable": False,
                "hint": "An unexpected error occurred during agent execution.",
            })

    @staticmethod
    async def _git_revision(root) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD", cwd=root, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode:
            raise RuntimeError("Unable to determine shadow workspace revision")
        return out.decode().strip()
