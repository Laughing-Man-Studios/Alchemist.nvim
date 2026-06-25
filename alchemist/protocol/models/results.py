"""
Method result models for common successful JSON-RPC responses.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# client/initialize
# ---------------------------------------------------------------------------

class ClientInitializeResult(BaseModel):
    daemon_version: str
    protocol_version: str
    aider_version: str
    status: str


# ---------------------------------------------------------------------------
# daemon/version
# ---------------------------------------------------------------------------

class DaemonVersionResult(BaseModel):
    daemon_version: str
    protocol_version: str
    aider_version: Optional[str] = None


# ---------------------------------------------------------------------------
# daemon/health
# ---------------------------------------------------------------------------

class DaemonHealthResult(BaseModel):
    status: str
    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# agent/submit_prompt
# ---------------------------------------------------------------------------

AgentSubmitStatus = Literal["accepted", "queued", "running"]


class AgentSubmitPromptResult(BaseModel):
    status: AgentSubmitStatus
    job_id: Optional[str] = None


# ---------------------------------------------------------------------------
# agent/cancel
# ---------------------------------------------------------------------------

class AgentCancelResult(BaseModel):
    cancelled: bool
    state: str


# ---------------------------------------------------------------------------
# agent/status
# ---------------------------------------------------------------------------

class AgentStatusResult(BaseModel):
    status: str
    active_job: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# agent/list_files
# ---------------------------------------------------------------------------

class AgentListFilesResult(BaseModel):
    editable: List[str]
    read_only: List[str]


# ---------------------------------------------------------------------------
# config/list_providers
# ---------------------------------------------------------------------------

class ProviderInfo(BaseModel):
    name: str
    available: bool
    model_config = {"extra": "allow"}


class ConfigListProvidersResult(BaseModel):
    providers: List[ProviderInfo]


# ---------------------------------------------------------------------------
# config/list_keys  — masked labels only, never raw key material
# ---------------------------------------------------------------------------

class MaskedKeyInfo(BaseModel):
    provider: str
    key_index: int
    label: str      # e.g. "sk-...abc" — last 4 chars only


class ConfigListKeysResult(BaseModel):
    keys: List[MaskedKeyInfo]
