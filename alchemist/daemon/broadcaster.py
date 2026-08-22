"""Broadcaster for sending JSON-RPC notifications to connected clients."""

import asyncio
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class Broadcaster:
    """Sends notifications to specific clients or broadcasts to all."""
    
    def __init__(self):
        # Maps client_id -> asyncio.StreamWriter
        self._clients: Dict[str, asyncio.StreamWriter] = {}

    def register_client(self, client_id: str, writer: asyncio.StreamWriter) -> None:
        """Register a client connection for notifications."""
        self._clients[client_id] = writer

    def unregister_client(self, client_id: str) -> None:
        """Remove a client connection."""
        self._clients.pop(client_id, None)

    def _send_payload(self, writer: asyncio.StreamWriter, payload: dict) -> None:
        """Send a payload asynchronously without blocking."""
        try:
            data = json.dumps(payload).encode('utf-8')
            if b'\n' in data:
                data = data.replace(b'\n', b'\\n')
            writer.write(data + b'\n')
            # Use a fire-and-forget task to drain so we don't block
            asyncio.create_task(self._safe_drain(writer))
        except Exception as e:
            logger.error(f"Failed to write broadcast payload: {e}")

    async def _safe_drain(self, writer: asyncio.StreamWriter) -> None:
        """Drain the writer safely, ignoring errors if connection is closed."""
        try:
            await writer.drain()
        except ConnectionError:
            pass
        except Exception as e:
            logger.debug(f"Error draining writer: {e}")

    def notify_client(self, client_id: str, method: str, params: dict | None = None) -> None:
        """Send a notification to a specific client."""
        writer = self._clients.get(client_id)
        if not writer:
            logger.debug(f"Cannot notify client {client_id}: not found.")
            return

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params is not None:
            payload["params"] = params

        self._send_payload(writer, payload)

    def broadcast(self, method: str, params: dict | None = None) -> None:
        """Send a notification to all connected clients."""
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params is not None:
            payload["params"] = params

        for writer in self._clients.values():
            self._send_payload(writer, payload)
