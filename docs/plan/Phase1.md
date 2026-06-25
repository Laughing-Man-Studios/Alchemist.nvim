#### Phase 1: JSON-RPC Contract Implementation Plan

This phase establishes the foundational protocol contract between the NeoVim Lua client and the Python daemon. It must produce a deterministic, typed JSON-RPC 2.0 implementation over newline-delimited JSON frames, with contract tests that can run without the real Aider backend.

Phase 1 does not implement the full daemon lifecycle, provider routing, Aider execution, shadow workspace engine, or NeoVim UI. It only implements the shared protocol layer, data models, method registry, dispatcher behavior, and fake client/server tests.

---

### 1. Transport and Framing Layer: NDJSON

The communication protocol uses JSON-RPC 2.0 objects encoded as Newline-Delimited JSON over Unix Domain Socket byte streams.

#### Requirements

- Implement an asynchronous stream reader and writer.
- Encode all JSON-RPC objects as UTF-8 JSON.
- Terminate each frame with exactly one newline byte: `\n`.
- Newlines inside JSON string values must be represented through normal JSON escaping.
- The receiver buffers bytes until a newline is encountered.
- The maximum accepted frame size is `16 MiB`.
- If a frame exceeds `16 MiB`, reject it with the normalized Alchemist error `FRAME_TOO_LARGE`.
- Invalid JSON must produce JSON-RPC parse error `-32700`.
- Empty lines should be ignored or rejected consistently; choose one behavior and cover it with tests.
- JSON-RPC batch requests are not supported in V1. If a decoded frame is a JSON array, return `-32600 Invalid Request`.

#### Deliverables

- `NdjsonReader`
- `NdjsonWriter`
- Frame-size enforcement
- UTF-8 decoding validation
- Tests for:
  - complete frame
  - fragmented frame
  - multiple frames in one read
  - escaped newlines inside strings
  - malformed JSON
  - oversized frame
  - unsupported batch array

---

### 2. JSON-RPC 2.0 Base Envelopes

Define strict Pydantic models for the JSON-RPC envelope layer.

#### Envelope Rules

Every JSON-RPC object must enforce:

```json
{
  "jsonrpc": "2.0"
}
```

Supported top-level object types:

- Request
- Notification
- Success Response
- Error Response

#### Request IDs

- Client-originated request IDs should be UUID strings.
- Daemon-originated request IDs for server-initiated prompts may be non-UUID strings, such as `srv_req_...`.
- Response IDs must match the corresponding request ID exactly.
- Notifications must not include an `id`.

#### Unsupported JSON-RPC Features

- Batch requests are unsupported in V1.
- Positional params arrays are unsupported in V1.
- `params`, when present, must be an object.

#### Deliverables

- `JsonRpcRequest`
- `JsonRpcNotification`
- `JsonRpcSuccessResponse`
- `JsonRpcErrorResponse`
- `JsonRpcErrorObject`
- ID type aliases:
  - `ClientRequestId`
  - `ServerRequestId`
  - `JsonRpcId`

---

### 3. Shared Parameter Base Models

Do not force every method to include all context IDs. Instead, define layered context models.

#### Required Base Models

- `ClientScopedParams`
  - `client_id`

- `SessionScopedParams`
  - `client_id`
  - `session_id`

- `ProjectScopedParams`
  - `client_id`
  - `session_id`
  - `project_id`

Use UUID string validation for context IDs.

#### Method Usage

- `client/initialize` uses `ClientScopedParams`, not `ProjectScopedParams`.
- Agent operations generally use `ProjectScopedParams`.
- Daemon global methods such as `daemon/version` and `daemon/health` may use empty params or `ClientScopedParams`, depending on the final method contract.
- Daemon-to-client UI notifications that refer to an operation should use `ProjectScopedParams`.

---

### 4. Domain-Specific Client-to-Daemon Models

Implement method-specific Pydantic param models for all Client → Daemon methods.

#### Required Methods

- `client/initialize`
  - `client_id`
  - `cwd`
  - `nvim_pid`
  - `protocol_version`

- `client/shutdown`
  - `client_id`

- `daemon/version`
  - empty params or `client_id`

- `daemon/health`
  - empty params or `client_id`

- `agent/submit_prompt`
  - `client_id`
  - `session_id`
  - `project_id`
  - `project_path`
  - `mode`
  - `prompt`
  - `active_files`
  - `buffers`

- `agent/cancel`
- `agent/status`
- `agent/list_sessions`
- `agent/reset`
- `agent/clear`
- `agent/add_file`
- `agent/drop_file`
- `agent/list_files`
- `agent/read_only`
- `agent/repo_map`
- `agent/run`
- `agent/test`
- `agent/lint`
- `config/set_key`
- `config/list_providers`
- `config/list_keys`
- `config/delete_key`

For methods whose full behavior is not implemented in Phase 1, still define minimal validated params and placeholder result models.

#### Buffer Snapshot Model

Each submitted buffer must include:

- `path`
- `content`
- `sha256`
- `modified`

Validate:

- `path` is non-empty
- `sha256` is non-empty
- `modified` is boolean
- `content` is string

#### Prompt Mode

Define a strict enum or literal union for known modes:

- `ask`
- `code`
- `architect`

Allow future extension only deliberately.

---

### 5. Domain-Specific Daemon-to-Client Models

Implement method-specific Pydantic param models for all Daemon → Client methods.

#### Required Notifications

- `ui/status_update`
  - `client_id`
  - `session_id`
  - `project_id`
  - `status`
  - `model`
  - `provider`
  - `key_index`
  - `tokens_per_second`
  - `phase`

- `ui/diff_ready`
  - `client_id`
  - `session_id`
  - `project_id`
  - `base_hashes`
  - `diff`
  - `files_changed`

- `ui/clear_prompt`

- `agent/stream_delta`
  - `client_id`
  - `session_id`
  - `project_id`
  - `delta`

- `daemon/key_swapped`
  - `provider`
  - `model`
  - `current_key_index`
  - `cooldown_target`
  - `reason`

- `daemon/error`

- `daemon/exhausted`

#### Required Server-Initiated Request

- `server/request_confirmation`
  - `client_id`
  - `session_id`
  - `project_id`
  - `prompt_type`
  - `message`
  - `default_value`
  - `timeout_ms`

`prompt_type` must be one of:

- `boolean`
- `text`
- `selection`

`timeout_ms` defaults to `60000`.

#### Confirmation Response Result

Define the result model for client responses to `server/request_confirmation`:

- `confirmed`
- `value`

---

### 6. Method Result Models

Define typed result models for common successful responses.

#### Minimum Required Results

- `client/initialize`
  - `daemon_version`
  - `protocol_version`
  - `aider_version`
  - `status`

- `daemon/version`
  - `daemon_version`
  - `protocol_version`
  - optional `aider_version`

- `daemon/health`
  - `status`
  - optional diagnostic fields

- `agent/submit_prompt`
  - accepted/queued/running status
  - job/session identifier if applicable

- `agent/cancel`
  - cancellation state

- `agent/status`
  - current status
  - active job summary if visible

- `agent/list_files`
  - editable files
  - read-only files

- `config/list_providers`
  - provider names and availability metadata, never raw keys

- `config/list_keys`
  - provider names
  - key indexes
  - masked key labels only, never raw key material

---

### 7. Standardized Error Model

Errors must use standard JSON-RPC 2.0 error envelopes with structured Alchemist error data.

#### JSON-RPC Error Codes

Use standard codes where applicable:

- `-32700` Parse error
- `-32600` Invalid Request
- `-32601` Method not found
- `-32602` Invalid params
- `-32603` Internal error

Use application-defined codes in the `-32000` to `-32099` range for normalized Alchemist operational errors.

#### Alchemist Error Data

Every user-facing Alchemist error must include:

- `retryable`
- `hint`
- optional `client_id`
- optional `session_id`
- optional `project_id`
- optional additional context safe for logs/UI

#### Normalized V1 Error Constants

Define a strict enum or literal type containing:

- `NO_KEYS_CONFIGURED`
- `PROVIDER_RATE_LIMITED`
- `ALL_KEYS_EXHAUSTED`
- `PATCH_APPLY_FAILED`
- `AIDER_INTERNAL_ERROR`
- `UV_BOOTSTRAP_FAILED`
- `MODEL_CONTEXT_EXCEEDED`
- `DAEMON_VERSION_MISMATCH`
- `SHADOW_SYNC_FAILED`
- `FRAME_TOO_LARGE`
- `IPC_DISCONNECTED`
- `DAEMON_UNAVAILABLE`
- `AGENT_BUSY`

#### Mandatory Hints

Every normalized user-facing error must have a remediation hint.

Examples:

- `NO_KEYS_CONFIGURED`: `Run :AlchemistSetup and add an API key.`
- `ALL_KEYS_EXHAUSTED`: `Add another key or wait for provider quota reset.`
- `PATCH_APPLY_FAILED`: `Buffers were restored. Reopen the diff or retry the prompt.`
- `DAEMON_VERSION_MISMATCH`: `Update the plugin and rerun setup.`

---

### 8. Method Registry and Dispatcher

Implement the internal routing mechanism that connects JSON-RPC method strings to async Python callbacks.

#### Registry Requirements

Map method string literals to:

- param model
- result model
- async handler
- direction metadata, if useful

Example method strings:

- `client/initialize`
- `agent/submit_prompt`
- `server/request_confirmation`
- `ui/status_update`

#### Dispatcher Requirements

- Decode a raw JSON dictionary into the correct JSON-RPC envelope.
- Reject unsupported batch requests.
- Reject requests with missing or invalid `jsonrpc`.
- Reject unknown methods with `-32601 Method not found`.
- Validate params using the registered Pydantic model.
- Return `-32602 Invalid params` for method-specific params validation failures.
- Return `-32600 Invalid Request` for invalid envelope structure.
- Dispatch valid requests to async handlers.
- Serialize handler results using the registered result model.
- Never send success responses for notifications.
- Gracefully catch unexpected handler exceptions and return `-32603 Internal error` or a normalized Alchemist error where appropriate.
- Redact secrets from validation errors, logs, and diagnostic payloads.

---

### 9. Response Correlation

Implement a small request/response correlation helper for bidirectional JSON-RPC.

#### Requirements

- Track pending outbound requests by ID.
- Match inbound success/error responses to pending requests.
- Reject or log responses with unknown IDs.
- Support daemon-originated `server/request_confirmation` requests.
- Enforce timeout handling for pending requests.
- Ensure response IDs are preserved exactly.

---

### 10. Secret and Redaction Rules

Phase 1 must define secret-bearing schema types because the data contract includes config methods.

#### Requirements

- `config/set_key` must use Pydantic secret types where practical.
- Raw API keys must never appear in:
  - model dumps
  - validation error messages
  - test snapshots
  - logs
  - JSON-RPC diagnostic errors
- `config/list_keys` must only return masked key labels or indexes.

---

### 11. Fake Client/Server Testing Suite

Construct headless Python tests using `pytest` and `pytest-asyncio`.

#### Test Areas

##### Framing Tests

Verify that the parser:

- handles fragmented byte streams
- handles multiple frames in one stream chunk
- preserves escaped newlines inside strings
- rejects invalid UTF-8
- rejects invalid JSON
- enforces the 16 MiB frame limit
- returns or raises `FRAME_TOO_LARGE` when appropriate

##### Envelope Tests

Verify:

- valid request parsing
- valid notification parsing
- valid success response parsing
- valid error response parsing
- invalid `jsonrpc` rejection
- missing method rejection
- unsupported batch request rejection
- params array rejection

##### Method Validation Tests

Verify:

- `client/initialize` succeeds without `session_id` and `project_id`
- `agent/submit_prompt` requires `client_id`, `session_id`, and `project_id`
- incomplete payloads produce `-32602 Invalid params`
- unknown methods produce `-32601 Method not found`
- request IDs are validated according to origin rules

##### Dispatcher Tests

Verify:

- request dispatch invokes the correct handler
- handler result is serialized correctly
- notification dispatch does not produce a response
- handler exceptions produce safe JSON-RPC errors
- Pydantic validation errors are redacted

##### Bidirectional Simulation

Create a lightweight fake client and fake server loop that exchanges:

1. `client/initialize`
2. initialize response
3. `agent/submit_prompt`
4. fake `ui/status_update`
5. fake `agent/stream_delta`
6. fake `server/request_confirmation`
7. client confirmation response
8. fake `ui/diff_ready`

##### Secret Redaction Tests

Verify:

- API keys passed to `config/set_key` are not printed by model dumps
- API keys do not appear in validation messages
- `config/list_keys` does not expose raw key material

---

### 12. Suggested File Layout

Recommended Python package layout:

```text
alchemist/
  protocol/
    __init__.py
    framing.py
    jsonrpc.py
    ids.py
    errors.py
    registry.py
    dispatcher.py
    correlation.py
    models/
      __init__.py
      common.py
      client_to_daemon.py
      daemon_to_client.py
      results.py
tests/
  protocol/
    test_framing.py
    test_jsonrpc_envelopes.py
    test_method_models.py
    test_dispatcher.py
    test_correlation.py
    test_fake_client_server.py
    test_redaction.py
```

---

### 13. Phase 1 Acceptance Criteria

Phase 1 is complete when:

- NDJSON framing is implemented and tested.
- JSON-RPC envelope models are strict and tested.
- All V1 method names have registered param models.
- Core result models are defined.
- Normalized Alchemist errors are implemented with mandatory hints.
- Dispatcher validates and routes requests correctly.
- Notifications do not receive responses.
- Server-initiated request/response correlation works.
- Fake client/server lifecycle test passes.
- Secret-bearing config payloads are redacted.
- No Aider, LiteLLM, shadow workspace, or real NeoVim runtime is required for tests.
