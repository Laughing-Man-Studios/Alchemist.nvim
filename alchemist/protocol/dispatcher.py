"""
JSON-RPC dispatcher for the Alchemist protocol.

The Dispatcher receives a raw decoded dict, validates it against the
registered method entry, calls the async handler, and returns a JSON-RPC
response dict (or None for notifications).

Error handling:
  - batch array         -> -32600 Invalid Request
  - bad jsonrpc field   -> -32600 Invalid Request
  - unknown method      -> -32601 Method not found
  - invalid params      -> -32602 Invalid params  (secrets redacted)
  - handler exception   -> -32603 Internal error  (message sanitised)
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

from pydantic import ValidationError

from alchemist.protocol.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    make_internal_error,
    make_invalid_params,
    make_invalid_request,
    make_method_not_found,
)
from alchemist.protocol.ids import make_client_request_id
from alchemist.protocol.jsonrpc import (
    JsonRpcErrorObject,
    JsonRpcErrorResponse,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcSuccessResponse,
    classify_message,
)
from alchemist.protocol.registry import MethodRegistry, build_default_registry

log = logging.getLogger(__name__)

_JSONRPC_VERSION = "2.0"


def _redact_validation_error(exc: ValidationError) -> str:
    """Return a safe string representation of a ValidationError.

    Pydantic includes field values in error messages, which could expose
    secrets.  We strip the 'input' values from each error dict.
    """
    safe_errors = []
    for err in exc.errors():
        safe_errors.append(
            {
                "type": err.get("type"),
                "loc": err.get("loc"),
                "msg": err.get("msg"),
                # Deliberately omit "input" and "url"
            }
        )
    return str(safe_errors)


def _build_error_response(
    id_: Any,
    code: int,
    message: str,
    data: Any = None,
) -> dict:
    return {
        "jsonrpc": _JSONRPC_VERSION,
        "id": id_,
        "error": {"code": code, "message": message, "data": data},
    }


class Dispatcher:
    """Route incoming JSON-RPC messages to async handlers.

    Parameters
    ----------
    registry:
        A populated MethodRegistry.  Defaults to the standard V1 registry.
    """

    def __init__(self, registry: Optional[MethodRegistry] = None) -> None:
        self._registry = registry or build_default_registry()

    async def dispatch(self, raw: Any) -> Optional[dict]:
        """Process a raw decoded frame dict.

        Returns a JSON-RPC response dict, or *None* for notifications.
        """
        # Structural classification
        try:
            envelope = classify_message(raw)
        except ValueError as exc:
            message = str(exc)
            if "batch" in message.lower():
                err = make_invalid_request("Batch requests are not supported")
            elif "jsonrpc" in message.lower():
                err = make_invalid_request(message)
            else:
                err = make_invalid_request(message)
            return _build_error_response(None, err["code"], err["message"])

        # --- Notification (no response)
        if isinstance(envelope, JsonRpcNotification):
            await self._dispatch_notification(envelope)
            return None

        # --- Request (response required)
        if isinstance(envelope, JsonRpcRequest):
            return await self._dispatch_request(envelope)

        # We received a response frame — not expected in server role.
        log.warning("Dispatcher received a response frame unexpectedly: %r", raw)
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _dispatch_request(self, req: JsonRpcRequest) -> dict:
        entry = self._registry.lookup(req.method)
        if entry is None:
            err = make_method_not_found(req.method)
            return _build_error_response(req.id, err["code"], err["message"])

        # Validate params
        try:
            params = entry.params_model.model_validate(req.params or {})
        except ValidationError as exc:
            safe_msg = _redact_validation_error(exc)
            log.debug("Params validation failed for %s: %s", req.method, safe_msg)
            err = make_invalid_params(f"Invalid params for {req.method}")
            return _build_error_response(req.id, err["code"], err["message"])

        # Call handler
        try:
            if inspect.iscoroutinefunction(entry.handler):
                result = await entry.handler(params)
            else:
                result = entry.handler(params)
        except Exception as exc:  # noqa: BLE001
            log.exception("Handler for %s raised an exception", req.method)
            err = make_internal_error(f"Internal error handling {req.method}")
            return _build_error_response(req.id, err["code"], err["message"])

        # Serialize result
        if result is None:
            serialized = None
        elif entry.result_model is not None and isinstance(result, entry.result_model):
            serialized = result.model_dump()
        elif hasattr(result, "model_dump"):
            serialized = result.model_dump()
        else:
            serialized = result

        return {
            "jsonrpc": _JSONRPC_VERSION,
            "id": req.id,
            "result": serialized,
        }

    async def _dispatch_notification(self, note: JsonRpcNotification) -> None:
        entry = self._registry.lookup(note.method)
        if entry is None:
            log.warning("Received notification for unknown method: %s", note.method)
            return

        try:
            params = entry.params_model.model_validate(note.params or {})
        except ValidationError as exc:
            log.debug(
                "Notification params validation failed for %s: %s",
                note.method,
                _redact_validation_error(exc),
            )
            return

        try:
            if inspect.iscoroutinefunction(entry.handler):
                await entry.handler(params)
            else:
                entry.handler(params)
        except Exception:  # noqa: BLE001
            log.exception("Handler for notification %s raised an exception", note.method)
