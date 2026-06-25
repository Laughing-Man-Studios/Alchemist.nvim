"""
Headless fake client/server lifecycle test.

Simulates the full 8-step exchange from the implementation plan using
in-memory asyncio queues — no sockets, no Aider, no NeoVim required.

Steps:
  1. client/initialize
  2. initialize success response
  3. agent/submit_prompt
  4. ui/status_update  (notification from server)
  5. agent/stream_delta (notification from server)
  6. server/request_confirmation (server-initiated request)
  7. client confirmation response
  8. ui/diff_ready (notification from server)
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest

from alchemist.protocol.correlation import CorrelationTracker
from alchemist.protocol.dispatcher import Dispatcher
from alchemist.protocol.ids import make_client_request_id, make_server_request_id
from alchemist.protocol.models.client_to_daemon import (
    AgentSubmitPromptParams,
    ClientInitializeParams,
)
from alchemist.protocol.models.results import (
    AgentSubmitPromptResult,
    ClientInitializeResult,
)
from alchemist.protocol.registry import MethodEntry, MethodRegistry


CLIENT_ID = str(uuid.uuid4())
SESSION_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _QueuePair:
    """Two queues that act as a bidirectional pipe between client and server."""

    def __init__(self) -> None:
        self.client_to_server: asyncio.Queue = asyncio.Queue()
        self.server_to_client: asyncio.Queue = asyncio.Queue()


async def _server_loop(qp: _QueuePair, events: list[str]) -> None:
    """Minimal fake server: handles initialize, submit_prompt, then pushes notifications."""

    # Step 1 — receive client/initialize
    msg: dict = await asyncio.wait_for(qp.client_to_server.get(), timeout=2.0)
    assert msg["method"] == "client/initialize"
    events.append("server_got_initialize")
    req_id = msg["id"]

    # Step 2 — send initialize success response
    await qp.server_to_client.put({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "daemon_version": "0.1",
            "protocol_version": "1.0",
            "aider_version": "1.0",
            "status": "ok",
        },
    })
    events.append("server_sent_init_response")

    # Step 3 — receive agent/submit_prompt
    msg = await asyncio.wait_for(qp.client_to_server.get(), timeout=2.0)
    assert msg["method"] == "agent/submit_prompt"
    events.append("server_got_submit_prompt")
    prompt_req_id = msg["id"]

    # Step 4 — send ui/status_update notification
    await qp.server_to_client.put({
        "jsonrpc": "2.0",
        "method": "ui/status_update",
        "params": {
            "client_id": CLIENT_ID,
            "session_id": SESSION_ID,
            "project_id": PROJECT_ID,
            "status": "running",
            "model": "gpt-4o",
            "provider": "openai",
            "key_index": 0,
            "phase": "thinking",
        },
    })
    events.append("server_sent_status_update")

    # Step 5 — send agent/stream_delta notification
    await qp.server_to_client.put({
        "jsonrpc": "2.0",
        "method": "agent/stream_delta",
        "params": {
            "client_id": CLIENT_ID,
            "session_id": SESSION_ID,
            "project_id": PROJECT_ID,
            "delta": "Here is the refactored code...",
        },
    })
    events.append("server_sent_stream_delta")

    # Step 6 — send server/request_confirmation (server-initiated request)
    srv_req_id = make_server_request_id("confirm-1")
    await qp.server_to_client.put({
        "jsonrpc": "2.0",
        "id": srv_req_id,
        "method": "server/request_confirmation",
        "params": {
            "client_id": CLIENT_ID,
            "session_id": SESSION_ID,
            "project_id": PROJECT_ID,
            "prompt_type": "boolean",
            "message": "Apply these changes?",
        },
    })
    events.append("server_sent_confirmation_request")

    # Step 7 — receive client confirmation response
    confirmation: dict = await asyncio.wait_for(qp.client_to_server.get(), timeout=2.0)
    assert confirmation["id"] == srv_req_id
    assert confirmation["result"]["confirmed"] is True
    events.append("server_got_confirmation_response")

    # Step 8 — send ui/diff_ready notification
    await qp.server_to_client.put({
        "jsonrpc": "2.0",
        "method": "ui/diff_ready",
        "params": {
            "client_id": CLIENT_ID,
            "session_id": SESSION_ID,
            "project_id": PROJECT_ID,
            "base_hashes": {"main.py": "abc123"},
            "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-x=1\n+x=2\n",
            "files_changed": ["main.py"],
        },
    })
    events.append("server_sent_diff_ready")

    # Also send the submit_prompt result
    await qp.server_to_client.put({
        "jsonrpc": "2.0",
        "id": prompt_req_id,
        "result": {"status": "accepted", "job_id": "job-1"},
    })


async def _client_loop(qp: _QueuePair, events: list[str]) -> None:
    """Minimal fake client: drives the 8-step lifecycle."""
    tracker = CorrelationTracker()

    # Step 1 — send client/initialize
    init_id = make_client_request_id()
    init_fut = tracker.add_pending(init_id)
    await qp.client_to_server.put({
        "jsonrpc": "2.0",
        "id": init_id,
        "method": "client/initialize",
        "params": {
            "client_id": CLIENT_ID,
            "cwd": "/proj",
            "nvim_pid": 42,
            "protocol_version": "1.0",
        },
    })
    events.append("client_sent_initialize")

    # Step 2 — receive and correlate initialize response
    msg = await asyncio.wait_for(qp.server_to_client.get(), timeout=2.0)
    tracker.resolve(msg)
    init_result = await asyncio.wait_for(init_fut, timeout=1.0)
    assert init_result["status"] == "ok"
    events.append("client_got_init_response")

    # Step 3 — send agent/submit_prompt
    prompt_id = make_client_request_id()
    prompt_fut = tracker.add_pending(prompt_id)
    await qp.client_to_server.put({
        "jsonrpc": "2.0",
        "id": prompt_id,
        "method": "agent/submit_prompt",
        "params": {
            "client_id": CLIENT_ID,
            "session_id": SESSION_ID,
            "project_id": PROJECT_ID,
            "project_path": "/proj",
            "mode": "code",
            "prompt": "Refactor x=1 to x=2",
        },
    })
    events.append("client_sent_submit_prompt")

    # Steps 4-6 — drain server notifications until we see the confirmation request
    srv_req_id = None
    while srv_req_id is None:
        msg = await asyncio.wait_for(qp.server_to_client.get(), timeout=2.0)
        if "method" in msg:
            if msg["method"] == "ui/status_update":
                events.append("client_got_status_update")
            elif msg["method"] == "agent/stream_delta":
                events.append("client_got_stream_delta")
            elif msg["method"] == "server/request_confirmation":
                srv_req_id = msg["id"]
                events.append("client_got_confirmation_request")
        elif "result" in msg and msg.get("id") == prompt_id:
            tracker.resolve(msg)

    # Step 7 — send confirmation response
    await qp.client_to_server.put({
        "jsonrpc": "2.0",
        "id": srv_req_id,
        "result": {"confirmed": True, "value": None},
    })
    events.append("client_sent_confirmation_response")

    # Step 8 — receive ui/diff_ready (plus possible prompt result)
    received_diff = False
    while not received_diff:
        msg = await asyncio.wait_for(qp.server_to_client.get(), timeout=2.0)
        if "method" in msg and msg["method"] == "ui/diff_ready":
            received_diff = True
            events.append("client_got_diff_ready")
        elif "result" in msg:
            tracker.resolve(msg)


async def test_full_lifecycle_exchange():
    """All 8 steps complete without error."""
    qp = _QueuePair()
    events: list[str] = []

    await asyncio.gather(
        _server_loop(qp, events),
        _client_loop(qp, events),
    )

    # Verify all 8 expected events occurred on both sides
    expected = [
        "client_sent_initialize",
        "server_got_initialize",
        "server_sent_init_response",
        "client_got_init_response",
        "client_sent_submit_prompt",
        "server_got_submit_prompt",
        "server_sent_status_update",
        "server_sent_stream_delta",
        "server_sent_confirmation_request",
        "client_got_status_update",
        "client_got_stream_delta",
        "client_got_confirmation_request",
        "client_sent_confirmation_response",
        "server_got_confirmation_response",
        "server_sent_diff_ready",
        "client_got_diff_ready",
    ]
    for event in expected:
        assert event in events, f"Missing event: {event!r}\nGot: {events}"
