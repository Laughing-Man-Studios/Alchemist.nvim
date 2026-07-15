#### Phase 2: Python Daemon Implementation Plan

This phase establishes the foundational Python daemon, focusing on process control, lifecycle coordination, local state management, and execution stubs. It must produce a single, robust system-wide master process that handles client initialization, manages its own persistence layer, and simulates agent routing without yet requiring the real shadow workspace or NeoVim Lua UI.

---

### 1. Process Control and IPC Server

The daemon must operate as a single Python process utilizing an asyncio event loop to manage Unix socket connections.

#### Requirements

* Implement an asynchronous stream server using Unix domain sockets.


* Resolve the socket path to `$XDG_RUNTIME_DIR/alchemist.sock` with a fallback to `/tmp/alchemist_$USER.sock`.


* Enforce strict `0600` socket permissions.


* Validate that connecting clients belong to the same OS user.


* Implement the initialization handshake to negotiate the daemon version, protocol version, and status.


* Ensure the main event loop remains non-blocking during file operations or future Aider execution.



#### Deliverables

* `AlchemistDaemon` class and main asyncio event loop.
* `IpcServer` for managing the Unix domain socket.
* Client registry to track active NeoVim connections.
* Handshake handler for `client/initialize` negotiation.
* Tests for concurrent client connections and permission enforcement.

---

### 2. Lifecycle Management and Master Election

To prevent multiple NeoVim instances from spawning duplicate daemons, strict lifecycle and lockfile management must be established.

#### Requirements

* Implement lockfile acquisition logic using an atomic OS-level file lock.


* Resolve the lockfile path to `$XDG_RUNTIME_DIR/alchemist.lock` with a fallback to `/tmp/alchemist_$USER.lock`.


* Implement stale socket detection, which verifies if a daemon is actively listening before allowing a client to remove a dead socket.


* Track active client channels using a reference counter.


* Implement a reference-counted shutdown sequence that initiates a 15-second grace period when the active client count reaches zero.


* Flush all telemetry and terminate the process cleanly if no client reconnects during the grace period.



#### Deliverables

* `LifecycleManager` and lockfile acquisition utilities.
* Stale socket cleanup routines.
* Graceful shutdown timer and reference counter.
* Tests simulating rapid client disconnect/reconnect and concurrent spawn attempts.

---

### 3. State Management: SQLite Ledger

The daemon requires a persistent local ledger to track historical quota usage, normalized errors, and telemetry.

#### Requirements

* Initialize an `aiosqlite` database connection.


* Configure the SQLite database to use Write-Ahead Logging (WAL).


* Apply the following PRAGMAs: `journal_mode = WAL;`, `synchronous = NORMAL;`, and `busy_timeout = 5000;`.


* Ensure that raw prompts, code snippets, full file contents, and plaintext API keys are never persisted to this ledger.


* Build a background asyncio worker that batches memory metrics.


* Implement a deferred commit policy that flushes metrics to the ledger every 2 seconds, at the end of an LLM block, or during daemon shutdown.



#### Deliverables

* `SqliteLedger` database manager and schema initialization.
* Telemetry tables for tracking token counts, models, and timestamps.


* Background batch worker for deferred commits.
* Tests verifying WAL mode, data retention, and privacy boundaries.

---

### 4. State Management: Provider Key Vault

Before the robust cryptographic derivation of Phase 5 is applied, the structural foundation for the local provider key vault must be established.

#### Requirements

* Define the primary path for the encrypted local vault at `~/.config/alchemist/vault.enc`.


* Enforce strict `0600` file permissions upon creation (owner read/write only).


* Create the foundational read/write boundaries for the vault.


* Stub the internal payload structure to prepare for the 12-byte random IV, ciphertext, and 16-byte auth tag.



#### Deliverables

* `LocalVault` manager class.
* Path resolution and OS-level permission enforcement logic.
* Storage interfaces that integrate with Pydantic `SecretStr` models.
* Tests verifying correct file permissions upon creation.

---

### 5. Agent Engine and Routing Stubs

The daemon orchestrates Aider execution and model selection, which must be hidden behind generic interfaces for testing and future-proofing.

#### Requirements

* Define an internal `AssistantEngine` interface to isolate the daemon from direct coupling with Aider.


* Stub out the engine methods: `submit_prompt`, `cancel`, `get_status`, and `reset`.


* Create a fake LiteLLM provider to enable deterministic testing.


* Ensure the fake provider can simulate successful completions, streaming chunks, token usage headers, HTTP 429 rate limits, and context-limit errors.


* Build the basic routing matrix stub that hardcodes the fallback logic to route repository mapping to Gemini Flash-class models, code modifications to DeepSeek-V3, and exploratory chats to Qwen 72B-class models.



#### Deliverables

* `AssistantEngine` base class and stub implementation.
* `FakeLiteLLMProvider` simulating provider responses and quotas.
* `RoutingPolicy` module defining the task routing matrix.
* Tests validating engine abstraction and fake provider error simulations.

---

### 6. Suggested File Layout

Recommended Python package layout:

```text
alchemist/
  daemon/
    __init__.py
    main.py
    server.py
    lifecycle.py
    lock.py
  state/
    __init__.py
    ledger.py
    vault.py
    quota.py
  engine/
    __init__.py
    interface.py
    routing.py
  testing/
    __init__.py
    fake_litellm.py
tests/
  daemon/
    test_server.py
    test_lifecycle.py
    test_lock.py
  state/
    test_ledger.py
    test_vault.py
  engine/
    test_routing.py
    test_fake_litellm.py

```

---

### 7. Phase 2 Acceptance Criteria

Phase 2 is complete when:

* A single daemon instance successfully claims the lockfile and starts the Unix server.
* Duplicate daemon spawn attempts gracefully fail or connect to the master process.
* The Unix socket and vault files are created with strict `0600` permissions.
* Client disconnections properly decrement the active client count.
* The daemon shuts down cleanly after 15 seconds of zero active clients.
* The `aiosqlite` ledger initializes in WAL mode and safely flushes batched metrics.
* The generic `AssistantEngine` interface is fully mocked.
* The fake LiteLLM provider reliably triggers simulated streaming and rate-limit errors during test execution.
