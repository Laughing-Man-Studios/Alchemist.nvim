"""
Client -> Daemon method param models for the Alchemist JSON-RPC protocol.

Every model name mirrors its method string, e.g.:
  client/initialize  ->  ClientInitializeParams
  agent/submit_prompt -> AgentSubmitPromptParams
"""
from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr, field_validator

from alchemist.protocol.models.common import (
    ClientScopedParams,
    ProjectScopedParams,
    SessionScopedParams,
)

# ---------------------------------------------------------------------------
# Supporting value types
# ---------------------------------------------------------------------------

PromptMode = Literal["ask", "code", "architect"]


class BufferSnapshot(BaseModel):
    """Snapshot of a NeoVim buffer at submission time."""

    path: str
    content: str
    sha256: str
    modified: bool

    @field_validator("path")
    @classmethod
    def path_nonempty(cls, v: str) -> str:
        if not v:
            raise ValueError("path must not be empty")
        return v

    @field_validator("sha256")
    @classmethod
    def sha256_nonempty(cls, v: str) -> str:
        if not v:
            raise ValueError("sha256 must not be empty")
        return v


# ---------------------------------------------------------------------------
# client/* methods
# ---------------------------------------------------------------------------

class ClientInitializeParams(ClientScopedParams):
    """client/initialize — first message from NeoVim client to daemon."""

    cwd: str
    nvim_pid: int
    protocol_version: str


class ClientShutdownParams(ClientScopedParams):
    """client/shutdown — graceful teardown request."""


# ---------------------------------------------------------------------------
# daemon/* methods
# ---------------------------------------------------------------------------

class DaemonVersionParams(ClientScopedParams):
    """daemon/version — client_id always required."""


class DaemonHealthParams(ClientScopedParams):
    """daemon/health — client_id always required."""


# ---------------------------------------------------------------------------
# agent/* methods
# ---------------------------------------------------------------------------

class AgentSubmitPromptParams(ProjectScopedParams):
    """agent/submit_prompt — submit a prompt to the active Aider session."""

    project_path: str
    mode: PromptMode
    prompt: str
    active_files: List[str] = Field(default_factory=list)
    buffers: List[BufferSnapshot] = Field(default_factory=list)


class AgentCancelParams(ProjectScopedParams):
    """agent/cancel — cancel any in-progress agent operation."""


class AgentStatusParams(ProjectScopedParams):
    """agent/status — query current agent status."""


class AgentListSessionsParams(ClientScopedParams):
    """agent/list_sessions — list all sessions for this client."""


class AgentResetParams(ProjectScopedParams):
    """agent/reset — reset the agent session state."""


class AgentClearParams(ProjectScopedParams):
    """agent/clear — clear the agent chat history."""


class AgentAddFileParams(ProjectScopedParams):
    """agent/add_file — add a file to the editable context."""

    path: str


class AgentDropFileParams(ProjectScopedParams):
    """agent/drop_file — remove a file from the editable context."""

    path: str


class AgentListFilesParams(ProjectScopedParams):
    """agent/list_files — list editable and read-only context files."""


class AgentReadOnlyParams(ProjectScopedParams):
    """agent/read_only — toggle read-only status of a context file."""

    path: str
    enabled: bool


class AgentRepoMapParams(ProjectScopedParams):
    """agent/repo_map — request a repository map from the agent."""


class AgentRunParams(ProjectScopedParams):
    """agent/run — run an arbitrary shell command inside the session."""

    command: str


class AgentTestParams(ProjectScopedParams):
    """agent/test — run the project test suite via the agent."""


class AgentLintParams(ProjectScopedParams):
    """agent/lint — run the project linter via the agent."""


# ---------------------------------------------------------------------------
# config/* methods
# ---------------------------------------------------------------------------

class ConfigSetKeyParams(ClientScopedParams):
    """config/set_key — store an API key (field typed as SecretStr)."""

    provider: str
    key: SecretStr  # Never exposed in model_dump() or validation errors


class ConfigListProvidersParams(ClientScopedParams):
    """config/list_providers — list known providers and availability."""


class ConfigListKeysParams(ClientScopedParams):
    """config/list_keys — list stored key slots (masked labels only)."""


class ConfigDeleteKeyParams(ClientScopedParams):
    """config/delete_key — delete a key slot by provider and index."""

    provider: str
    key_index: int
