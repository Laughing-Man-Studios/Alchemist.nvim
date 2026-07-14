"""
File: tests/protocol/test_jsonrpc_envelopes.py

Detailed Summary:
This test file validates the JSON-RPC 2.0 envelope models and message classification
functionality in the alchemist.protocol.jsonrpc module. It contains comprehensive tests
for four main components:

1. JsonRpcRequest Model:
   - Tests valid request creation with required fields (jsonrpc, id, method)
   - Verifies optional params field handling (must be dict if present)
   - Validates rejection of:
     * Wrong JSON-RPC version (must be "2.0")
     * Missing required fields (jsonrpc, method)
     * Invalid params type (arrays are rejected)

2. JsonRpcNotification Model:
   - Tests valid notification creation (no id field)
   - Verifies params must be a dict if present
   - Confirms proper method field handling

3. JsonRpcSuccessResponse Model:
   - Tests valid success response creation with result field
   - Verifies proper id field handling

4. JsonRpcErrorResponse Model:
   - Tests valid error response creation with error object
   - Verifies null id is allowed in error responses
   - Confirms proper error code and message handling

5. classify_message Function:
   - Tests proper classification of all message types:
     * Requests (contain id and method)
     * Notifications (contain method, no id)
     * Success responses (contain id and result)
     * Error responses (contain id and error)
   - Validates error cases:
     * Batch arrays (rejected with ValueError)
     * Missing jsonrpc field
     * Wrong jsonrpc version
     * Non-dict input

The tests use Pydantic's model_validate for schema validation and pytest for
assertions and error case testing. All tests follow JSON-RPC 2.0 specification
requirements.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from alchemist.protocol.jsonrpc import (
    JsonRpcErrorResponse,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcSuccessResponse,
    classify_message,
)


class TestJsonRpcRequest:
    def test_valid_request(self):
        raw = {"jsonrpc": "2.0", "id": "abc", "method": "client/initialize", "params": {"client_id": "x"}}
        req = JsonRpcRequest.model_validate(raw)
        assert req.method == "client/initialize"
        assert req.id == "abc"

    def test_request_without_params(self):
        raw = {"jsonrpc": "2.0", "id": "1", "method": "daemon/health"}
        req = JsonRpcRequest.model_validate(raw)
        assert req.params is None

    def test_wrong_jsonrpc_version_rejected(self):
        with pytest.raises(ValidationError):
            JsonRpcRequest.model_validate({"jsonrpc": "1.0", "id": "1", "method": "x"})

    def test_missing_jsonrpc_rejected(self):
        with pytest.raises(ValidationError):
            JsonRpcRequest.model_validate({"id": "1", "method": "x"})

    def test_missing_method_rejected(self):
        with pytest.raises(ValidationError):
            JsonRpcRequest.model_validate({"jsonrpc": "2.0", "id": "1"})

    def test_params_array_rejected(self):
        with pytest.raises(ValidationError):
            JsonRpcRequest.model_validate(
                {"jsonrpc": "2.0", "id": "1", "method": "x", "params": [1, 2]}
            )


class TestJsonRpcNotification:
    def test_valid_notification(self):
        raw = {"jsonrpc": "2.0", "method": "ui/status_update", "params": {"status": "ok"}}
        note = JsonRpcNotification.model_validate(raw)
        assert note.method == "ui/status_update"

    def test_params_array_rejected(self):
        with pytest.raises(ValidationError):
            JsonRpcNotification.model_validate(
                {"jsonrpc": "2.0", "method": "x", "params": ["a"]}
            )


class TestJsonRpcSuccessResponse:
    def test_valid_success_response(self):
        raw = {"jsonrpc": "2.0", "id": "1", "result": {"status": "ok"}}
        resp = JsonRpcSuccessResponse.model_validate(raw)
        assert resp.result == {"status": "ok"}


class TestJsonRpcErrorResponse:
    def test_valid_error_response(self):
        raw = {
            "jsonrpc": "2.0",
            "id": "1",
            "error": {"code": -32601, "message": "Method not found"},
        }
        resp = JsonRpcErrorResponse.model_validate(raw)
        assert resp.error.code == -32601

    def test_error_response_null_id_allowed(self):
        raw = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error"},
        }
        resp = JsonRpcErrorResponse.model_validate(raw)
        assert resp.id is None


class TestClassifyMessage:
    def test_classifies_request(self):
        raw = {"jsonrpc": "2.0", "id": "1", "method": "daemon/version"}
        msg = classify_message(raw)
        assert isinstance(msg, JsonRpcRequest)

    def test_classifies_notification(self):
        raw = {"jsonrpc": "2.0", "method": "ui/clear_prompt"}
        msg = classify_message(raw)
        assert isinstance(msg, JsonRpcNotification)

    def test_classifies_success_response(self):
        raw = {"jsonrpc": "2.0", "id": "1", "result": {}}
        msg = classify_message(raw)
        assert isinstance(msg, JsonRpcSuccessResponse)

    def test_classifies_error_response(self):
        raw = {"jsonrpc": "2.0", "id": "1", "error": {"code": -32603, "message": "Err"}}
        msg = classify_message(raw)
        assert isinstance(msg, JsonRpcErrorResponse)

    def test_batch_array_raises(self):
        with pytest.raises(ValueError, match="[Bb]atch"):
            classify_message([{"jsonrpc": "2.0"}])

    def test_missing_jsonrpc_raises(self):
        with pytest.raises(ValueError):
            classify_message({"id": "1", "method": "x"})

    def test_wrong_jsonrpc_raises(self):
        with pytest.raises(ValueError):
            classify_message({"jsonrpc": "1.0", "id": "1", "method": "x"})

    def test_non_dict_raises(self):
        with pytest.raises(ValueError):
            classify_message("hello")
