"""
Tests for method-specific param models (client->daemon and daemon->client).
"""
from __future__ import annotations

import uuid
import pytest
from pydantic import ValidationError

from alchemist.protocol.models.client_to_daemon import (
    AgentSubmitPromptParams,
    BufferSnapshot,
    ClientInitializeParams,
    ConfigSetKeyParams,
    DaemonHealthParams,
    DaemonVersionParams,
)
from alchemist.protocol.models.daemon_to_client import (
    ConfirmationResult,
    ServerRequestConfirmationParams,
)

CLIENT_ID = str(uuid.uuid4())
SESSION_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())


class TestClientInitializeParams:
    def test_valid_without_session_or_project(self):
        p = ClientInitializeParams(
            client_id=CLIENT_ID,
            cwd="/home/user/proj",
            nvim_pid=1234,
            protocol_version="1.0",
        )
        assert str(p.client_id) == CLIENT_ID

    def test_missing_client_id_fails(self):
        with pytest.raises(ValidationError):
            ClientInitializeParams(cwd="/", nvim_pid=1, protocol_version="1.0")

    def test_invalid_uuid_client_id_fails(self):
        with pytest.raises(ValidationError):
            ClientInitializeParams(
                client_id="not-a-uuid",
                cwd="/",
                nvim_pid=1,
                protocol_version="1.0",
            )


class TestDaemonVersionAndHealth:
    def test_daemon_version_requires_client_id(self):
        with pytest.raises(ValidationError):
            DaemonVersionParams()

    def test_daemon_health_requires_client_id(self):
        with pytest.raises(ValidationError):
            DaemonHealthParams()

    def test_daemon_version_valid(self):
        p = DaemonVersionParams(client_id=CLIENT_ID)
        assert str(p.client_id) == CLIENT_ID


class TestAgentSubmitPromptParams:
    def _valid(self, **overrides):
        base = dict(
            client_id=CLIENT_ID,
            session_id=SESSION_ID,
            project_id=PROJECT_ID,
            project_path="/proj",
            mode="code",
            prompt="Refactor this",
        )
        base.update(overrides)
        return AgentSubmitPromptParams(**base)

    def test_valid_full(self):
        p = self._valid()
        assert p.mode == "code"

    def test_missing_client_id_fails(self):
        with pytest.raises(ValidationError):
            AgentSubmitPromptParams(
                session_id=SESSION_ID,
                project_id=PROJECT_ID,
                project_path="/",
                mode="ask",
                prompt="hi",
            )

    def test_missing_session_id_fails(self):
        with pytest.raises(ValidationError):
            AgentSubmitPromptParams(
                client_id=CLIENT_ID,
                project_id=PROJECT_ID,
                project_path="/",
                mode="ask",
                prompt="hi",
            )

    def test_missing_project_id_fails(self):
        with pytest.raises(ValidationError):
            AgentSubmitPromptParams(
                client_id=CLIENT_ID,
                session_id=SESSION_ID,
                project_path="/",
                mode="ask",
                prompt="hi",
            )

    def test_invalid_mode_fails(self):
        with pytest.raises(ValidationError):
            self._valid(mode="invalid_mode")

    def test_ask_mode_valid(self):
        p = self._valid(mode="ask")
        assert p.mode == "ask"

    def test_architect_mode_valid(self):
        p = self._valid(mode="architect")
        assert p.mode == "architect"


class TestBufferSnapshot:
    def test_valid_snapshot(self):
        s = BufferSnapshot(path="foo.py", content="x=1", sha256="abc123", modified=False)
        assert s.path == "foo.py"

    def test_empty_path_fails(self):
        with pytest.raises(ValidationError):
            BufferSnapshot(path="", content="", sha256="abc", modified=False)

    def test_empty_sha256_fails(self):
        with pytest.raises(ValidationError):
            BufferSnapshot(path="f.py", content="", sha256="", modified=False)


class TestServerRequestConfirmation:
    def test_valid_boolean_prompt(self):
        p = ServerRequestConfirmationParams(
            client_id=CLIENT_ID,
            session_id=SESSION_ID,
            project_id=PROJECT_ID,
            prompt_type="boolean",
            message="Continue?",
        )
        assert p.timeout_ms == 60_000

    def test_default_timeout(self):
        p = ServerRequestConfirmationParams(
            client_id=CLIENT_ID,
            session_id=SESSION_ID,
            project_id=PROJECT_ID,
            prompt_type="text",
            message="Name?",
        )
        assert p.timeout_ms == 60_000

    def test_invalid_prompt_type_fails(self):
        with pytest.raises(ValidationError):
            ServerRequestConfirmationParams(
                client_id=CLIENT_ID,
                session_id=SESSION_ID,
                project_id=PROJECT_ID,
                prompt_type="checkbox",
                message="?",
            )


class TestConfirmationResult:
    def test_confirmed_true(self):
        r = ConfirmationResult(confirmed=True, value="yes")
        assert r.confirmed is True

    def test_confirmed_false_no_value(self):
        r = ConfirmationResult(confirmed=False)
        assert r.value is None
