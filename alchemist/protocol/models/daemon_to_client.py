"""
This module defines the Pydantic data models used for communication between the daemon, the agent, and the client.

It categorizes messages into three primary functional areas:

1. UI Notifications: Models for updating the user interface, such as live status updates from agent operations, signaling when diffs are ready for review, or instructing the client to clear prompt inputs.
2. Agent Notifications: Models for streaming text deltas from the agent to the client.
3. Daemon Notifications: Models for system-level events, including API key rotations, error reporting, and exhaustion of provider resources.

Additionally, the module defines the structure for server-initiated requests, allowing the daemon to request user confirmation or input via the client, and the corresponding result structures used for client responses.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from alchemist.protocol.models.common import (
    ClientScopedParams,
    ProjectScopedParams,
)


# ---------------------------------------------------------------------------
# ui/* notifications
# ---------------------------------------------------------------------------

class UiStatusUpdateParams(ProjectScopedParams):
    """ui/status_update — live status from a running agent operation."""

    status: str
    model: str
    provider: str
    key_index: int
    tokens_per_second: Optional[float] = None
    phase: str


class UiDiffReadyParams(ProjectScopedParams):
    """ui/diff_ready — agent has produced a diff ready for review."""

    base_hashes: Dict[str, str]
    diff: str
    files_changed: List[str]


class UiClearPromptParams(BaseModel):
    """ui/clear_prompt — tell the client to clear the prompt input."""


# ---------------------------------------------------------------------------
# agent/* notifications
# ---------------------------------------------------------------------------

class AgentStreamDeltaParams(ProjectScopedParams):
    """agent/stream_delta — streaming text chunk from the agent."""

    delta: str


# ---------------------------------------------------------------------------
# daemon/* notifications
# ---------------------------------------------------------------------------

class DaemonKeySwappedParams(BaseModel):
    """daemon/key_swapped — daemon has rotated to a different API key."""

    provider: str
    model: str
    current_key_index: int
    cooldown_target: Optional[str] = None   # ISO-8601 timestamp or None
    reason: str


class DaemonErrorParams(BaseModel):
    """daemon/error — generic daemon-level error notification."""

    code: str
    message: str
    retryable: bool = False
    hint: Optional[str] = None


class DaemonExhaustedParams(BaseModel):
    """daemon/exhausted — all provider keys are exhausted."""


# ---------------------------------------------------------------------------
# server/* — server-initiated request
# ---------------------------------------------------------------------------

PromptType = Literal["boolean", "text", "selection"]


class ServerRequestConfirmationParams(ProjectScopedParams):
    """server/request_confirmation — daemon asks the client for user input."""

    prompt_type: PromptType
    message: str
    default_value: Optional[str] = None
    timeout_ms: int = Field(default=60_000, ge=0)


# ---------------------------------------------------------------------------
# Confirmation response result (client reply to server/request_confirmation)
# ---------------------------------------------------------------------------

class ConfirmationResult(BaseModel):
    """Result body sent back by the client for a server/request_confirmation."""

    confirmed: bool
    value: Optional[str] = None
