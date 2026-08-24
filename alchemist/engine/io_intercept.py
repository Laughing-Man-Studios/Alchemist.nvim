"""Intercepts IO from Aider to pipe it to the JSON-RPC Broadcaster."""

import logging
from typing import Callable

logger = logging.getLogger(__name__)

class InterceptedIO:
    """Stub IO interceptor mapping terminal output to RPC notifications."""
    
    def __init__(self, session_id: str, notify_cb: Callable[[str, dict], None]):
        self.session_id = session_id
        self.notify_cb = notify_cb

    def write_stream(self, text: str) -> None:
        """Called when streaming model chunks arrive."""
        self.notify_cb("agent/stream_delta", {
            "session_id": self.session_id,
            "text": text
        })

    def tool_output(self, text: str) -> None:
        """Called when a tool produces output."""
        # For Phase 2, we just treat it as generic output
        pass

    def get_input(self, prompt: str) -> str:
        """Intercepted raw input (stub)."""
        logger.warning("get_input called synchronously in InterceptedIO. This should be bridged.")
        return ""
