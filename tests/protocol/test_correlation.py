"""
Tests for alchemist.protocol.correlation — CorrelationTracker.
"""
from __future__ import annotations

import asyncio
import pytest

from alchemist.protocol.correlation import CorrelationTracker, UnknownResponseIdError
from alchemist.protocol.ids import make_client_request_id, make_server_request_id


class TestCorrelationTracker:
    async def test_pending_request_resolved_by_matching_id(self):
        tracker = CorrelationTracker()
        req_id = make_client_request_id()
        fut = tracker.add_pending(req_id)

        response = {"jsonrpc": "2.0", "id": req_id, "result": {"status": "ok"}}
        tracker.resolve(response)

        result = await asyncio.wait_for(fut, timeout=1.0)
        assert result == {"status": "ok"}

    async def test_error_response_sets_exception_on_future(self):
        tracker = CorrelationTracker()
        req_id = make_client_request_id()
        fut = tracker.add_pending(req_id)

        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": "Method not found"},
        }
        tracker.resolve(response)

        with pytest.raises(RuntimeError, match="Method not found"):
            await asyncio.wait_for(fut, timeout=1.0)

    def test_unmatched_response_id_raises(self):
        tracker = CorrelationTracker()
        response = {"jsonrpc": "2.0", "id": "unknown-id", "result": {}}
        with pytest.raises(UnknownResponseIdError):
            tracker.resolve(response)

    async def test_expire_cancels_pending_future(self):
        tracker = CorrelationTracker()
        req_id = make_client_request_id()
        fut = tracker.add_pending(req_id)
        tracker.expire(req_id)

        assert fut.cancelled()
        assert req_id not in tracker.pending_ids()

    async def test_server_request_confirmation_roundtrip(self):
        tracker = CorrelationTracker()
        srv_id = make_server_request_id("prompt-1")
        fut = tracker.add_pending(srv_id)

        response = {"jsonrpc": "2.0", "id": srv_id, "result": {"confirmed": True}}
        tracker.resolve(response)

        result = await asyncio.wait_for(fut, timeout=1.0)
        assert result["confirmed"] is True

    def test_len_tracks_pending_count(self):
        tracker = CorrelationTracker()
        assert len(tracker) == 0
        id1 = make_client_request_id()
        id2 = make_client_request_id()
        tracker.add_pending(id1)
        tracker.add_pending(id2)
        assert len(tracker) == 2
        tracker.expire(id1)
        assert len(tracker) == 1
