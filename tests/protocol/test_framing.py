"""
Tests for alchemist.protocol.framing — NdjsonReader / NdjsonWriter.
"""
from __future__ import annotations

import asyncio
import json
import pytest

from alchemist.protocol.framing import (
    MAX_FRAME_SIZE,
    FrameError,
    NdjsonReader,
    NdjsonWriter,
)
from alchemist.protocol.errors import PARSE_ERROR, INVALID_REQUEST, AlchemistErrorCode


# ---------------------------------------------------------------------------
# Helpers — in-memory stream stubs
# ---------------------------------------------------------------------------

class _MemStream:
    """Minimal asyncio-compatible stream backed by a bytes queue."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self._written = bytearray()

    async def read(self, n: int) -> bytes:
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        return chunk

    def write(self, data: bytes) -> None:
        self._written.extend(data)

    async def drain(self) -> None:
        pass

    @property
    def written(self) -> bytes:
        return bytes(self._written)


def _reader(*chunks: bytes) -> NdjsonReader:
    return NdjsonReader(_MemStream(list(chunks)))


def _writer() -> tuple[NdjsonWriter, _MemStream]:
    stream = _MemStream([])
    return NdjsonWriter(stream), stream


# ---------------------------------------------------------------------------
# NdjsonReader tests
# ---------------------------------------------------------------------------

class TestNdjsonReaderFeed:
    """Use the synchronous feed() helper for simpler tests."""

    def test_complete_single_frame(self):
        reader = NdjsonReader(None)  # no stream needed for feed()
        data = b'{"jsonrpc":"2.0","method":"ping"}\n'
        frames = reader.feed(data)
        assert len(frames) == 1
        assert frames[0]["method"] == "ping"

    def test_multiple_frames_in_one_chunk(self):
        reader = NdjsonReader(None)
        chunk = b'{"jsonrpc":"2.0","id":"1","method":"a"}\n{"jsonrpc":"2.0","id":"2","method":"b"}\n'
        frames = reader.feed(chunk)
        assert len(frames) == 2
        assert frames[0]["method"] == "a"
        assert frames[1]["method"] == "b"

    def test_fragmented_frame(self):
        reader = NdjsonReader(None)
        part1 = b'{"jsonrpc"'
        part2 = b':"2.0","method":"frag"}\n'
        frames = reader.feed(part1)
        assert frames == []
        frames = reader.feed(part2)
        assert len(frames) == 1
        assert frames[0]["method"] == "frag"

    def test_empty_lines_ignored(self):
        reader = NdjsonReader(None)
        data = b'\n\n{"jsonrpc":"2.0","method":"ok"}\n\n'
        frames = reader.feed(data)
        assert len(frames) == 1

    def test_escaped_newlines_inside_string(self):
        obj = {"jsonrpc": "2.0", "method": "m", "params": {"text": "line1\nline2"}}
        serialized = json.dumps(obj).encode() + b"\n"
        reader = NdjsonReader(None)
        frames = reader.feed(serialized)
        assert len(frames) == 1
        assert frames[0]["params"]["text"] == "line1\nline2"

    def test_invalid_json_raises_frame_error(self):
        reader = NdjsonReader(None)
        with pytest.raises(FrameError) as exc_info:
            reader.feed(b'not json\n')
        assert exc_info.value.code == PARSE_ERROR

    def test_invalid_utf8_raises_frame_error(self):
        reader = NdjsonReader(None)
        with pytest.raises(FrameError) as exc_info:
            reader.feed(b'\xff\xfe\n')
        assert exc_info.value.code == PARSE_ERROR

    def test_batch_array_raises_invalid_request(self):
        reader = NdjsonReader(None)
        with pytest.raises(FrameError) as exc_info:
            reader.feed(b'[{"jsonrpc":"2.0"}]\n')
        assert exc_info.value.code == INVALID_REQUEST

    def test_frame_exactly_at_limit_is_accepted(self):
        # Build a frame that is exactly MAX_FRAME_SIZE bytes before the newline.
        # The simplest way: a string value padded to hit the limit.
        padding_needed = MAX_FRAME_SIZE - len('{"jsonrpc":"2.0","method":"x","params":{"p":""}}')
        payload = {"jsonrpc": "2.0", "method": "x", "params": {"p": "a" * padding_needed}}
        data = json.dumps(payload, separators=(",", ":")).encode() + b"\n"
        # Should be exactly MAX_FRAME_SIZE + 1 (the newline) bytes total
        assert len(data) - 1 == MAX_FRAME_SIZE
        reader = NdjsonReader(None)
        frames = reader.feed(data)
        assert len(frames) == 1

    def test_oversized_frame_raises_frame_too_large(self):
        # Build a frame that exceeds MAX_FRAME_SIZE
        payload = {"jsonrpc": "2.0", "method": "x", "params": {"p": "a" * (MAX_FRAME_SIZE + 10)}}
        data = json.dumps(payload, separators=(",", ":")).encode() + b"\n"
        reader = NdjsonReader(None)
        with pytest.raises(FrameError) as exc_info:
            reader.feed(data)
        assert exc_info.value.code == int(AlchemistErrorCode.FRAME_TOO_LARGE)


class TestNdjsonReaderAsync:
    async def test_complete_frame_from_stream(self):
        data = b'{"jsonrpc":"2.0","method":"ping"}\n'
        reader = _reader(data)
        frame = await reader.read_frame()
        assert frame["method"] == "ping"

    async def test_fragmented_stream_reassembles(self):
        part1 = b'{"jsonrpc"'
        part2 = b':"2.0","method":"ok"}\n'
        reader = _reader(part1, part2)
        frame = await reader.read_frame()
        assert frame["method"] == "ok"


# ---------------------------------------------------------------------------
# NdjsonWriter tests
# ---------------------------------------------------------------------------

class TestNdjsonWriter:
    async def test_write_frame_produces_newline_terminated_json(self):
        writer, stream = _writer()
        obj = {"jsonrpc": "2.0", "id": "1", "result": True}
        await writer.write_frame(obj)
        raw = stream.written
        assert raw.endswith(b"\n")
        parsed = json.loads(raw.decode())
        assert parsed == obj

    async def test_roundtrip_via_reader_and_writer(self):
        writer, stream = _writer()
        obj = {"jsonrpc": "2.0", "method": "test", "params": {"key": "val\nue"}}
        await writer.write_frame(obj)
        reader = NdjsonReader(None)
        frames = reader.feed(stream.written)
        assert frames[0] == obj
