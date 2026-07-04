"""
NDJSON framing layer for the Alchemist protocol.

NdjsonReader — reads newline-delimited JSON frames from an asyncio stream.
NdjsonWriter — writes newline-delimited JSON frames to an asyncio stream.

Frame contract
--------------
- One JSON object per line, terminated by exactly one ``\\n`` byte.
- Maximum frame size: 16 MiB.  Oversized frames raise FrameError with
  AlchemistErrorCode.FRAME_TOO_LARGE.
- Empty lines are silently ignored.
- Batch (array) frames are rejected with INVALID_REQUEST.
- Invalid UTF-8 or malformed JSON raises FrameError with PARSE_ERROR.
"""
from __future__ import annotations

import json
from typing import Any

from alchemist.protocol.errors import (
    AlchemistErrorCode,
    INVALID_REQUEST,
    PARSE_ERROR,
    make_alchemist_error,
)

MAX_FRAME_SIZE: int = 16 * 1024 * 1024  # 16 MiB


class FrameError(Exception):
    """Raised for framing-level protocol errors.

    Attributes
    ----------
    code:    JSON-RPC error code integer.
    message: Human-readable description.
    data:    Optional structured error data dict.
    """

    """Initialize a new error instance with a status code, message, and optional metadata.

    Args:
        code: The error status code.
        message: A descriptive error message.
        data: Optional additional information associated with the error.
    """
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class NdjsonReader:
    """Read newline-delimited JSON frames from an asyncio-compatible stream.

    The stream object must implement ``async read(n) -> bytes``.
    """

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._buf = bytearray()

    """Read and return the next complete JSON-RPC frame as a plain dict.

    Continuously reads from the underlying stream into a buffer until a
    complete frame is parsed. 
    """
    async def read_frame(self) -> dict:
        """Read and return the next complete JSON-RPC frame as a plain dict.

        Raises
        ------
        FrameError   on protocol violations (too large, bad encoding, etc.)
        EOFError     when the underlying stream is closed.
        """
        while True:
            result = self._try_parse()
            if result is not None:
                return result
            chunk = await self._stream.read(65536)
            if not chunk:
                raise EOFError("Stream closed before a complete frame was received")
            self._buf.extend(chunk)

    def feed(self, data: bytes) -> list[dict]:
        """Feed raw bytes and return all complete frames parsed so far.

        Useful in tests that want to drive the reader without an async stream.
        """
        self._buf.extend(data)
        frames: list[dict] = []
        while True:
            result = self._try_parse()
            if result is None:
                break
            frames.append(result)
        return frames

    """
    Attempts to extract and parse a single JSON-RPC frame from the internal buffer.

    This method looks for a newline delimiter to identify a complete frame. It handles
    size validation to prevent memory exhaustion, skips empty lines, performs UTF-8
    decoding, and validates that the resulting JSON is a non-batch dictionary object.

    Returns:
        dict: The parsed JSON object if successful.
        None: If no complete frame is available in the buffer.

    Raises:
        FrameError: If the frame exceeds the maximum size, contains invalid UTF-8,
                    contains invalid JSON, or violates JSON-RPC structure requirements.
    """
    def _try_parse(self) -> dict | None:
        """Try to extract one frame from the buffer.  Returns None if incomplete."""
        newline_pos = self._buf.find(b"\n")
        if newline_pos == -1:
            # No complete frame yet — but check if the accumulating data is
            # already over the limit so we can fail fast.
            if len(self._buf) > MAX_FRAME_SIZE:
                self._buf.clear()
                raise FrameError(
                    int(AlchemistErrorCode.FRAME_TOO_LARGE),
                    "IPC frame exceeded 16 MiB limit",
                    make_alchemist_error(AlchemistErrorCode.FRAME_TOO_LARGE)["data"],
                )
            return None

        raw_frame = bytes(self._buf[:newline_pos])
        del self._buf[: newline_pos + 1]

        # Skip empty lines silently.
        if not raw_frame.strip():
            return self._try_parse()  # look for the next frame immediately

        # Per-frame size check (bytes before newline).
        if len(raw_frame) > MAX_FRAME_SIZE:
            raise FrameError(
                int(AlchemistErrorCode.FRAME_TOO_LARGE),
                "IPC frame exceeded 16 MiB limit",
                make_alchemist_error(AlchemistErrorCode.FRAME_TOO_LARGE)["data"],
            )

        # UTF-8 decode.
        try:
            text = raw_frame.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FrameError(PARSE_ERROR, f"Invalid UTF-8 in frame: {exc}") from exc

        # JSON parse.
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FrameError(PARSE_ERROR, f"Invalid JSON: {exc}") from exc

        # Reject batch arrays.
        if isinstance(obj, list):
            raise FrameError(INVALID_REQUEST, "Batch requests are not supported")

        if not isinstance(obj, dict):
            raise FrameError(PARSE_ERROR, "JSON-RPC frame must be a JSON object")

        return obj


class NdjsonWriter:
    """Write newline-delimited JSON frames to an asyncio-compatible stream.

    The stream object must implement ``write(data: bytes)`` and
    ``async drain() -> None``.
    """

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    """Serializes a dictionary to a UTF-8 encoded JSON string, appends a newline, and writes it to the stream, awaiting the drain operation to ensure the data is sent."""
    async def write_frame(self, obj: dict) -> None:
        """Serialize *obj* as UTF-8 JSON and write it as a newline-terminated frame."""
        payload = json.dumps(obj, ensure_ascii=False) + "\n"
        self._stream.write(payload.encode("utf-8"))
        await self._stream.drain()
