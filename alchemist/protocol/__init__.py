"""
Alchemist JSON-RPC protocol package.

Public re-exports for the most commonly used symbols.
"""
from alchemist.protocol.correlation import CorrelationTracker
from alchemist.protocol.dispatcher import Dispatcher
from alchemist.protocol.errors import AlchemistErrorCode, AlchemistErrorData
from alchemist.protocol.framing import FrameError, NdjsonReader, NdjsonWriter
from alchemist.protocol.ids import (
    ClientRequestId,
    JsonRpcId,
    ServerRequestId,
    make_client_request_id,
    make_server_request_id,
)
from alchemist.protocol.jsonrpc import (
    JsonRpcErrorObject,
    JsonRpcErrorResponse,
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcSuccessResponse,
    classify_message,
)
from alchemist.protocol.registry import MethodEntry, MethodRegistry, build_default_registry

__all__ = [
    "AlchemistErrorCode",
    "AlchemistErrorData",
    "classify_message",
    "ClientRequestId",
    "CorrelationTracker",
    "Dispatcher",
    "FrameError",
    "JsonRpcErrorObject",
    "JsonRpcErrorResponse",
    "JsonRpcId",
    "JsonRpcNotification",
    "JsonRpcRequest",
    "JsonRpcSuccessResponse",
    "MethodEntry",
    "MethodRegistry",
    "NdjsonReader",
    "NdjsonWriter",
    "ServerRequestId",
    "build_default_registry",
    "make_client_request_id",
    "make_server_request_id",
]
