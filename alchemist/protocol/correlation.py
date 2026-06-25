"""
Request/response correlation tracker for bidirectional JSON-RPC.

Tracks outbound requests and matches inbound responses.  Supports both
client-originated (UUID) and daemon-originated (srv_req_*) request IDs.

Usage
-----
    tracker = CorrelationTracker()
    future = tracker.add_pending(request_id)
    # ... send the request over the wire ...
    result = await asyncio.wait_for(future, timeout=30.0)

On the receive side:
    tracker.resolve(response_dict)  # matches id and resolves the future
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class UnknownResponseIdError(Exception):
    """Raised when a response ID does not match any pending request."""


class CorrelationTracker:
    """Track pending outbound requests and correlate inbound responses."""

    def __init__(self) -> None:
        self._pending: Dict[Any, asyncio.Future] = {}

    # ------------------------------------------------------------------
    # Adding pending requests
    # ------------------------------------------------------------------

    def add_pending(self, request_id: Any) -> asyncio.Future:
        """Register *request_id* as a pending request.

        Returns an asyncio.Future that will be resolved when the matching
        response arrives.  The caller is responsible for applying a timeout
        (e.g. via asyncio.wait_for).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        fut: asyncio.Future = loop.create_future()
        self._pending[request_id] = fut
        return fut

    # ------------------------------------------------------------------
    # Resolving inbound responses
    # ------------------------------------------------------------------

    def resolve(self, response: dict) -> None:
        """Match an inbound response to a pending request and resolve its future.

        The response dict must have an ``id`` key.

        Raises
        ------
        UnknownResponseIdError
            If no pending request matches the response's ``id``.
        """
        response_id = response.get("id")
        fut = self._pending.pop(response_id, None)
        if fut is None:
            raise UnknownResponseIdError(
                f"Received response for unknown request id: {response_id!r}"
            )
        if fut.done():
            log.warning("Future for id %r was already done (possible duplicate)", response_id)
            return
        if "error" in response:
            fut.set_exception(
                RuntimeError(
                    f"JSON-RPC error {response['error'].get('code')}: "
                    f"{response['error'].get('message')}"
                )
            )
        else:
            fut.set_result(response.get("result"))

    # ------------------------------------------------------------------
    # Timeout / cleanup
    # ------------------------------------------------------------------

    def expire(self, request_id: Any) -> None:
        """Cancel and remove the pending future for *request_id*, if present."""
        fut = self._pending.pop(request_id, None)
        if fut and not fut.done():
            fut.cancel()

    def pending_ids(self) -> list:
        return list(self._pending.keys())

    def __len__(self) -> int:
        return len(self._pending)
