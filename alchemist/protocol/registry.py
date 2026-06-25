"""
Method registry for the Alchemist JSON-RPC protocol.

Maps method strings to (params_model, result_model, handler, direction).
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, Literal, Optional, Type

from pydantic import BaseModel

from alchemist.protocol.models.client_to_daemon import (
    AgentAddFileParams,
    AgentCancelParams,
    AgentClearParams,
    AgentDropFileParams,
    AgentLintParams,
    AgentListFilesParams,
    AgentListSessionsParams,
    AgentReadOnlyParams,
    AgentRepoMapParams,
    AgentResetParams,
    AgentRunParams,
    AgentStatusParams,
    AgentSubmitPromptParams,
    AgentTestParams,
    ClientInitializeParams,
    ClientShutdownParams,
    ConfigDeleteKeyParams,
    ConfigListKeysParams,
    ConfigListProvidersParams,
    ConfigSetKeyParams,
    DaemonHealthParams,
    DaemonVersionParams,
)
from alchemist.protocol.models.daemon_to_client import (
    AgentStreamDeltaParams,
    ConfirmationResult,
    DaemonErrorParams,
    DaemonExhaustedParams,
    DaemonKeySwappedParams,
    ServerRequestConfirmationParams,
    UiClearPromptParams,
    UiDiffReadyParams,
    UiStatusUpdateParams,
)
from alchemist.protocol.models.results import (
    AgentCancelResult,
    AgentListFilesResult,
    AgentStatusResult,
    AgentSubmitPromptResult,
    ClientInitializeResult,
    ConfigListKeysResult,
    ConfigListProvidersResult,
    DaemonHealthResult,
    DaemonVersionResult,
)

Direction = Literal["client_to_daemon", "daemon_to_client"]

AsyncHandler = Callable[..., Any]


@dataclasses.dataclass
class MethodEntry:
    """Registry record for a single JSON-RPC method."""

    method: str
    params_model: Type[BaseModel]
    result_model: Optional[Type[BaseModel]]
    handler: Optional[AsyncHandler]
    direction: Direction


class MethodRegistry:
    """Central map of method strings to MethodEntry records."""

    def __init__(self) -> None:
        self._entries: Dict[str, MethodEntry] = {}

    def register(self, entry: MethodEntry) -> None:
        self._entries[entry.method] = entry

    def lookup(self, method: str) -> Optional[MethodEntry]:
        return self._entries.get(method)

    def all_methods(self) -> list[str]:
        return list(self._entries.keys())


def _placeholder_handler(*args: Any, **kwargs: Any) -> None:
    """Default no-op handler for methods not yet implemented in Phase 1."""
    return None


def build_default_registry(
    override_handlers: Optional[Dict[str, AsyncHandler]] = None,
) -> MethodRegistry:
    """Construct a MethodRegistry pre-populated with all V1 method entries.

    Parameters
    ----------
    override_handlers:
        Optional mapping of method -> handler to inject for testing.
    """
    overrides = override_handlers or {}
    registry = MethodRegistry()

    _c2d: list[tuple[str, Type[BaseModel], Optional[Type[BaseModel]]]] = [
        # client/*
        ("client/initialize",       ClientInitializeParams,    ClientInitializeResult),
        ("client/shutdown",         ClientShutdownParams,      None),
        # daemon/*
        ("daemon/version",          DaemonVersionParams,       DaemonVersionResult),
        ("daemon/health",           DaemonHealthParams,        DaemonHealthResult),
        # agent/*
        ("agent/submit_prompt",     AgentSubmitPromptParams,   AgentSubmitPromptResult),
        ("agent/cancel",            AgentCancelParams,         AgentCancelResult),
        ("agent/status",            AgentStatusParams,         AgentStatusResult),
        ("agent/list_sessions",     AgentListSessionsParams,   None),
        ("agent/reset",             AgentResetParams,          None),
        ("agent/clear",             AgentClearParams,          None),
        ("agent/add_file",          AgentAddFileParams,        None),
        ("agent/drop_file",         AgentDropFileParams,       None),
        ("agent/list_files",        AgentListFilesParams,      AgentListFilesResult),
        ("agent/read_only",         AgentReadOnlyParams,       None),
        ("agent/repo_map",          AgentRepoMapParams,        None),
        ("agent/run",               AgentRunParams,            None),
        ("agent/test",              AgentTestParams,           None),
        ("agent/lint",              AgentLintParams,           None),
        # config/*
        ("config/set_key",          ConfigSetKeyParams,        None),
        ("config/list_providers",   ConfigListProvidersParams, ConfigListProvidersResult),
        ("config/list_keys",        ConfigListKeysParams,      ConfigListKeysResult),
        ("config/delete_key",       ConfigDeleteKeyParams,     None),
    ]

    for method, params_model, result_model in _c2d:
        handler = overrides.get(method, _placeholder_handler)
        registry.register(
            MethodEntry(
                method=method,
                params_model=params_model,
                result_model=result_model,
                handler=handler,
                direction="client_to_daemon",
            )
        )

    _d2c: list[tuple[str, Type[BaseModel], Optional[Type[BaseModel]]]] = [
        # ui/* notifications
        ("ui/status_update",              UiStatusUpdateParams,              None),
        ("ui/diff_ready",                 UiDiffReadyParams,                 None),
        ("ui/clear_prompt",               UiClearPromptParams,               None),
        # agent/* notifications
        ("agent/stream_delta",            AgentStreamDeltaParams,            None),
        # daemon/* notifications
        ("daemon/key_swapped",            DaemonKeySwappedParams,            None),
        ("daemon/error",                  DaemonErrorParams,                 None),
        ("daemon/exhausted",              DaemonExhaustedParams,             None),
        # server-initiated request
        ("server/request_confirmation",   ServerRequestConfirmationParams,   ConfirmationResult),
    ]

    for method, params_model, result_model in _d2c:
        handler = overrides.get(method, _placeholder_handler)
        registry.register(
            MethodEntry(
                method=method,
                params_model=params_model,
                result_model=result_model,
                handler=handler,
                direction="daemon_to_client",
            )
        )

    return registry
