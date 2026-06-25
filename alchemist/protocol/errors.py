"""
Standardized Alchemist error model and JSON-RPC error codes.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Standard JSON-RPC error codes
# ---------------------------------------------------------------------------

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# Alchemist application error codes  (-32000 .. -32099)
# ---------------------------------------------------------------------------

class AlchemistErrorCode(IntEnum):
    NO_KEYS_CONFIGURED = -32000
    PROVIDER_RATE_LIMITED = -32001
    ALL_KEYS_EXHAUSTED = -32002
    PATCH_APPLY_FAILED = -32003
    AIDER_INTERNAL_ERROR = -32004
    UV_BOOTSTRAP_FAILED = -32005
    MODEL_CONTEXT_EXCEEDED = -32006
    DAEMON_VERSION_MISMATCH = -32007
    SHADOW_SYNC_FAILED = -32008
    FRAME_TOO_LARGE = -32009
    IPC_DISCONNECTED = -32010
    DAEMON_UNAVAILABLE = -32011
    AGENT_BUSY = -32012


_HINTS: dict[AlchemistErrorCode, str] = {
    AlchemistErrorCode.NO_KEYS_CONFIGURED: (
        "Run :AlchemistSetup and add an API key."
    ),
    AlchemistErrorCode.PROVIDER_RATE_LIMITED: (
        "Provider is rate-limited. Waiting for cooldown."
    ),
    AlchemistErrorCode.ALL_KEYS_EXHAUSTED: (
        "Add another key or wait for provider quota reset."
    ),
    AlchemistErrorCode.PATCH_APPLY_FAILED: (
        "Buffers were restored. Reopen the diff or retry the prompt."
    ),
    AlchemistErrorCode.AIDER_INTERNAL_ERROR: (
        "Aider encountered an internal error. Check the daemon log."
    ),
    AlchemistErrorCode.UV_BOOTSTRAP_FAILED: (
        "uv environment setup failed. Run :AlchemistSetup again."
    ),
    AlchemistErrorCode.MODEL_CONTEXT_EXCEEDED: (
        "Prompt is too long for the selected model. Reduce context."
    ),
    AlchemistErrorCode.DAEMON_VERSION_MISMATCH: (
        "Update the plugin and rerun setup."
    ),
    AlchemistErrorCode.SHADOW_SYNC_FAILED: (
        "Shadow workspace sync failed. Save your buffers and retry."
    ),
    AlchemistErrorCode.FRAME_TOO_LARGE: (
        "IPC frame exceeded 16 MiB limit. This is likely a bug."
    ),
    AlchemistErrorCode.IPC_DISCONNECTED: (
        "Connection to daemon lost. Restart with :AlchemistStart."
    ),
    AlchemistErrorCode.DAEMON_UNAVAILABLE: (
        "Daemon is not running. Start it with :AlchemistStart."
    ),
    AlchemistErrorCode.AGENT_BUSY: (
        "Agent is busy. Cancel the current operation or wait."
    ),
}


def get_hint(code: AlchemistErrorCode) -> str:
    return _HINTS[code]


# ---------------------------------------------------------------------------
# Alchemist error data model
# ---------------------------------------------------------------------------

class AlchemistErrorData(BaseModel):
    """Structured error data embedded inside JSON-RPC error objects."""

    code: str          # AlchemistErrorCode.name
    retryable: bool
    hint: str
    client_id: Optional[str] = None
    session_id: Optional[str] = None
    project_id: Optional[str] = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Error data factory
# ---------------------------------------------------------------------------

def make_alchemist_error_data(
    code: AlchemistErrorCode,
    retryable: bool = False,
    client_id: Optional[str] = None,
    session_id: Optional[str] = None,
    project_id: Optional[str] = None,
    **extra: Any,
) -> AlchemistErrorData:
    return AlchemistErrorData(
        code=code.name,
        retryable=retryable,
        hint=get_hint(code),
        client_id=client_id,
        session_id=session_id,
        project_id=project_id,
        **extra,
    )


# ---------------------------------------------------------------------------
# JSON-RPC error object dict factories
# ---------------------------------------------------------------------------

def make_parse_error(message: str = "Parse error") -> dict:
    return {"code": PARSE_ERROR, "message": message, "data": None}


def make_invalid_request(message: str = "Invalid Request") -> dict:
    return {"code": INVALID_REQUEST, "message": message, "data": None}


def make_method_not_found(method: str) -> dict:
    return {
        "code": METHOD_NOT_FOUND,
        "message": f"Method not found: {method}",
        "data": None,
    }


def make_invalid_params(message: str = "Invalid params") -> dict:
    return {"code": INVALID_PARAMS, "message": message, "data": None}


def make_internal_error(message: str = "Internal error") -> dict:
    return {"code": INTERNAL_ERROR, "message": message, "data": None}


def make_alchemist_error(
    code: AlchemistErrorCode,
    retryable: bool = False,
    client_id: Optional[str] = None,
    session_id: Optional[str] = None,
    project_id: Optional[str] = None,
    **extra: Any,
) -> dict:
    data = make_alchemist_error_data(
        code=code,
        retryable=retryable,
        client_id=client_id,
        session_id=session_id,
        project_id=project_id,
        **extra,
    )
    return {
        "code": int(code),
        "message": code.name,
        "data": data.model_dump(),
    }
