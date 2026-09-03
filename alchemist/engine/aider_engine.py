"""Real Aider adapter, isolated from the daemon event loop."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from aider.coders import Coder
from aider.models import Model
from aider.repo import GitRepo

from alchemist.engine.bridge import ThreadIsolatedBridge
from alchemist.engine.interface import AssistantEngine, PromptContext
from alchemist.engine.io_intercept import InterceptedIO
from alchemist.engine.litellm_interceptor import LiteLLMInterceptor
from alchemist.engine.routing import RoutingPolicy
from alchemist.state.vault import LocalVault

logger = logging.getLogger(__name__)


@dataclass
class _Session:
    coder: Any
    workspace_root: Path
    model: str
    provider: str


class AiderEngine(AssistantEngine):
    """Runs one blocking Aider Coder at a time in the shadow workspace."""

    def __init__(self, vault: LocalVault, broadcaster: Any,
                 bridge: ThreadIsolatedBridge, coder_factory: Callable[..., Any] = Coder.create,
                 interceptor: Optional[LiteLLMInterceptor] = None) -> None:
        self.vault = vault
        self.broadcaster = broadcaster
        self.bridge = bridge
        self.coder_factory = coder_factory
        self.interceptor = interceptor or LiteLLMInterceptor()
        self._sessions: Dict[str, _Session] = {}

    def _route(self, mode: str) -> tuple[str, str, Any]:
        configured = [provider for provider, slots in self.vault.list_keys().items() if slots]
        model = RoutingPolicy.route_request(mode, configured)
        provider = model.split("/", 1)[0]
        key = self.vault.get_key(provider, 0)
        if key is None:  # defensive: vault changed after routing
            raise ValueError("No configured provider supports this prompt mode")
        return model, provider, key

    def can_submit(self, mode: str) -> bool:
        try:
            self._route(mode)
        except ValueError:
            return False
        return True

    async def submit_prompt(self, context: PromptContext | str, prompt: Optional[str] = None) -> None:
        if isinstance(context, str):
            raise TypeError("AiderEngine requires PromptContext")
        model, provider, key = self._route(context.mode)
        self.broadcaster.notify_client(context.client_id, "ui/status_update", {
            "client_id": context.client_id, "session_id": context.session_id,
            "project_id": context.project_id,
            "status": "processing", "model": model, "provider": provider,
            "key_index": 0, "phase": "agent_execution",
        })
        await self.bridge.run_in_thread(self._run, context, model, provider, key)

    def _run(self, context: PromptContext, model: str, provider: str, key: Any) -> None:
        existing = self._sessions.get(context.session_id)
        io = InterceptedIO(context.session_id, context.client_id, context.project_id, self.bridge.loop,
                           self.broadcaster.notify_client, str(context.workspace_root))
        if existing and existing.workspace_root == context.workspace_root and existing.model == model:
            coder = existing.coder
            coder.io = io
        else:
            fnames = [str((context.workspace_root / name).resolve()) for name in context.active_files]
            repo = GitRepo(io, fnames, str(context.workspace_root))
            coder = self.coder_factory(
                main_model=Model(model), io=io, repo=repo, fnames=fnames,
                auto_commits=True, dirty_commits=True, restore_chat_history=False,
                auto_lint=False, auto_test=False, suggest_shell_commands=False,
            )
            self._sessions[context.session_id] = _Session(coder, context.workspace_root, model, provider)
        with self.interceptor.scoped_completion(key):
            coder.run(with_message=context.prompt)

    async def cancel(self, session_id: str) -> None:
        # Aider has no safe cancellation primitive in this embedded version.
        return None

    async def get_status(self, session_id: str) -> Dict[str, Any]:
        return {"state": "idle", "session_id": session_id}

    async def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def reject(self, session_id: str) -> None:
        """Discard Aider conversation after its changes are rejected."""
        await self.reset(session_id)

    async def shutdown(self) -> None:
        self._sessions.clear()
        self.bridge.shutdown()
