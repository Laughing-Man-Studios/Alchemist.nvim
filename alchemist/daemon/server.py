"""Unix domain socket IPC server for the Alchemist daemon."""

import asyncio
import json
import logging
import os
import stat
from typing import Any, Callable, Coroutine
from .constants import MAX_FRAME_SIZE
from .lifecycle import LifecycleManager
from .paths import get_socket_path

logger = logging.getLogger(__name__)

class IpcServer:
    """Manages the Unix socket, client connections, and JSON-RPC framing."""
    def __init__(
        self, 
        lifecycle: LifecycleManager,
        dispatcher_callback: Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any] | None]],
        unregister_client: Callable[[str], None] | None = None,
    ):
        self.lifecycle = LifecycleManager
        self.lifecycle_instance = lifecycle
        self.dispatcher_callback = dispatcher_callback
        self.unregister_client = unregister_client
        self.socket_path = get_socket_path()
        self._server: asyncio.Server | None = None
        self._active_connections: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Start the Unix socket server."""
        # Clean up stale socket if necessary
        if self.socket_path.exists():
            try:
                # If we get here, we hold the lockfile, meaning any existing socket is stale
                self.socket_path.unlink()
            except OSError as e:
                logger.error(f"Failed to remove stale socket {self.socket_path}: {e}")

        # Start the server
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path)
        )
        
        # Enforce 0600 permissions
        os.chmod(self.socket_path, stat.S_IRUSR | stat.S_IWUSR)
        logger.info(f"IPC server listening on {self.socket_path}")

    async def stop(self) -> None:
        """Stop the server and close all client connections."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        
        # Cancel all active client handlers
        for task in self._active_connections:
            task.cancel()
            
        if self._active_connections:
            await asyncio.gather(*self._active_connections, return_exceptions=True)

        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle an individual client connection."""
        self.lifecycle_instance.client_connected()
        peer = writer.get_extra_info('peername') or "unknown"
        client_ids: set[str] = set()
        logger.debug(f"Client connected from {peer}")
        
        # Wrap the connection handling to manage the active connection set
        current_task = asyncio.current_task()
        if current_task:
            self._active_connections.add(current_task)
            current_task.add_done_callback(self._active_connections.discard)

        try:
            while not reader.at_eof():
                try:
                    # Read until newline
                    line = await reader.readuntil(b'\n')
                except asyncio.exceptions.LimitOverrunError:
                    # Frame too large
                    logger.warning("Rejecting oversized frame (FRAME_TOO_LARGE)")
                    error_resp = self._make_json_rpc_error(None, -32600, "FRAME_TOO_LARGE", "Frame exceeded 16 MiB")
                    writer.write(error_resp.encode('utf-8') + b'\n')
                    await writer.drain()
                    # We must consume the remaining data or drop the connection.
                    # Given stream corruption, dropping the connection is safer.
                    break
                except asyncio.exceptions.IncompleteReadError:
                    break

                # Enforce size
                if len(line) > MAX_FRAME_SIZE:
                    logger.warning("Rejecting oversized frame (FRAME_TOO_LARGE)")
                    error_resp = self._make_json_rpc_error(None, -32600, "FRAME_TOO_LARGE", "Frame exceeded 16 MiB")
                    writer.write(error_resp.encode('utf-8') + b'\n')
                    await writer.drain()
                    continue

                if not line.strip():
                    continue

                try:
                    payload = json.loads(line.decode('utf-8'))
                except json.JSONDecodeError as e:
                    logger.warning(f"Parse error: {e}")
                    error_resp = self._make_json_rpc_error(None, -32700, "Parse error", "Invalid JSON")
                    writer.write(error_resp.encode('utf-8') + b'\n')
                    await writer.drain()
                    continue

                # Dispatch
                try:
                    if payload.get("method") == "client/initialize":
                        client_id = payload.get("params", {}).get("client_id")
                        if client_id:
                            client_ids.add(str(client_id))
                    payload["_connection_writer"] = writer
                    response = await self.dispatcher_callback(payload)
                    if response is not None:
                        # Serialize and send response
                        resp_bytes = json.dumps(response).encode('utf-8')
                        if b'\n' in resp_bytes:
                            # Sanity check: response shouldn't have unescaped newlines
                            resp_bytes = resp_bytes.replace(b'\n', b'\\n')
                        writer.write(resp_bytes + b'\n')
                        await writer.drain()
                except Exception as e:
                    logger.error(f"Error in dispatcher: {e}", exc_info=True)
                    req_id = payload.get("id") if isinstance(payload, dict) else None
                    error_resp = self._make_json_rpc_error(req_id, -32603, "Internal error", str(e))
                    writer.write(error_resp.encode('utf-8') + b'\n')
                    await writer.drain()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error handling client connection: {e}", exc_info=True)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            self.lifecycle_instance.client_disconnected()
            if self.unregister_client:
                for client_id in client_ids:
                    self.unregister_client(client_id)
            logger.debug(f"Client connection closed {peer}")

    def _make_json_rpc_error(self, req_id: Any, code: int, message: str, data: Any = None) -> str:
        """Create a raw JSON-RPC error payload (fallback for when dispatcher isn't reached)."""
        err = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message
            }
        }
        if data is not None:
            err["error"]["data"] = data
        return json.dumps(err)
