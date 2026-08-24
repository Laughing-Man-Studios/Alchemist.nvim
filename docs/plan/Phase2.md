# Phase 2: Python Daemon Implementation Plan

This phase establishes the foundational Python daemon, focusing on process control, lifecycle coordination, local state management, execution stubs, and the core architectural boundaries required for later phases. It must produce a single, robust system-wide master process that handles client initialization, manages its persistence layer, enforces protocol framing, and simulates agent routing without yet requiring the real shadow workspace or NeoVim Lua UI.

---

## 1. Process Control and IPC Server

The daemon must operate as a single Python process utilizing an asyncio event loop to manage Unix socket connections, enforce protocol boundaries, and route JSON-RPC traffic.

### Requirements

* Implement an asynchronous stream server using Unix domain sockets.
* Resolve the socket path to `$XDG_RUNTIME_DIR/alchemist.sock` with a fallback to `/tmp/alchemist_$USER.sock`.
* Enforce strict `0600` socket permissions.
* Validate that connecting clients belong to the same OS user.
* Implement the initialization handshake (`client/initialize`) to negotiate the daemon version, protocol version, Aider version, and status.
* Implement version compatibility checks. If the client's `protocol_version` is incompatible, return `DAEMON_VERSION_MISMATCH` with a hint to update and rerun setup.
* Track the originating `nvim_pid` per client for process-liveness checks.
* Enforce a maximum frame size of 16 MiB; reject oversized frames with the `FRAME_TOO_LARGE` error code.
* Reject invalid JSON with a JSON-RPC parse error (-32700).
* Buffer incoming bytes until newline termination and reject frames containing embedded literal newlines.
* Ensure the main event loop remains non-blocking during file operations or future Aider execution.

### Deliverables

* `AlchemistDaemon` class and main asyncio event loop.
* `IpcServer` for managing the Unix domain socket and framing validation.
* Client registry to track active NeoVim connections.
* Handshake handler for `client/initialize` negotiation and version compatibility enforcement.
* Framing validator integrated into the IPC server's read loop.
* Tests for concurrent client connections, permission enforcement, oversized frames, malformed JSON, and partial-frame buffering.

---

## 2. JSON-RPC Dispatch and Error Normalization

To bridge the Phase 1 contract with the daemon's internal execution, a robust dispatch and error normalization layer is required.

### Requirements

* Implement a JSON-RPC 2.0 method dispatcher that maps incoming method strings to async handler callables.
* Support both request-response and notification (no-ID) message types.
* Implement request/response correlation using UUID string IDs.
* Define a centralized `AlchemistError` exception hierarchy mapping internal failures to normalized V1 error codes (e.g., `NO_KEYS_CONFIGURED`, `ALL_KEYS_EXHAUSTED`, `DAEMON_VERSION_MISMATCH`, `FRAME_TOO_LARGE`, `AGENT_BUSY`).
* Each error must carry a stable string code, a human-readable message, a `retryable` boolean, and a `hint` string with a remediation action.
* Implement a top-level exception handler in the RPC dispatcher that catches `AlchemistError` subclasses and serializes them into the standard JSON-RPC error envelope with structured `data`. Tracebacks must never be forwarded to clients.
* Register stub handlers for the full V1 client→daemon method registry, returning normalized "not yet implemented" errors where appropriate:
  * `daemon/version`, `daemon/health`
  * `agent/submit_prompt`, `agent/cancel`, `agent/status`, `agent/list_sessions`, `agent/reset`, `agent/clear`, `agent/add_file`, `agent/drop_file`, `agent/list_files`, `agent/read_only`, `agent/repo_map`, `agent/run`, `agent/test`, `agent/lint`
  * `config/set_key`, `config/list_providers`, `config/list_keys`, `config/delete_key`
* Implement `daemon/health` returning process liveness, socket path, active client count, uptime, and whether any keys are configured.
* Implement `daemon/version` returning daemon version, protocol version, and Aider version.

### Deliverables

* `MethodRegistry` class mapping method names to async handlers.
* `RpcDispatcher` that decodes frames, routes to handlers, and encodes responses.
* `errors.py` module with the exception hierarchy and code→hint mapping table.
* `daemon/health` and `daemon/version` handler implementations.
* Tests verifying that every error code produces a well-formed envelope with a non-empty hint, and that health/version endpoints return correct metadata immediately after startup.

---

## 3. Project Registry and Active Job State

The daemon must enforce V1 global serialization rules and track project/session state.

### Requirements

* Implement a `ProjectRegistry` that maps `project_id` → project metadata (path, shadow workspace root placeholder, active session).
* Implement an `ActiveJobTracker` that enforces the V1 constraint of **one active agent job globally**.
* When a job is in progress and another `agent/submit_prompt` arrives, return `AGENT_BUSY` with a summary of the current job and a suggestion to wait or cancel.
* Generate and track `session_id` UUIDs for protocol correlation (in-memory only, not persisted across restarts).
* Track `client_id` → `project_id` ownership so that server-initiated prompts route to the correct client.

### Deliverables

* `ProjectRegistry` class.
* `ActiveJobTracker` with single-job enforcement and `AGENT_BUSY` error emission.
* `SessionManager` for session ID generation and lookup.
* Tests for concurrent job submission, `AGENT_BUSY` enforcement, and session lifecycle.

---

## 4. Lifecycle Management and Master Election

To prevent multiple NeoVim instances from spawning duplicate daemons, strict lifecycle, signal handling, and lockfile management must be established.

### Requirements

* Implement lockfile acquisition logic using an atomic OS-level file lock.
* Resolve the lockfile path to `$XDG_RUNTIME_DIR/alchemist.lock` with a fallback to `/tmp/alchemist_$USER.lock`.
* Implement stale socket detection, which verifies if a daemon is actively listening before allowing a client to remove a dead socket.
* Track active client channels using a reference counter.
* Implement a reference-counted shutdown sequence that initiates a 15-second grace period when the active client count reaches zero.
* Install `SIGTERM` and `SIGINT` handlers that trigger immediate graceful shutdown (bypassing the 15-second grace period).
* On signal: flush all batched SQLite metrics, run a WAL checkpoint, close the database, remove the socket file, release the lockfile, and exit with code 0.
* On `SIGHUP`: log and ignore (do not crash).
* Flush all telemetry and terminate the process cleanly if no client reconnects during the grace period.

### Deliverables

* `LifecycleManager` and lockfile acquisition utilities.
* Stale socket cleanup routines.
* Graceful shutdown timer, reference counter, and OS signal handler integration.
* Tests simulating rapid client disconnect/reconnect, concurrent spawn attempts, and clean shutdown on `SIGTERM` with pending batched metrics.

---

## 5. State Management: SQLite Ledger & Quota Tracker

The daemon requires a persistent local ledger to track historical quota usage, normalized errors, and telemetry. It also requires the in-memory data structures for high-frequency quota tracking.

### Requirements

* Initialize an `aiosqlite` database connection.
* Configure the SQLite database to use Write-Ahead Logging (WAL).
* Apply the following PRAGMAs: `journal_mode = WAL;`, `synchronous = NORMAL;`, and `busy_timeout = 5000;`.
* Ensure that raw prompts, code snippets, full file contents, and plaintext API keys are never persisted to this ledger.
* Build a background asyncio worker that batches memory metrics.
* Implement a deferred commit policy that flushes metrics to the ledger every 2 seconds, at the end of an LLM block, or during daemon shutdown.
* Initialize an empty in-memory `QuotaTracker` dictionary keyed by `(provider, key_index)`.
* Define metric fields: `rpm`, `tpm`, `rpd`, `tpd`, `cooldown_until`, `last_request_ts`, `state` (active/cooldowned/exhausted). Full rotation/cooldown logic is deferred to Phase 6.

### Deliverables

* `SqliteLedger` database manager and schema initialization.
* Telemetry tables for tracking token counts, models, and timestamps.
* Background batch worker for deferred commits.
* `QuotaTracker` data structure (in-memory only).
* Tests verifying WAL mode, data retention, privacy boundaries, and that the fake provider can update/read quota state.

---

## 6. State Management: Provider Key Vault & Config Handlers

Before the robust cryptographic derivation of Phase 5 is applied, the structural foundation for the local provider key vault and its JSON-RPC handlers must be established.

### Requirements

* Define the primary path for the encrypted local vault at `~/.config/alchemist/vault.enc`.
* Enforce strict `0600` file permissions upon creation (owner read/write only).
* Create the foundational read/write boundaries for the vault.
* Stub the internal payload structure to prepare for the 12-byte random IV, ciphertext, and 16-byte auth tag.
* Implement `config/set_key` — accepts `provider` and `api_key` (as Pydantic `SecretStr`), persists to the vault, returns a masked confirmation.
* Implement `config/list_providers` — returns the list of supported V1 providers (hardcoded).
* Implement `config/list_keys` — returns provider names and key indices, never raw key values.
* Implement `config/delete_key` — internal/test method for cleanup.
* Return `NO_KEYS_CONFIGURED` appropriately when agent methods are called before any key exists.

### Deliverables

* `LocalVault` manager class.
* Path resolution and OS-level permission enforcement logic.
* Storage interfaces that integrate with Pydantic `SecretStr` models.
* `config/*` RPC handlers wired to the `LocalVault`.
* Tests verifying correct file permissions, set/list/delete flows, and masked output verification.

---

## 7. State Management: Logging and Redaction

Phase 5 handles full credential redaction, but the logging infrastructure with redaction hook points must be established now.

### Requirements

* Set up Python `logging` with a structured formatter.
* Logs are **disabled by default** (disk writes off).
* Provide a debug toggle (via RPC or env var) to enable logging for development.
* Install a redaction filter at the logger level that replaces bearer patterns with `[REDACTED_CREDENTIAL]`. The regex can be a stub in Phase 2 and hardened in Phase 5.
* Define a `LogPanelBuffer` (in-memory ring buffer) that the future `:AlchemistLogs` command will read via RPC. It must store normalized operational errors and hints, never raw prompts or code.

### Deliverables

* `LoggingConfig` with redaction filter stub.
* `LogPanelBuffer` in-memory ring buffer.
* Tests verifying that `SecretStr` values and bearer-like strings are masked in log output.

---

## 8. Agent Engine, Routing, and Interception Stubs

The daemon orchestrates Aider execution and model selection, which must be hidden behind generic interfaces for testing and future-proofing. The architectural pattern for thread isolation and IO interception must be established now.

### Requirements

* Define an internal `AssistantEngine` interface to isolate the daemon from direct coupling with Aider. Stub out `submit_prompt`, `cancel`, `get_status`, and `reset`.
* Create a fake LiteLLM provider to enable deterministic testing (simulating successful completions, streaming chunks, token usage headers, HTTP 429 rate limits, and context-limit errors).
* Build the basic routing matrix stub that hardcodes the fallback logic (mapping to Gemini Flash, DeepSeek-V3, Qwen 72B).
* Establish the `ThreadIsolatedBridge` architectural pattern: Aider execution runs in a worker thread, and prompt requests are bridged to the main event loop via `asyncio.run_coroutine_threadsafe`.
* The bridge must support `server/request_confirmation` round-trips (boolean, text, selection) with a 60-second timeout and conservative fallback defaults.
* Implement the `DaemonInputOutput` stub overriding the IO boundary to capture streaming output, status updates, and confirmation prompts, routing them correctly.
* Stub a `LiteLLMInterceptor` layer that will eventually inject keys, track token usage, and rotate keys. For Phase 2, it delegates to the `FakeLiteLLMProvider` and stubs interception hooks as no-ops.
* Implement a `Broadcaster` to send notifications to specific clients or all connected clients (for `daemon/key_swapped`, `daemon/exhausted`). Notifications must not block the event loop.

### Deliverables

* `AssistantEngine` base class and stub implementation.
* `FakeLiteLLMProvider` simulating provider responses and quotas.
* `RoutingPolicy` module defining the task routing matrix.
* `ThreadIsolatedBridge` class with thread-safe future plumbing.
* `InterceptedIO` base class defining the capture surface.
* `LiteLLMInterceptor` class with pluggable hook slots.
* `Broadcaster` class integrated with the client registry.
* Tests validating engine abstraction, fake provider error simulations, blocking prompt behavior (ensuring it doesn't stall IPC), and targeted vs. global notification delivery.

---

## 9. Dependency and Path Normalization Utilities

Centralized path handling and dependency declaration ensure future Windows support and `uv` bootstrapping succeed without refactoring.

### Requirements

* The daemon entry point (`alchemist_daemon.py`) must include PEP 723 inline script metadata (`# /// script`) declaring `requires-python = "==3.12.*"` and pinned dependency ranges for `aider-chat`, `litellm`, `pydantic`, `aiosqlite`, `cryptography`.
* The daemon must refuse to start if required dependencies are missing (fail fast with a clear error).
* Implement a `PathUtil` module that centralizes:
  * Socket path resolution (`$XDG_RUNTIME_DIR` vs `/tmp` fallback).
  * Lockfile path resolution.
  * Vault path resolution (`~/.config/alchemist/`).
  * Shadow workspace path resolution (stub for Phase 3).
  * Project root detection.
* All path operations in the daemon must go through this layer, not call `os.path` or `pathlib` directly in business logic.

### Deliverables

* PEP 723 header in `alchemist_daemon.py`.
* `constants.py` with pinned version strings.
* `paths.py` utility module.
* Tests for XDG fallback, tilde expansion, and permission-checked directory creation.

---

## 10. Suggested File Layout

Recommended Python package layout incorporating all Phase 2 requirements:

```text
alchemist/
  daemon/
    __init__.py
    main.py                 # Entry point with PEP 723 header, signal handlers
    server.py               # IpcServer, framing, frame size enforcement
    lifecycle.py            # LifecycleManager, grace period, reference counter
    lock.py                 # Lockfile acquisition
    dispatcher.py           # RpcDispatcher, MethodRegistry
    broadcaster.py          # Notification broadcast to clients
    paths.py                # Centralized path normalization
    constants.py            # Pinned versions, provider/model defaults
  state/
    __init__.py
    ledger.py               # SqliteLedger, WAL, batch worker
    vault.py                # LocalVault, 0600 enforcement
    quota.py                # In-memory QuotaTracker (stub for Phase 6)
    log_panel.py            # In-memory ring buffer for :AlchemistLogs
  engine/
    __init__.py
    interface.py            # AssistantEngine abstract interface
    routing.py              # RoutingPolicy matrix
    bridge.py               # ThreadIsolatedBridge
    io_intercept.py         # InterceptedIO stub
    litellm_interceptor.py  # LiteLLMInterceptor with hook slots
  errors.py                 # AlchemistError hierarchy, code→hint mapping
  logging_config.py         # Logging setup with redaction filter stub
  testing/
    __init__.py
    fake_litellm.py         # FakeLiteLLMProvider
tests/
  daemon/
    test_server.py
    test_lifecycle.py
    test_lock.py
    test_dispatcher.py
    test_broadcaster.py
    test_framing.py
    test_handshake.py
    test_health_version.py
    test_signal_shutdown.py
  state/
    test_ledger.py
    test_vault.py
    test_quota_tracker.py
    test_log_panel.py
  engine/
    test_routing.py
    test_fake_litellm.py
    test_bridge.py
    test_io_intercept.py
    test_litellm_interceptor.py
  test_errors.py
  test_paths.py
  test_config_handlers.py
  test_project_registry.py
  test_active_job_tracker.py
```

---

## 11. Phase 2 Acceptance Criteria

Phase 2 is complete when:

* A single daemon instance successfully claims the lockfile and starts the Unix server.
* Duplicate daemon spawn attempts gracefully fail or connect to the master process.
* The Unix socket and vault files are created with strict `0600` permissions.
* Client disconnections properly decrement the active client count.
* The daemon shuts down cleanly after 15 seconds of zero active clients, or immediately upon `SIGTERM` (flushing SQLite, removing socket, releasing lock).
* The `aiosqlite` ledger initializes in WAL mode and safely flushes batched metrics.
* The JSON-RPC dispatcher routes all registered methods (stubs return normalized `NOT_IMPLEMENTED` or canned responses).
* Oversized frames (>16 MiB) are rejected with `FRAME_TOO_LARGE`; invalid JSON returns a parse error.
* Every normalized error code produces a well-formed envelope with a non-empty remediation hint.
* `daemon/health` and `daemon/version` return correct metadata immediately after startup.
* `config/set_key`, `config/list_providers`, `config/list_keys`, and `config/delete_key` function correctly against the vault; raw keys never appear in responses or logs.
* `client/initialize` correctly negotiates versions and returns `DAEMON_VERSION_MISMATCH` on incompatible protocol versions.
* A second concurrent `agent/submit_prompt` returns `AGENT_BUSY` with the current job summary.
* The thread-isolated bridge does not stall the IPC event loop when the fake provider issues a blocking prompt.
* The fake LiteLLM provider's streaming chunks flow through IO interception into correctly shaped `agent/stream_delta` notifications.
* The `Broadcaster` delivers targeted notifications to the correct client and global notifications to all connected clients.
* PEP 723 inline metadata is present and `uv run alchemist_daemon.py` succeeds in a clean environment.
* The in-memory `QuotaTracker` structure is initialized and the fake provider can read/write quota state during tests.
* All path resolution goes through the centralized `paths.py` utility; no direct `os.path`/`pathlib` calls in business logic.
* Log output with debug enabled shows `[REDACTED_CREDENTIAL]` in place of bearer-like strings (stub regex is acceptable for Phase 2).
