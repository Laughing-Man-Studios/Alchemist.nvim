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
    AgentAddFileParams,
    AgentCancelParams,
    AgentClearParams,
    AgentDropFileParams,
    AgentLintParams,
    AgentListFilesParams,
    AgentListSessionsParams,
    AgentReadOnlyParams,
    AgentRejectDiffParams,
    AgentRepoMapParams,
    AgentResetParams,
    AgentRunParams,
    AgentStatusParams,
    AgentSubmitPromptParams,
    AgentTestParams,
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
        self._session_files: Dict[str, Dict[str, set[str]]] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}

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
        task = asyncio.create_task(
            self._execute_prompt(validated),
            name=f"prompt-{session_id[:8]}",
        )
        self._active_tasks[session_id] = task

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

    async def handle_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/cancel: cancel in-flight prompt task."""
        validated = AgentCancelParams(**params)
        session_id = str(validated.session_id)

        task = self._active_tasks.pop(session_id, None)
        cancelled = False
        if task and not task.done():
            task.cancel()
            cancelled = True

        await self.engine.cancel(session_id)
        self.job_tracker.clear_job(session_id)

        return {"cancelled": cancelled, "state": "cancelled" if cancelled else "idle"}

    async def handle_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/status: return current agent state."""
        validated = AgentStatusParams(**params)
        session_id = str(validated.session_id)

        active_job = self.job_tracker.get_current_job()
        engine_status = await self.engine.get_status(session_id)

        if active_job and active_job["session_id"] == session_id:
            return {"status": "busy", "active_job": active_job}
        return {"status": engine_status.get("state", "idle"), "active_job": None}

    async def handle_reset(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/reset: full session teardown."""
        validated = AgentResetParams(**params)
        session_id = str(validated.session_id)
        project_id = str(validated.project_id)

        task = self._active_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

        await self.engine.reset(session_id)
        self.job_tracker.force_clear()
        self._session_files.pop(session_id, None)

        if self.shadow_manager.has_workspace(project_id):
            workspace = self.shadow_manager.get_workspace(project_id)
            workspace.pending_diff = None
            workspace.base_hashes = {}

        return {}

    async def handle_clear(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/clear: clear chat history, keep context files."""
        validated = AgentClearParams(**params)
        session_id = str(validated.session_id)

        clear_func = getattr(self.engine, "clear", None)
        if clear_func:
            await clear_func(session_id)
        else:
            await self.engine.reset(session_id)

        return {}

    async def handle_list_sessions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/list_sessions: list tracked sessions."""
        validated = AgentListSessionsParams(**params)

        sessions = list(self._session_files.keys())
        engine_sessions = getattr(self.engine, "_sessions", {})
        for sid in engine_sessions:
            if sid not in sessions:
                sessions.append(sid)

        return {"sessions": sessions}

    def _get_session_files(self, session_id: str) -> Dict[str, set[str]]:
        """Get or create the file context for a session."""
        if session_id not in self._session_files:
            self._session_files[session_id] = {
                "editable": set(),
                "read_only": set(),
            }
        return self._session_files[session_id]

    async def handle_add_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/add_file: add a file to the editable context."""
        validated = AgentAddFileParams(**params)
        session_id = str(validated.session_id)

        files = self._get_session_files(session_id)
        files["read_only"].discard(validated.path)
        files["editable"].add(validated.path)

        return {}

    async def handle_drop_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/drop_file: remove a file from all context sets."""
        validated = AgentDropFileParams(**params)
        session_id = str(validated.session_id)

        files = self._get_session_files(session_id)
        files["editable"].discard(validated.path)
        files["read_only"].discard(validated.path)

        return {}

    async def handle_list_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/list_files: return editable and read-only context files."""
        validated = AgentListFilesParams(**params)
        session_id = str(validated.session_id)

        files = self._get_session_files(session_id)
        return {
            "editable": sorted(files["editable"]),
            "read_only": sorted(files["read_only"]),
        }

    async def handle_read_only(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/read_only: toggle a file's read-only status."""
        validated = AgentReadOnlyParams(**params)
        session_id = str(validated.session_id)

        files = self._get_session_files(session_id)
        if validated.enabled:
            files["editable"].discard(validated.path)
            files["read_only"].add(validated.path)
        else:
            files["read_only"].discard(validated.path)
            files["editable"].add(validated.path)

        return {}

    async def handle_repo_map(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/repo_map: generate a repository structure map."""
        validated = AgentRepoMapParams(**params)
        project_id = str(validated.project_id)

        if not self.shadow_manager.has_workspace(project_id):
            return {"map": "", "files": []}

        workspace = self.shadow_manager.get_workspace(project_id)
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-files", cwd=workspace.shadow_root,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        file_list = out.decode().strip().splitlines() if out else []

        return {"map": "\n".join(file_list), "files": file_list}

    async def handle_run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/run: execute a shell command, streaming output."""
        validated = AgentRunParams(**params)
        client_id = str(validated.client_id)
        project_id = str(validated.project_id)

        cwd = None
        if self.shadow_manager.has_workspace(project_id):
            workspace = self.shadow_manager.get_workspace(project_id)
            cwd = str(workspace.project_path)

        exit_code = await self._run_command(validated.command, client_id, cwd)
        return {"exit_code": exit_code}

    async def handle_test(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/test: run the project test suite."""
        validated = AgentTestParams(**params)
        client_id = str(validated.client_id)
        project_id = str(validated.project_id)

        cwd = None
        if self.shadow_manager.has_workspace(project_id):
            workspace = self.shadow_manager.get_workspace(project_id)
            cwd = str(workspace.project_path)

        command = await self._detect_test_command(cwd)
        exit_code = await self._run_command(command, client_id, cwd)
        return {"exit_code": exit_code}

    async def handle_lint(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle agent/lint: run the project linter."""
        validated = AgentLintParams(**params)
        client_id = str(validated.client_id)
        project_id = str(validated.project_id)

        cwd = None
        if self.shadow_manager.has_workspace(project_id):
            workspace = self.shadow_manager.get_workspace(project_id)
            cwd = str(workspace.project_path)

        command = await self._detect_lint_command(cwd)
        exit_code = await self._run_command(command, client_id, cwd)
        return {"exit_code": exit_code}

    async def _run_command(self, command: str, client_id: str, cwd: str | None) -> int:
        """Run a shell command, streaming stdout/stderr via broadcaster."""
        proc = await asyncio.create_subprocess_shell(
            command, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        if proc.stdout:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                self.broadcaster.notify_client(client_id, "agent/stream_delta", {
                    "delta": line.decode(errors="replace"),
                })
        await proc.wait()
        return proc.returncode if proc.returncode is not None else 0

    @staticmethod
    async def _detect_test_command(cwd: str | None) -> str:
        """Detect the project's test command based on config files."""
        if cwd:
            from pathlib import Path
            root = Path(cwd)
            if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists():
                return "python -m pytest"
            if (root / "package.json").exists():
                return "npm test"
            if (root / "Cargo.toml").exists():
                return "cargo test"
            if (root / "go.mod").exists():
                return "go test ./..."
        return "echo 'No test runner detected'"

    @staticmethod
    async def _detect_lint_command(cwd: str | None) -> str:
        """Detect the project's lint command based on config files."""
        if cwd:
            from pathlib import Path
            root = Path(cwd)
            if (root / "pyproject.toml").exists():
                return "python -m ruff check ."
            if (root / "package.json").exists():
                return "npx eslint ."
            if (root / "Cargo.toml").exists():
                return "cargo clippy"
            if (root / "go.mod").exists():
                return "golangci-lint run"
        return "echo 'No linter detected'"

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
        finally:
            self._active_tasks.pop(session_id, None)

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
