# Alchemist.nvim — Full Architecture Specification

**Version:** V1 Working Personal Plugin Specification

**Status:** Implementation-ready draft

**Primary milestone:** Working personal plugin

**Primary platform:** macOS

**Secondary V1 platform:** Linux

**Deferred platform:** Windows

---

## 0. Executive Summary

Alchemist.nvim is a zero-config, native NeoVim AI assistant plugin that wraps the Aider agent core and LiteLLM SDK inside a single headless Python background daemon. The daemon is managed invisibly through Astral's `uv`, exposes a structured JSON-RPC 2.0 API over local IPC, and coordinates all editor instances through a single system-wide master process.

The plugin's primary product goal is to provide Aider-like code editing workflows directly inside NeoVim while hiding Python setup, daemon lifecycle management, model selection, API key storage, quota tracking, and provider failover behind simple UI flows.

For V1, Alchemist intentionally prioritizes determinism and simplicity:

- One system-wide daemon
- One active agent job globally
- One project active at a time
- macOS-first, Linux-supported
- Unix domain sockets only
- UI-based setup only
- No manual config file editing
- Aider parity as the guiding behavior model
- Hardcoded provider/model routing optimized for free-tier preservation

Post-V1 features such as Windows named pipes, OS keychain integration, advanced configuration, concurrent jobs, project-local overrides, and complex multi-provider policy tuning are explicitly deferred.

---

## 1. Naming, Identity, and User-Facing Surface

### 1.1 Canonical Name

The canonical product name is:

```text
Alchemist.nvim

```

All user-facing commands, statusline functions, Lua APIs, daemon filenames, documentation, logs, and internal package names must use **Alchemist**. Previous placeholder names such as `FreeAider`, `free_aider_daemon.py`, `FreeAiderStatus()`, and `:FreeAiderSetup` are removed.

### 1.2 Canonical Internal Names

Recommended names:

```text
alchemist_daemon.py
alchemist.sock
alchemist_<user>.sock
~/.local/share/nvim/alchemist/
~/.config/alchemist/
.git/alchemist/shadow/

```

### 1.3 V1 User Commands

Alchemist should mirror Aider behavior as closely as practical while translating terminal-centric slash commands into NeoVim-native commands and UI actions.

Core lifecycle commands:

```vim
:AlchemistSetup
:AlchemistOpen
:AlchemistClose
:AlchemistStart
:AlchemistStop
:AlchemistRestart
:AlchemistDoctor
:AlchemistLogs
:AlchemistStatus

```

Core agent commands:

```vim
:AlchemistChat
:AlchemistAsk
:AlchemistCode
:AlchemistArchitect
:AlchemistCancel
:AlchemistDiff
:AlchemistApply
:AlchemistReject
:AlchemistReset
:AlchemistClear

```

File/context commands:

```vim
:AlchemistAdd
:AlchemistReadOnly
:AlchemistDrop
:AlchemistFiles
:AlchemistMap
:AlchemistMapRefresh

```

Execution/support commands:

```vim
:AlchemistRun
:AlchemistTest
:AlchemistLint
:AlchemistCommit

```

Model/config inspection commands:

```vim
:AlchemistModels
:AlchemistSettings

```

V1 does not need to implement every Aider command perfectly, but the command vocabulary and behavior should be designed so that Aider command parity can be expanded without breaking the public API.

### 1.4 Lua API

Minimal Lua setup:

```lua
require("alchemist").setup()

```

Statusline API:

```lua
require("alchemist").status()

```

The status function should return a short, render-safe string suitable for statusline integrations such as lualine:

```text
🤖 Alchemist [DeepSeek-V3 | Key #3]

```

The statusline may expose the actual active provider/model because the user explicitly wants this information visible.

---

## 2. Product Philosophy and Zero-Config Definition

### 2.1 Core Product Goal

Alchemist is designed to make Aider-style AI coding assistance feel native inside NeoVim. The user should not need to understand or manually manage Python virtual environments, daemon processes, LiteLLM routing, JSON-RPC transport, dependency installation, shadow workspaces, or quota ledgers.

### 2.2 Definition of Zero-Config

For Alchemist, zero-config means:

* No manual editing of config files
* No manual Python environment setup
* No manual daemon installation
* No manual dependency installation
* No required Lua options beyond `require("alchemist").setup()`
* All required setup occurs through interactive NeoVim UI flows

Zero-config does **not** mean that chat works without API keys. Users must add provider API keys through `:AlchemistSetup` before agent features become available.

### 2.3 First-Run Behavior

On first use:

1. Client initializes.
2. Client checks whether the daemon is reachable.
3. Client checks whether `uv` is available.
4. If `uv` is missing, the user is prompted before download.
5. Client starts or connects to daemon.
6. Daemon reports whether any usable provider keys exist.
7. If no keys exist, Alchemist opens setup flow automatically.
8. Chat/code-editing operations remain disabled until at least one provider key is configured.

### 2.4 No Offline/Local Fallback in V1

V1 does not include offline/local LLM mode. If no API keys are added, agent features fail with `NO_KEYS_CONFIGURED` and direct the user to setup.

---

## 3. V1 Scope and Non-Goals

### 3.1 V1 Included Scope

V1 includes:

* Single system-wide Python daemon
* Multi-client NeoVim connection support
* One active job globally
* One active project at a time
* Unix domain socket IPC on macOS/Linux
* JSON-RPC 2.0 over newline-delimited JSON frames
* `uv`-managed Python runtime and dependencies
* UI-driven setup
* UI-driven API key entry and persistence
* Basic provider/model routing
* Multi-key support per provider
* Free-tier-preserving quota tracking
* Shadow workspace execution
* Prompt submission
* Streaming status/token updates
* Unified diff generation
* Diff approval/rejection
* Basic conflict handling
* Cancellation if supported by the underlying Aider execution path
* Statusline function
* Local-only telemetry for quota usage
* Headless tests for daemon and NeoVim UI

### 3.2 Explicit V1 Non-Goals

The following are deferred:

* Windows named pipe support
* Native Windows Credential Manager / DPAPI support
* Linux Secret Service hardening as primary V1 path
* macOS Keychain as primary V1 path
* Advanced user configuration
* Project-local `.alchemist.*` configuration
* User-defined model profiles
* Multiple concurrent jobs
* Multiple simultaneously mutable project workspaces
* Cross-client job visibility
* Persistent chat sessions
* Hunk-level custom UI beyond what the chosen diff UI supports
* Full marketplace-ready polish
* Enterprise-safe no-download mode
* Remote telemetry/analytics

---

## 4. System Topology and Communication Model

### 4.1 Architecture Pattern

Alchemist uses a **single system-wide master daemon / multi-client architecture**.

Multiple lightweight NeoVim Lua clients communicate with one stateful Python daemon. The daemon owns provider keys, quota state, shadow workspaces, model routing, and Aider orchestration.

```text
┌────────────────────────┐               ┌────────────────────────┐
│   NeoVim Instance #1   │               │   NeoVim Instance #2   │
│  Lua UI / Client       │               │  Lua UI / Client       │
└───────────┬────────────┘               └───────────┬────────────┘
            │                                        │
            │ JSON-RPC 2.0 over Unix Domain Socket   │
            └───────────────────┬────────────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ Alchemist Master Daemon│
                    │ Single Python Process  │
                    └───────────┬────────────┘
                                │
                                │ aiosqlite WAL ledger
                                ▼
                    ┌────────────────────────┐
                    │ Shared SQLite Ledger   │
                    └────────────────────────┘

```

### 4.2 Transport Mechanism

V1 transport:

* macOS/Linux: Unix domain sockets
* Windows: deferred

Default socket path resolution:

```text
$XDG_RUNTIME_DIR/alchemist.sock

```

Fallback:

```text
/tmp/alchemist_$USER.sock

```

The socket file must be created with restrictive permissions and must only be accessible to the current OS user.

### 4.3 Protocol

The protocol is structured JSON-RPC 2.0. Raw terminal parsing, pseudo-TTY scraping, ANSI-sequence parsing, and shell-output scraping are prohibited for the main daemon/client control path.

### 4.4 Message Framing

V1 uses newline-delimited JSON frames over the socket.

Rules:

* Each JSON-RPC object is encoded as UTF-8 JSON.
* Each frame is terminated with a single newline byte: `\n`.
* Newlines inside string values must be JSON-escaped.
* The receiver buffers bytes until newline.
* Invalid JSON produces JSON-RPC parse error.
* Oversized frames are rejected with `FRAME_TOO_LARGE`.

Recommended max frame size for V1:

```text
16 MiB

```

Large diffs exceeding this size should be rejected with a clear remediation message or later moved to an out-of-band temp-file exchange mechanism in post-V1.

---

## 5. Daemon Lifecycle, Master Election, and Versioning

### 5.1 Bootstrap Flow

On NeoVim initialization:

1. Lua client computes socket path.
2. Client attempts to connect.
3. If connection succeeds, client sends `client/initialize`.
4. If connection fails, client attempts to acquire daemon lockfile.
5. If lock acquisition succeeds, client starts daemon via `uv run`.
6. Client waits for socket readiness.
7. Client connects and initializes.
8. If stale socket exists, client removes stale socket after verifying no daemon is listening.
9. User is notified and asked whether to restart daemon.

### 5.2 Race Prevention

To prevent two NeoVim instances from spawning two daemons simultaneously, V1 uses:

* Unix socket existence check
* Lockfile acquisition
* Atomic file creation or OS-level file lock

Recommended lock path:

```text
$XDG_RUNTIME_DIR/alchemist.lock

```

Fallback:

```text
/tmp/alchemist_$USER.lock

```

Only the lock holder may spawn the daemon.

### 5.3 Stale Socket Handling

If the socket path exists but connection fails:

1. Client treats it as potentially stale.
2. Client attempts a short retry window.
3. If still unreachable, client closes/removes stale socket if permitted.
4. Client notifies user.
5. Client asks whether to restart daemon.

### 5.4 Version Compatibility

The daemon must expose both daemon version and protocol version during initialization.

Example `client/initialize` response:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "daemon_version": "0.1.0",
    "protocol_version": "1.0",
    "aider_version": "0.70.x",
    "status": "ready"
  },
  "id": "uuid"
}

```

If the Lua client and daemon protocol versions are incompatible:

* Notify the user.
* Tell the user to update and run the latest setup flow.
* Prevent agent execution until resolved.

### 5.5 Plugin Update Behavior

When the plugin updates, the client should detect daemon/script version mismatch and perform a controlled daemon restart if safe. If automatic restart fails, `:AlchemistDoctor` should present remediation steps.

### 5.6 Reference-Counted Shutdown

The daemon tracks active client channels.

* On client disconnect, decrement active client count.
* If active client count reaches zero, start a 15-second grace period.
* If no client reconnects, flush SQLite telemetry, close sockets, remove lockfiles/socket files, and exit cleanly.

### 5.7 Manual Lifecycle Commands

```vim
:AlchemistStart
:AlchemistStop
:AlchemistRestart
:AlchemistOpen
:AlchemistClose
:AlchemistDoctor
:AlchemistLogs

```

`Open` and `Close` refer to opening/closing the Alchemist UI panel, not necessarily daemon lifecycle.

---

## 6. Automated Installation and Dependency Management

### 6.1 Installation Philosophy

All runtime dependencies live inside the plugin repository or are resolved by `uv`. The daemon script ships with the plugin repository. No separate daemon artifact is downloaded in V1.

### 6.2 Plugin Manager Support

V1 should support or document:

* lazy.nvim
* packer.nvim
* vim-plug
* rocks.nvim
* manual installation

Implementation may prioritize lazy.nvim first, but the project should not structurally depend on lazy.nvim-only behavior.

### 6.3 uv Handling

If `uv` is missing:

1. Client prompts the user.
2. Prompt shows the download source.
3. Prompt shows what binary will be downloaded.
4. User must explicitly approve.
5. If approval is denied, setup stops with remediation.

No silent binary download is allowed in V1.

### 6.4 Pinned Runtime Policy

V1 pins:

* `uv` version
* Python version
* Aider version range
* LiteLLM version range
* Pydantic version range
* aiosqlite version range
* cryptography version range

### 6.5 PEP 723 Script Metadata

The daemon declares script dependencies inline.

Example:

```python
# /// script
# requires-python = "==3.12.*"
# dependencies = [
#   "aider-chat>=0.70.0,<0.71.0",
#   "litellm>=1.0.0,<2.0.0",
#   "pydantic>=2.0.0,<3.0.0",
#   "aiosqlite>=0.20.0,<1.0.0",
#   "cryptography>=42.0.0,<45.0.0",
# ]
# ///

```

Exact versions should be finalized during implementation and tied to CI.

### 6.6 Cache Corruption

If `uv` dependency cache appears corrupted, Alchemist should use the appropriate `uv` remediation path if available. If automated repair fails, `:AlchemistDoctor` should show the precise cache path and recommended cleanup command.

---

## 7. Core Python Daemon Blueprint

### 7.1 Daemon Responsibilities

The daemon owns:

* IPC server
* JSON-RPC request dispatch
* Client registry
* Project registry
* Active job state
* Aider execution orchestration
* Shadow workspace management
* LiteLLM routing/interception
* Provider key storage
* Quota accounting
* SQLite persistence
* Error normalization
* Credential redaction
* Status broadcasting

### 7.2 Process Model

V1 uses a single Python process with:

* Main asyncio event loop
* Async Unix socket server
* Thread-isolated Aider execution bridge
* In-memory quota router
* Async SQLite persistence worker

### 7.3 Async IPC Server

The daemon uses asyncio stream server primitives for Unix sockets.

Conceptual structure:

```python
async def main():
    server = await asyncio.start_unix_server(handle_client, path=socket_path)
    async with server:
        await server.serve_forever()

```

The daemon must not block the main event loop during Aider execution or long-running file operations.

### 7.4 Aider Integration

Alchemist treats Aider as a hybrid dependency:

* Use library internals where practical.
* Use subprocess fallback where library boundaries are unstable or blocking.
* Hide Aider behind a generic assistant engine API.
* Preserve all Aider repository map behavior inside the shadow workspace.
* Pin Aider tightly for V1.

### 7.5 Generic Assistant Engine Interface

The daemon should define an internal interface that isolates Alchemist from direct Aider coupling.

Conceptual interface:

```python
class AssistantEngine:
    def submit_prompt(self, request): ...
    def cancel(self, session_id): ...
    def get_status(self, session_id): ...
    def reset(self, project_id): ...

```

Aider is the only V1 engine implementation.

### 7.6 InputOutput Interception

The daemon overrides Aider's IO boundary to capture:

* Streaming output
* Status updates
* Confirmation prompts
* Selection prompts
* Text-entry prompts
* Diff lifecycle events

Raw terminal output is not parsed as protocol.

### 7.7 LiteLLM Interception

The daemon intercepts LiteLLM completion calls to:

* Inject provider keys
* Select model/provider
* Track token usage
* Rotate keys
* Enforce cooldowns
* Redact credentials from logs/errors
* Broadcast status changes

---

## 8. NeoVim Lua Client Blueprint

### 8.1 Client Responsibilities

The Lua client owns:

* User commands
* UI panels
* Statusline function
* Socket connection
* JSON-RPC framing
* Request/response correlation
* Diff review UI
* Buffer snapshotting
* Patch application to live buffers
* User notifications
* Setup flow
* Daemon bootstrap orchestration

### 8.2 State Store

The client maintains an in-memory state table including:

```lua
{
  client_id = "uuid",
  connected = true,
  daemon_version = "0.1.0",
  protocol_version = "1.0",
  active_project_id = "uuid",
  active_session_id = "uuid",
  active_job = nil,
  pending_requests = {},
  last_status = {},
  last_error = nil,
}

```

### 8.3 UI Stack

V1 may use:

* native floating windows
* nui.nvim if present or bundled as dependency
* split buffers for diff review
* NeoVim native diff mode

Diff UI should prefer native NeoVim behavior unless a lightweight plugin dependency is selected.

### 8.4 Statusline

The client exposes:

```lua
require("alchemist").status()

```

Potential states:

```text
🤖 Alchemist [offline]
🤖 Alchemist [setup required]
🤖 Alchemist [idle]
🤖 Alchemist [DeepSeek-V3 | Key #2]
🤖 Alchemist [rate limited]
🤖 Alchemist [error]

```

---

## 9. JSON-RPC 2.0 Data Contract

### 9.1 Envelope Requirements

Every request and notification params object should include where applicable:

```json
{
  "client_id": "uuid",
  "session_id": "uuid",
  "project_id": "uuid"
}

```

Request IDs are UUID strings.

### 9.2 Method Registry

#### Client → Daemon

```text
client/initialize
client/shutdown
daemon/version
daemon/health
agent/submit_prompt
agent/cancel
agent/status
agent/list_sessions
agent/reset
agent/clear
agent/add_file
agent/drop_file
agent/list_files
agent/read_only
agent/repo_map
agent/run
agent/test
agent/lint
config/set_key
config/list_providers
config/list_keys
config/delete_key

```

Note: `config/delete_key` may exist internally for cleanup/testing even if no public V1 export/delete command is advertised.

#### Daemon → Client

```text
ui/status_update
ui/diff_ready
ui/clear_prompt
agent/stream_delta
server/request_confirmation
daemon/key_swapped
daemon/error
daemon/exhausted

```

### 9.3 Initialization Request

```json
{
  "jsonrpc": "2.0",
  "method": "client/initialize",
  "params": {
    "client_id": "0ca7751c-0aa7-437f-9f94-672e9d97011a",
    "cwd": "/Users/dev/src/project",
    "nvim_pid": 12345,
    "protocol_version": "1.0"
  },
  "id": "5c06c0ef-bc78-49fa-b6a8-3ebd679c9f25"
}

```

### 9.4 Submit Prompt Request

```json
{
  "jsonrpc": "2.0",
  "method": "agent/submit_prompt",
  "params": {
    "client_id": "uuid",
    "session_id": "uuid",
    "project_id": "uuid",
    "project_path": "/Users/dev/src/utils",
    "mode": "code",
    "prompt": "Refactor compute_totals to use vector operations",
    "active_files": ["math.py"],
    "buffers": [
      {
        "path": "math.py",
        "content": "...",
        "sha256": "...",
        "modified": true
      }
    ]
  },
  "id": "uuid"
}

```

### 9.5 Status Update Notification

```json
{
  "jsonrpc": "2.0",
  "method": "ui/status_update",
  "params": {
    "client_id": "uuid",
    "session_id": "uuid",
    "project_id": "uuid",
    "status": "processing_stream",
    "model": "deepseek-v3",
    "provider": "deepseek",
    "key_index": 2,
    "tokens_per_second": 48.5,
    "phase": "file_modification"
  }
}

```

### 9.6 Streaming Delta Notification

```json
{
  "jsonrpc": "2.0",
  "method": "agent/stream_delta",
  "params": {
    "client_id": "uuid",
    "session_id": "uuid",
    "project_id": "uuid",
    "delta": "Updated compute_totals to..."
  }
}

```

### 9.7 Diff Ready Notification

```json
{
  "jsonrpc": "2.0",
  "method": "ui/diff_ready",
  "params": {
    "client_id": "uuid",
    "session_id": "uuid",
    "project_id": "uuid",
    "base_hashes": {
      "math.py": "sha256-before"
    },
    "diff": "diff --git a/math.py b/math.py\n...",
    "files_changed": ["math.py"]
  }
}

```

### 9.8 Key Swap Broadcast

```json
{
  "jsonrpc": "2.0",
  "method": "daemon/key_swapped",
  "params": {
    "provider": "deepseek",
    "model": "deepseek-v3",
    "current_key_index": 4,
    "cooldown_target": 3,
    "reason": "HTTP 429 Rate Limit Enforced"
  }
}

```

### 9.9 Server-Initiated Confirmation Request

```json
{
  "jsonrpc": "2.0",
  "method": "server/request_confirmation",
  "params": {
    "client_id": "uuid",
    "session_id": "uuid",
    "project_id": "uuid",
    "prompt_type": "boolean",
    "message": "File src/utils/math.py is not under git control. Do you want to add it?",
    "default_value": false,
    "timeout_ms": 60000
  },
  "id": "srv_req_9921a"
}

```

### 9.10 Client Response to Server-Initiated Request

```json
{
  "jsonrpc": "2.0",
  "result": {
    "confirmed": true,
    "value": "y"
  },
  "id": "srv_req_9921a"
}

```

### 9.11 Error Envelope

Use standard JSON-RPC error format with structured data.

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32000,
    "message": "PATCH_APPLY_FAILED",
    "data": {
      "retryable": false,
      "hint": "Patch application failed. Buffers were restored from snapshots. Reopen the diff or retry the prompt.",
      "client_id": "uuid",
      "session_id": "uuid",
      "project_id": "uuid"
    }
  },
  "id": "uuid"
}

```

### 9.12 Error Codes

Normalized V1 user-facing errors:

```text
NO_KEYS_CONFIGURED
PROVIDER_RATE_LIMITED
ALL_KEYS_EXHAUSTED
PATCH_APPLY_FAILED
AIDER_INTERNAL_ERROR
UV_BOOTSTRAP_FAILED
MODEL_CONTEXT_EXCEEDED
DAEMON_VERSION_MISMATCH
SHADOW_SYNC_FAILED
FRAME_TOO_LARGE
IPC_DISCONNECTED
DAEMON_UNAVAILABLE

```

Every user-facing error should include a remediation hint.

---

## 10. Provider, Model, and Routing Policy

### 10.1 Setup and Discovery

V1 provider keys are discovered through the setup panel. The user enters keys through `:AlchemistSetup`; the daemon persists them.

Supported providers and initial routing defaults are hardcoded for V1.

### 10.2 No Default Provider

Alchemist ships with no usable default provider. Agent features are disabled until keys are configured.

### 10.3 Routing Priorities

Routing policy priority:

1. Preserve free-tier quota.
2. Choose best-fit model for the prompt/task.
3. Prefer operational availability.
4. Fall back silently when the preferred model/provider is unavailable.

Silent fallback should still update statusline/status panels so users can see the active provider/model.

### 10.4 Task Routing Matrix

Initial hardcoded policy:

| Task Phase | Primary Choice | Secondary Fallback | Context / Pruning Logic |
| --- | --- | --- | --- |
| Repository indexing / mapping | Gemini Flash-class model | OpenRouter large free model | Favors long context and broad repo map generation |
| Code modification / diff creation | DeepSeek-V3-class model | Qwen Coder-class model | Uses target file segments and repo map context |
| Exploratory architecture chat | Qwen 72B-class model | Gemini Flash-class model | Generic reasoning with lower mutation risk |
| Ask/read-only question | Lowest-cost viable model | Long-context fallback | Avoids file mutation path |
| Test/lint repair | Code-focused model | General coding fallback | Includes failing output where available |

Exact provider names and model IDs should be centralized in daemon constants for V1.

### 10.5 User Configurability

V1 does not support custom model profiles. No `models = {}` setup config is exposed.

Post-V1 may add:

```lua
require("alchemist").setup({
  models = {
    edit = "...",
    chat = "...",
    map = "...",
  }
})

```

---

## 11. Quota Tracking and Key Rotation

### 11.1 Source of Truth

The master daemon maintains quota state in memory as the high-frequency source of truth.

SQLite is used for persistence, restart recovery, and historical quota tracking.

### 11.2 Initialization

Quota limits are initialized in this order:

1. Provider response headers, if available.
2. Provider-specific known heuristics.
3. Generic RPM/TPM fallback assumptions.

### 11.3 Tracked Metrics

Track provider-specific metrics where possible:

* Requests per minute
* Tokens per minute
* Requests per day
* Tokens per day
* Provider reset windows
* Cooldown deadlines
* Key availability state

Fallback metric:

* RPM only, if no token data is available

### 11.4 Rotation Strategy

Alchemist should proactively rotate keys shortly before exhaustion when quota state indicates a key is near its limit.

Reactive rotation also occurs on:

* HTTP 429
* Retryable provider quota error
* Provider-specific quota exhaustion response

### 11.5 Cooldown Strategy

Cooldown source priority:

1. `Retry-After` or equivalent provider response header.
2. Provider-specific hardcoded timeout.
3. Generic exponential backoff fallback.

### 11.6 Exhaustion Behavior

If all configured keys/providers are exhausted:

1. Stop the active operation if no safe fallback exists.
2. Notify user with `ALL_KEYS_EXHAUSTED`.
3. Offer options:
* Add another key.
* Wait until quotas reset.



### 11.7 Persistence

The SQLite quota ledger must survive daemon restarts to prevent accidental quota overuse after reboot.

### 11.8 SQLite WAL Configuration

The SQLite database should be initialized with:

```python
await db.execute("PRAGMA journal_mode = WAL;")
await db.execute("PRAGMA synchronous = NORMAL;")
await db.execute("PRAGMA busy_timeout = 5000;")

```

### 11.9 Deferred Commit Policy

Runtime metrics are batched in memory and asynchronously flushed:

* Every 2 seconds, or
* At completion of an LLM block, or
* During daemon shutdown

---

## 12. Credential Storage and Security

### 12.1 V1 Credential Policy

V1 key flow:

1. User enters key in `:AlchemistSetup`.
2. Lua sends the key to daemon over protected local IPC.
3. Daemon persists the key.
4. Lua does not retain key after setup response.
5. Keys are never retransmitted from Lua after initial setup.

Users are not allowed to use environment variables as the only supported key source in V1.

### 12.2 V1 Persistence Mechanism

Because key persistence is required and OS keyring integration is deferred, V1 uses an encrypted local vault.

Recommended path:

```text
~/.config/alchemist/vault.enc

```

The local vault is acceptable for V1 under the defined threat model.

### 12.3 Deferred Credential Backends

Post-V1:

* macOS Keychain
* Windows Credential Manager / DPAPI
* Linux Secret Service
* enterprise controls

### 12.4 Threat Model

Alchemist protects against:

* Accidental key leakage through logs/UI/errors
* Other local users reading credentials
* Casual filesystem inspection

Alchemist does **not** protect against:

* Malware running as the same user
* A compromised user account
* A malicious NeoVim plugin running in the same process

### 12.5 Machine-Bound Local Vault

For V1, the encrypted local vault derives a machine-bound key from stable OS identifiers.

Linux:

```text
/etc/machine-id
/var/lib/dbus/machine-id

```

macOS:

```text
IOPlatformUUID

```

The derived secret is passed through HKDF to produce a 32-byte AES-256-GCM key.

Conceptual derivation:

```text
K_crypt = HKDF-Expand(
  K_master,
  info = "alchemist_storage_key",
  L = 32
)

```

### 12.6 Vault Layout

Encrypted payload:

```text
┌────────────────────┬────────────────────┬────────────────────┐
│ 12-byte random IV  │ ciphertext         │ 16-byte auth tag   │
└────────────────────┴────────────────────┴────────────────────┘

```

### 12.7 File Permissions

Unix/macOS vault files must be created with owner read/write only:

```python
flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
fd = os.open(vault_path, flags, 0o600)
with os.fdopen(fd, "wb") as vault_file:
    vault_file.write(encrypted_payload)

```

### 12.8 IPC Security

The daemon must enforce:

* Unix socket mode `0600`
* Same-user validation for connecting clients
* Local-only socket path
* No remote TCP listener in V1

### 12.9 Secret Handling in Python

Credential-bearing models must use Pydantic secret types where practical.

```python
from pydantic import BaseModel, SecretStr

class ProviderKey(BaseModel):
    provider: str
    api_key: SecretStr

```

### 12.10 Logging and Redaction

Logs are disabled by default. When logs are enabled for debugging, credentials must be redacted.

The daemon must sanitize:

* Python logs
* LiteLLM callbacks
* JSON-RPC diagnostic payloads
* SQLite error ledger entries
* tracebacks shown to clients

### 12.11 No Credential Export/Delete Commands in Public V1 UI

V1 does not expose credential export/delete as user-facing commands. Internal test/helper methods may exist but must not be documented as user workflows.

---

## 13. Privacy, Telemetry, and Local Ledger

### 13.1 Privacy Policy

All telemetry is local-only.

Alchemist will not send usage analytics to an external service in V1.

### 13.2 Persisted Telemetry

SQLite may persist:

* Token counts
* Provider names
* Model names
* Request timestamps
* Quota state
* Cooldown state
* Normalized error codes

### 13.3 Explicitly Not Persisted

The daemon must not persist:

* Raw prompts
* Code snippets
* Full file contents
* API keys in plaintext
* Authorization headers
* Raw provider request payloads

### 13.4 Retention

Quota/telemetry metrics are retained indefinitely in V1.

### 13.5 Logs vs Log Panel

Disk logs are disabled by default.

The in-editor log panel may persist normalized operational errors and remediation hints, but must not include raw prompts, code content, or credentials.

---

## 14. Shadow Workspace Engine

### 14.1 Purpose

Aider operates primarily against filesystem-backed files and Git repositories. NeoVim users often have unsaved in-memory buffers. The shadow workspace engine reconciles these models by executing Aider in an isolated copy of the project and returning diffs to the live editor.

### 14.2 Location

V1 shadow workspace root:

```text
.git/alchemist/shadow

```

### 14.3 Project Partitioning

Each project root maps to one shadow workspace. Because V1 supports only one active project/job at a time, no concurrent worktree branching is required.

Post-V1 may use per-operation worktrees or branches.

### 14.4 Materialization Strategy

V1 uses a full filesystem copy of the project into the shadow workspace.

Large repositories are handled the same as small repositories in V1. Performance optimizations are deferred.

### 14.5 Ignore Rules

Alchemist follows Aider behavior for:

* `.gitignore`
* `.aiderignore`
* binary file exclusion
* repo map inclusion
* file selection behavior

If Aider exposes a reliable helper for ignore processing, Alchemist should reuse it.

### 14.6 Unsaved Buffers

Before execution, the Lua client sends all relevant in-memory buffers to the daemon. The daemon writes those contents into the shadow workspace before invoking Aider.

Unsaved file handling should mirror `aider.nvim` behavior as closely as practical.

### 14.7 Pre-Flight Sync

Before `agent/submit_prompt`, the client captures:

* Active file list
* Relevant buffer contents
* Buffer file paths
* SHA-256 content hashes
* Modified state

The daemon writes the provided buffer contents into the shadow workspace.

### 14.8 Shallow Git Sandbox

The shadow workspace maintains its own Git repository. This allows Aider to use Git history, repo map mechanics, and diff generation without mutating the user's real repository history.

### 14.9 Execution Flow

```text
NeoVim live buffers
      │
      │ pre-flight sync with content hashes
      ▼
Shadow workspace copy
      │
      │ Aider execution
      ▼
Shadow git commit / mutation
      │
      │ git diff / patch extraction
      ▼
JSON-RPC diff payload
      │
      ▼
NeoVim diff approval UI

```

### 14.10 Diff Generation

After Aider completes, the daemon calculates a unified diff from the shadow repository.

Preferred:

```shell
git diff HEAD~1

```

If Aider exposes a better native diff API, use Aider behavior.

### 14.11 Rejection Flow

On rejection:

1. Client closes diff UI.
2. Daemon rewinds the shadow workspace.
3. Prefer Aider-native undo/reset behavior.
4. Fallback:

```shell
git reset --hard HEAD~1

```

### 14.12 Acceptance Flow

On acceptance:

1. Client verifies optimistic hashes.
2. Client applies patch to live buffers.
3. Client writes buffers to disk.
4. Client notifies daemon.
5. Daemon updates shadow baseline.

### 14.13 Cleanup

V1 cleans shadow workspaces on daemon exit.

Post-V1 may preserve shadow workspaces for debugging.

---

## 15. Diff Review, Patch Application, and Conflict Handling

### 15.1 Diff Review UI

Diffs are rendered in either:

* Native NeoVim diff mode
* Lightweight plugin-based diff UI
* Scratch buffer fallback

### 15.2 Multi-File Diffs

V1 supports multi-file diff review to the extent supported by the chosen diff UI and patch application path.

### 15.3 Hunk-Level Application

Hunk-level application is not a custom V1 requirement. If the native diff plugin/viewer supports it, Alchemist may expose it. Otherwise full-diff apply is acceptable for V1.

### 15.4 File Operations

File creation, rename, deletion, and mode changes should follow Aider behavior. If Aider does not handle a case cleanly, fallback to `git apply` semantics where possible.

### 15.5 Optimistic Locking

Before pre-flight sync, the client records SHA-256 hashes for affected buffers.

Before applying returned diff:

1. Recompute hashes.
2. Compare against `base_hashes` in diff payload.
3. If hashes match, proceed.
4. If hashes differ, open native diff/conflict resolution mode or notify user.

### 15.6 Transactional Apply

Patch application must be transactional at the client layer.

Before applying:

* Snapshot all affected live buffers.
* Record cursor/window state where practical.

If any file fails to apply:

1. Restore all modified buffers from snapshots.
2. Do not write partial changes to disk.
3. Emit `PATCH_APPLY_FAILED`.
4. Show remediation hint.

### 15.7 Patch Application Priority

Patch application priority:

1. Aider-native mechanism, if available and safe.
2. `git apply` against a temporary index/worktree.
3. Lua-side buffer patching as fallback.

---

## 16. Interactive Upstream Prompting Protocol

### 16.1 Problem

Aider may issue blocking prompts such as confirmation, text input, or selection. The daemon must not allow those synchronous prompts to block the main asyncio IPC loop.

### 16.2 Thread-Isolated Bridge

Aider execution runs in a worker thread. Prompt requests are bridged to the main event loop using thread-safe futures.

Conceptual model:

```python
import asyncio

class DaemonInputOutput:
    def yes_no_prompt(self, prompt, default="n"):
        future = asyncio.run_coroutine_threadsafe(
            self.rpc_server.send_client_request(
                self.client_channel,
                "server/request_confirmation",
                {
                    "prompt_type": "boolean",
                    "message": prompt,
                    "default_value": default,
                    "timeout_ms": 60000,
                },
            ),
            self.main_loop,
        )
        return future.result(timeout=60.0)

```

### 16.3 Routing Rule

Server-initiated prompts always route to the NeoVim client that started the operation.

Other connected clients cannot answer prompts for that operation in V1.

### 16.4 Prompt Types

Supported prompt types:

```text
boolean
text
selection

```

### 16.5 Timeout Behavior

V1 uses a fixed 60-second timeout. It is not configurable in V1.

Timeout defaults are conservative:

* Reject structural mutations.
* Allow safe read-only operations where possible.
* Cancel operation if no safe default exists.

### 16.6 Client Disconnect

If the initiating NeoVim client closes while Aider is waiting:

* The prompt is dropped.
* The operation resolves with conservative fallback.
* The daemon must not hang.

### 16.7 Blocking Scope

Interactive prompts block only the current session/job, not the entire daemon.

Because V1 only has one active job globally, this distinction primarily protects daemon health and UI responsiveness.

### 16.8 Response Caching

Prompt responses may be cached for the duration of a single operation to avoid repeatedly asking the same question.

---

## 17. Concurrency and Session Model

### 17.1 V1 Global Serialization

V1 permits only one active agent job globally.

If another client attempts to start a job while one is active:

* Return `AGENT_BUSY` or equivalent normalized error.
* Include the current job summary.
* Suggest waiting or cancelling the active job if it belongs to the current client.

### 17.2 Sessions

Sessions exist as in-memory identifiers for protocol correlation but are not persisted across daemon restarts in V1.

### 17.3 Running Job Visibility

Users can view the current active job through:

```vim
:AlchemistStatus

```

A client should not see full details of jobs started by another client in V1. It may see only a generic busy state.

### 17.4 Cancellation

`agent/cancel` and `:AlchemistCancel` are supported if the underlying Aider execution path can be interrupted safely.

If true cancellation is unavailable, Alchemist should:

* Mark cancellation requested.
* Stop streaming updates.
* Prevent applying pending diffs.
* Let backend execution wind down safely.

---

## 18. Error Handling and Recovery

### 18.1 User-Facing Errors

Alchemist normalizes operational errors that affect user workflows.

Required V1 errors:

```text
NO_KEYS_CONFIGURED
PROVIDER_RATE_LIMITED
ALL_KEYS_EXHAUSTED
PATCH_APPLY_FAILED
AIDER_INTERNAL_ERROR
UV_BOOTSTRAP_FAILED
MODEL_CONTEXT_EXCEEDED
DAEMON_VERSION_MISMATCH
SHADOW_SYNC_FAILED
DAEMON_UNAVAILABLE
IPC_DISCONNECTED
FRAME_TOO_LARGE
AGENT_BUSY

```

### 18.2 Remediation Hints

Every error shown to the user must include a suggested next action.

Examples:

```text
NO_KEYS_CONFIGURED: Run :AlchemistSetup and add an API key.
ALL_KEYS_EXHAUSTED: Add another key or wait for provider quota reset.
PATCH_APPLY_FAILED: Buffers were restored. Reopen the diff or retry.
DAEMON_VERSION_MISMATCH: Update the plugin and rerun setup.

```

### 18.3 UI Presentation

Errors are surfaced via:

* NeoVim notification
* In-editor Alchemist log panel

Disk logs remain disabled by default.

### 18.4 Failed Operations

Failed operation behavior should mimic Aider where possible.

### 18.5 Daemon Crash Recovery

If daemon crashes:

1. Client detects IPC disconnect.
2. Client attempts auto-restart.
3. Client reinitializes.
4. Pending operations follow Aider-like failure behavior.

V1 does not guarantee replay of in-flight requests after crash.

---

## 19. Platform Support

### 19.1 V1 Platforms

Primary:

```text
macOS

```

Secondary:

```text
Linux

```

### 19.2 Deferred Windows Support

Windows support is post-V1 and should eventually include:

* Native Windows NeoVim
* WSL NeoVim
* Possible WSL-to-Windows daemon interop
* Windows Terminal workflows
* Named pipes
* Windows paths with spaces
* Path normalization via a library
* Windows ACL hardening
* DPAPI credential protection

### 19.3 Path Normalization

V1 should still centralize path normalization behind a utility layer so Windows support can be added later without rewriting protocol contracts.

---

## 20. Configuration Model

### 20.1 Minimal Required Config

```lua
require("alchemist").setup()

```

### 20.2 No Advanced Config in V1

V1 does not expose advanced setup options such as:

* custom provider policy
* custom model routing
* shadow workspace location
* UI provider selection
* local vault toggles
* auto-download policy overrides

### 20.3 No Project-Local Config in V1

V1 does not support:

```text
.alchemist.json
.alchemist.lua

```

Therefore, no project trust prompt is required in V1.

---

## 21. Testing and Verification Strategy

### 21.1 Test Frameworks

Python:

```text
pytest
pytest-asyncio

```

NeoVim/Lua:

```text
vusted
headless nvim tests

```

### 21.2 Fake Provider

A fake LiteLLM-compatible provider is required for deterministic tests.

It should simulate:

* successful completions
* streaming chunks
* token usage headers
* rate limits
* retry-after headers
* provider errors
* context-limit errors

### 21.3 Rate Limit Tests

Tests must cover:

* HTTP 429 handling
* retry-after cooldown
* key rotation
* all-keys-exhausted behavior
* SQLite persistence across daemon restart

### 21.4 Shadow Workspace Tests

Use real temporary Git repositories to verify:

* project copy
* pre-flight sync
* unsaved buffer materialization
* Aider/dummy mutation
* diff generation
* acceptance baseline update
* rejection reset
* cleanup on daemon exit

### 21.5 UI Tests

Headless NeoVim tests should verify:

* setup panel opens
* missing keys block chat
* statusline function returns valid string
* diff panel opens
* apply/reject keymaps dispatch expected RPC calls
* server prompt UI resolves boolean/text/selection requests

### 21.6 Security Tests

Tests must verify:

* API keys are not written to logs
* API keys are not included in JSON-RPC diagnostic errors
* API keys are masked in model dumps
* vault file permissions are restrictive
* socket permissions are restrictive

### 21.7 CI Matrix

V1 CI:

```text
macOS
Linux

```

Windows CI is deferred.

### 21.8 Acceptance Standard

The V1 acceptance standard is functional Aider parity for the selected V1 command subset, with deterministic daemon/client behavior and no credential leakage.

---

## 22. Roadmap Integration Status

The following phases from the Alchemist.nvim Product Roadmap have been fully integrated into this working specification:

* **Phase 1: JSON-RPC Contract**
* **Phase 2: Python Daemon**
* **Phase 3: Shadow Workspace**
* **Phase 4: NeoVim Lua Client**

*(Phases 5 and beyond are actively being developed or are deferred for future versions.)*

---

## 23. Final Architectural Principles

Alchemist V1 is governed by these principles:

1. **Aider parity first.** When uncertain, mimic Aider behavior.
2. **No manual file editing for setup.** All setup occurs through UI.
3. **Protocol before polish.** Stabilize JSON-RPC before UI expansion.
4. **One job at a time.** Avoid concurrency complexity in V1.
5. **Local-first privacy.** No remote analytics or prompt persistence.
6. **Credential hygiene by default.** Never leak keys into logs, errors, telemetry, or UI.
7. **Shadow before mutation.** Never let the agent directly mutate live buffers without approval.
8. **Simple config.** `require("alchemist").setup()` should be enough.
9. **macOS-first V1.** Build and validate the primary workflow before platform expansion.
10. **Future-proof boundaries.** Hide Aider behind an engine interface and path/platform utilities.
