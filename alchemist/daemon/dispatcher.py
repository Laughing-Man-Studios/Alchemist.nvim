"""JSON-RPC 2.0 dispatcher and method registry."""

import asyncio
import logging
import uuid
from typing import Any, Callable, Coroutine, Dict

from alchemist.errors import AlchemistError, DaemonVersionMismatchError, NotImplementedErrorResponse
from alchemist.daemon.constants import DAEMON_VERSION, PROTOCOL_VERSION, AIDER_VERSION

logger = logging.getLogger(__name__)

HandlerType = Callable[[Dict[str, Any]], Coroutine[Any, Any, Any]]

class MethodRegistry:
    """Registry mapping RPC method names to async handlers."""
    def __init__(self):
        self._handlers: Dict[str, HandlerType] = {}

    def register(self, method: str, handler: HandlerType) -> None:
        self._handlers[method] = handler

    def get(self, method: str) -> HandlerType | None:
        return self._handlers.get(method)

class RpcDispatcher:
    """Dispatches JSON-RPC requests, handling errors and responses."""
    def __init__(self, registry: MethodRegistry):
        self.registry = registry

    async def dispatch(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Process an incoming RPC message and return an optional response."""
        req_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", {})

        if not method:
            if req_id is not None:
                return self._make_error(req_id, -32600, "Invalid Request", "Missing 'method' field")
            return None

        handler = self.registry.get(method)
        if not handler:
            logger.warning(f"Method not found: {method}")
            if req_id is not None:
                return self._make_error(req_id, -32601, "Method not found", f"Method '{method}' is not registered.")
            return None

        try:
            result = await handler(params)
            
            # Notifications do not require a response
            if req_id is None:
                return None
                
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result
            }
            
        except AlchemistError as e:
            logger.debug(f"Handled AlchemistError for {method}: {e.code}")
            if req_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32000,
                        "message": e.message,
                        "data": e.to_dict()
                    }
                }
            return None
        except Exception as e:
            logger.error(f"Unhandled exception in method {method}: {e}", exc_info=True)
            if req_id is not None:
                # Never leak tracebacks in production
                return self._make_error(req_id, -32603, "Internal error", "An unexpected internal error occurred.")
            return None

    def _make_error(self, req_id: Any, code: int, message: str, hint: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
                "data": {
                    "hint": hint
                }
            }
        }


def build_default_registry(lifecycle, socket_path) -> MethodRegistry:
    """Build a method registry populated with stub handlers for Phase 2."""
    registry = MethodRegistry()
    
    async def handle_client_initialize(params: dict) -> dict:
        client_proto = params.get("protocol_version")
        if client_proto != PROTOCOL_VERSION:
            raise DaemonVersionMismatchError(
                f"Client protocol version {client_proto} doesn't match daemon protocol version {PROTOCOL_VERSION}."
            )
        return {
            "daemon_version": DAEMON_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "aider_version": AIDER_VERSION,
            "status": "ready"
        }
        
    async def handle_daemon_health(params: dict) -> dict:
        return {
            "liveness": "ok",
            "socket_path": str(socket_path),
            "active_clients": lifecycle.active_clients,
            # We stub out the keys_configured and uptime for Phase 2
            "keys_configured": False, 
            "uptime_seconds": 0 
        }
        
    async def handle_daemon_version(params: dict) -> dict:
        return {
            "daemon_version": DAEMON_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "aider_version": AIDER_VERSION
        }

    async def handle_not_implemented(params: dict) -> dict:
        raise NotImplementedErrorResponse("Method not yet implemented")

    registry.register("client/initialize", handle_client_initialize)
    registry.register("daemon/health", handle_daemon_health)
    registry.register("daemon/version", handle_daemon_version)

    # Stubs
    stubs = [
        "agent/submit_prompt", "agent/cancel", "agent/status", "agent/list_sessions",
        "agent/reset", "agent/clear", "agent/add_file", "agent/drop_file", "agent/list_files",
        "agent/read_only", "agent/repo_map", "agent/run", "agent/test", "agent/lint",
        "config/set_key", "config/list_providers", "config/list_keys", "config/delete_key"
    ]
    for method in stubs:
        registry.register(method, handle_not_implemented)
        
    return registry
