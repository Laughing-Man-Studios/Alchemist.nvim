"""Aider IO adapter which relays output to one initiating client."""

import logging
import asyncio
from typing import Callable

from aider.io import InputOutput

logger = logging.getLogger(__name__)

class InterceptedIO(InputOutput):
    """Non-interactive Aider IO which marshals thread output to asyncio."""
    
    def __init__(self, session_id: str, client_id: str, project_id: str, loop: asyncio.AbstractEventLoop,
                 notify_cb: Callable[[str, str, dict], None], root: str):
        super().__init__(pretty=False, yes=True, input_history_file=None,
                         chat_history_file=None, llm_history_file=None,
                         root=root, fancy_input=False)
        self.session_id = session_id
        self.client_id = client_id
        self.project_id = project_id
        self.loop = loop
        self.notify_cb = notify_cb

    def _notify(self, method: str, payload: dict) -> None:
        self.loop.call_soon_threadsafe(self.notify_cb, self.client_id, method, payload)

    def write_stream(self, text: str) -> None:
        """Called when streaming model chunks arrive."""
        self._notify("agent/stream_delta", {
            "client_id": self.client_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "delta": str(text),
        })

    def assistant_output(self, message: str, pretty=None) -> None:
        if message:
            self.write_stream(message)

    def tool_output(self, *messages, **kwargs) -> None:
        """Called when a tool produces output."""
        text = " ".join(str(item) for item in messages)
        if text:
            self.write_stream(text)

    def get_input(self, prompt: str) -> str:
        """Intercepted raw input (stub)."""
        logger.warning("Aider requested interactive input; rejecting it in daemon mode.")
        return ""

    def confirm_ask(self, *args, **kwargs) -> bool:
        logger.warning("Aider requested confirmation; rejecting it in daemon mode.")
        return False
