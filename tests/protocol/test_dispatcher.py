"""
Unit tests for the Dispatcher class in the alchemist protocol.

This module contains test suites for validating the core dispatching logic, including:
- JSON-RPC request handling (valid requests, unknown methods, invalid parameters, and internal errors).
- JSON-RPC notification handling (ensuring notifications return None and exceptions in handlers do not propagate).
- Validation of JSON-RPC structure and compliance.
"""
from __future__ import annotations

import uuid
import pytest

from alchemist.protocol.dispatcher import Dispatcher
from alchemist.protocol.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
)
from alchemist.protocol.models.client_to_daemon import ClientInitializeParams
from alchemist.protocol.models.results import ClientInitializeResult
from alchemist.protocol.registry import MethodEntry, MethodRegistry

CLIENT_ID = str(uuid.uuid4())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry_with(**handlers) -> MethodRegistry:
    """Build a minimal registry with custom handlers."""
    from alchemist.protocol.models.client_to_daemon import DaemonVersionParams
    from alchemist.protocol.models.results import DaemonVersionResult

    registry = MethodRegistry()

    for method, (params_model, result_model, handler) in handlers.items():
        registry.register(
            MethodEntry(
                method=method,
                params_model=params_model,
                result_model=result_model,
                handler=handler,
                direction="client_to_daemon",
            )
        )
    return registry


def _req(method: str, params: dict | None = None, id_: str = "req-1") -> dict:
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}


def _note(method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "method": method, "params": params or {}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDispatcherRequests:
    async def test_valid_request_dispatches_to_handler(self):
        async def my_handler(params: ClientInitializeParams):
            return ClientInitializeResult(
                daemon_version="0.1",
                protocol_version="1",
                aider_version="1.0",
                status="ok",
            )

        registry = _make_registry_with(
            **{
                "client/initialize": (
                    ClientInitializeParams,
                    ClientInitializeResult,
                    my_handler,
                )
            }
        )
        dispatcher = Dispatcher(registry=registry)
        response = await dispatcher.dispatch(
            _req(
                "client/initialize",
                {
                    "client_id": CLIENT_ID,
                    "cwd": "/proj",
                    "nvim_pid": 999,
                    "protocol_version": "1.0",
                },
            )
        )
        assert response is not None
        assert response["result"]["status"] == "ok"
        assert "error" not in response

    async def test_unknown_method_returns_method_not_found(self):
        dispatcher = Dispatcher()
        resp = await dispatcher.dispatch(_req("nonexistent/method"))
        assert resp["error"]["code"] == METHOD_NOT_FOUND

    async def test_invalid_params_returns_invalid_params(self):
        dispatcher = Dispatcher()
        # client/initialize missing required fields
        resp = await dispatcher.dispatch(_req("client/initialize", {}))
        assert resp["error"]["code"] == INVALID_PARAMS

    async def test_handler_exception_returns_internal_error(self):
        async def bad_handler(params):
            raise RuntimeError("boom")

        registry = _make_registry_with(
            **{
                "client/initialize": (
                    ClientInitializeParams,
                    ClientInitializeResult,
                    bad_handler,
                )
            }
        )
        dispatcher = Dispatcher(registry=registry)
        resp = await dispatcher.dispatch(
            _req(
                "client/initialize",
                {
                    "client_id": CLIENT_ID,
                    "cwd": "/",
                    "nvim_pid": 1,
                    "protocol_version": "1",
                },
            )
        )
        assert resp["error"]["code"] == INTERNAL_ERROR

    async def test_batch_array_returns_invalid_request(self):
        dispatcher = Dispatcher()
        resp = await dispatcher.dispatch([{"jsonrpc": "2.0"}])
        assert resp["error"]["code"] == INVALID_REQUEST

    async def test_bad_jsonrpc_field_returns_invalid_request(self):
        dispatcher = Dispatcher()
        resp = await dispatcher.dispatch({"jsonrpc": "1.0", "id": "1", "method": "x"})
        assert resp["error"]["code"] == INVALID_REQUEST


class TestDispatcherNotifications:
    async def test_notification_returns_none(self):
        called = []

        def handler(params):
            called.append(params)

        registry = MethodRegistry()
        from alchemist.protocol.models.daemon_to_client import UiClearPromptParams
        registry.register(
            MethodEntry(
                method="ui/clear_prompt",
                params_model=UiClearPromptParams,
                result_model=None,
                handler=handler,
                direction="daemon_to_client",
            )
        )
        dispatcher = Dispatcher(registry=registry)
        result = await dispatcher.dispatch(_note("ui/clear_prompt"))
        assert result is None
        assert len(called) == 1

    async def test_notification_handler_exception_does_not_propagate(self):
        def bad_handler(params):
            raise RuntimeError("should not propagate")

        registry = MethodRegistry()
        from alchemist.protocol.models.daemon_to_client import UiClearPromptParams
        registry.register(
            MethodEntry(
                method="ui/clear_prompt",
                params_model=UiClearPromptParams,
                result_model=None,
                handler=bad_handler,
                direction="daemon_to_client",
            )
        )
        dispatcher = Dispatcher(registry=registry)
        result = await dispatcher.dispatch(_note("ui/clear_prompt"))
        assert result is None  # no exception propagated
