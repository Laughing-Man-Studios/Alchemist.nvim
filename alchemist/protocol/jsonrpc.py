"""
JSON-RPC 2.0 strict Pydantic envelope models.

Supports:
  JsonRpcRequest, JsonRpcNotification,
  JsonRpcSuccessResponse, JsonRpcErrorResponse, JsonRpcErrorObject

Rejects:
  - batch arrays
  - positional params arrays
  - missing / wrong jsonrpc field
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, field_validator, model_validator


"""Represents a standard JSON-RPC error object containing a numeric code, a descriptive message, and optional additional data.
"""
class JsonRpcErrorObject(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


"""
Represents a JSON-RPC 2.0 request object, ensuring that 'params' is a dictionary rather than a list.
"""
class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"]
    id: Union[str, int]
    method: str
    params: Optional[Dict[str, Any]] = None

    @field_validator("params", mode="before")
    @classmethod
    def params_must_be_object(cls, v: Any) -> Any:
        if isinstance(v, list):
            raise ValueError("params must be an object, not an array")
        return v


"""
Represents a JSON-RPC 2.0 notification message.

Ensures that the 'params' field is a dictionary object rather than a list,
adhering to the JSON-RPC specification for notifications.
"""
class JsonRpcNotification(BaseModel):
    jsonrpc: Literal["2.0"]
    method: str
    params: Optional[Dict[str, Any]] = None

    @field_validator("params", mode="before")
    @classmethod
    def params_must_be_object(cls, v: Any) -> Any:
        if isinstance(v, list):
            raise ValueError("params must be an object, not an array")
        return v


"""Represents a successful JSON-RPC 2.0 response containing the result of a request."""
class JsonRpcSuccessResponse(BaseModel):
    jsonrpc: Literal["2.0"]
    id: Union[str, int]
    result: Any


"""Represents a JSON-RPC 2.0 error response object containing the protocol version, request ID, and error details."""
class JsonRpcErrorResponse(BaseModel):
    jsonrpc: Literal["2.0"]
    id: Optional[Union[str, int]]
    error: JsonRpcErrorObject


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

EnvelopeType = Union[
    JsonRpcRequest,
    JsonRpcNotification,
    JsonRpcSuccessResponse,
    JsonRpcErrorResponse,
]


"""Parses a raw JSON-RPC message and returns the corresponding envelope model.

Validates the structure of the input dictionary to determine if it is a
request, notification, success response, or error response based on
required JSON-RPC fields. Raises ValueError if the input is invalid,
not a dictionary, or lacks necessary fields.
"""
def classify_message(raw: Any) -> EnvelopeType:
    """Classify a decoded JSON dict into the appropriate envelope model.

    Raises ValueError for structural issues; callers should convert to
    JSON-RPC error responses as appropriate.
    """
    if isinstance(raw, list):
        raise ValueError("Batch requests are not supported")
    if not isinstance(raw, dict):
        raise ValueError("JSON-RPC message must be a JSON object")
    if raw.get("jsonrpc") != "2.0":
        raise ValueError('Missing or invalid "jsonrpc" field; must be "2.0"')

    if "method" in raw:
        if "id" in raw:
            return JsonRpcRequest.model_validate(raw)
        return JsonRpcNotification.model_validate(raw)
    if "result" in raw:
        return JsonRpcSuccessResponse.model_validate(raw)
    if "error" in raw:
        return JsonRpcErrorResponse.model_validate(raw)
    raise ValueError("Cannot classify JSON-RPC message: missing method/result/error")
