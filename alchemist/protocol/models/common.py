"""
Shared parameter base models for context scoping in the Alchemist protocol.

Layered hierarchy:
  ClientScopedParams   ->  client_id
  SessionScopedParams  ->  client_id + session_id
  ProjectScopedParams  ->  client_id + session_id + project_id

All IDs are validated as UUID strings.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ClientScopedParams(BaseModel):
    """Base for operations scoped to a single client connection."""

    client_id: UUID


class SessionScopedParams(ClientScopedParams):
    """Base for operations that additionally require a session ID."""

    session_id: UUID


class ProjectScopedParams(SessionScopedParams):
    """Base for operations that require client, session, and project IDs."""

    project_id: UUID
