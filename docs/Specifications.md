# High-Level Architecture Specification: Alchemist.nvim (Automated Hybrid Daemon)

This specification outlines the architecture for a zero-config, native NeoVim AI assistant plugin. It wraps the `aider` agent core and `litellm` SDK into a single headless Python background daemon, managed invisibly via `uv`. The system maximizes free-tier LLM API usage through smart key rotation, adaptive token/quota management, and task-specific routing while coordinating seamlessly across multiple concurrent editor instances.

---

## 1. System Topology & Communication Model

The application uses a **Single System-Wide Master Daemon / Multi-Client Architecture** to prevent resource contention. Multiple lightweight **UI/Client Layers** (NeoVim/Lua instances) communicate with a single stateful **Orchestration/Proxy Layer** (Python Daemon) via local Inter-Process Communication (IPC).

```
┌────────────────────────┐               ┌────────────────────────┐
│   NeoVim Instance #1   │               │   NeoVim Instance #2   │
│  (Lua UI / Client)     │               │  (Lua UI / Client)     │
└───────────┬────────────┘               └───────────┬────────────┘
            │                                        │
            │  JSON-RPC 2.0 over Unix Socket / Pipe  │
            └───────────────────┬────────────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ Central Master Daemon  │ ◄─── (In-Memory Quota Router)
                    │ (Single Python Process)│
                    └───────────┬────────────┘
                                │  aiosqlite (WAL Mode)
                                ▼
                    ┌────────────────────────┐
                    │  Shared SQLite Ledger  │
                    └────────────────────────┘

```

* **Transport Mechanism:** Local IPC streams (Unix Domain Sockets on macOS/Linux; Named Pipes on Windows) managed asynchronously via NeoVim's `vim.loop` (libuv).
* **Socket Paths:** * **Unix/macOS:** `$XDG_RUNTIME_DIR/alchemist.sock` or `/tmp/alchemist_$USER.sock`
* **Windows:** `\\.\pipe\alchemist_$USER.pipe`


* **Protocol:** Structured JSON-RPC 2.0. Raw terminal parsing or ANSI character scraping is strictly prohibited.
* **Lifecycle & Master Election:** The NeoVim client handles daemon spawning via a race-preventative bootstrap protocol:
1. On initialization, the client attempts to connect to the designated IPC socket.
2. **Connection Success:** The client registers its process identity (PID) and current working directory via an `initialize` handshake.
3. **Connection Failure:** The client elects itself as the bootstrap host, executes `uv run free_aider_daemon.py --master` asynchronously to initialize the system-wide socket server, and then establishes the client pipe connection.



---

## 2. Component Blueprints

### A. Core Central Python Daemon (`free_aider_daemon.py`)

The daemon runs an asynchronous IPC server (`asyncio.start_server`) that multiplexes requests from multiple editor instances into a single event loop.

* **PEP 723 Script Metadata:** Declares dependencies inline at the top of the file, enabling `uv` to handle instant virtual isolation on first execution.
* **Aider Core Wrap:** Inherits and overrides `aider.io.InputOutput` to capture stream tokens, intercepting structural writes and packaging them into clean JSON-RPC notifications.
* **Intelligent Traffic Manager:** Intercepts outgoing `litellm.completion()` calls globally across all active sessions to dynamically swap API endpoints, inject keys, track token velocity, and enforce cross-instance synchronization.

### B. NeoVim Lua Client

A thin, unblocked UI wrapper that drives the user interaction layer.

* **State Store:** Maintains an in-memory Lua table tracking current active session status, daemon connectivity, pending operations, and contextual error states.
* **UI Managers:** Floating text buffers driven by `nui.nvim` or native floating viewports that handle chat prompts, system metrics, and interactive diff confirmation modules.

---

## 3. Automated Installation Blueprint (The Zero-Config Flow)

To eliminate installation friction, dependency management and runtime bootstrapping are completely hidden behind an automated, lazy-loaded hook.

```
[User Installs Plugin] ──> [Lazy.nvim Build Step] ──> [Check for 'uv' Binary]
                                                               │
                                                               ├──> If Missing: Pull Standalone 'uv'
                                                               │
                                                               └──> Execute: 'uv run free_aider_daemon.py'
                                                                    (Auto-downloads Python, Aider, LiteLLM)

```

| Step | Responsible Layer | Technical Implementation Action |
| --- | --- | --- |
| **1. Hook Lifecycle** | NeoVim (`lazy.nvim`) | Triggers the `build` or `setup` configuration step on plugin pull. |
| **2. Engine Check** | Lua Host | Scans the system path for `uv`. If absent, downloads the native platform-specific single binary directly from GitHub releases to `stdpath("data")`. |
| **3. Dependencies** | Python Metadata | Employs inline PEP 723 declarations:<br>

<br>`# /// script`<br>

<br>`# dependencies = ["aider-chat>=0.70.0", "litellm>=1.0.0", "pydantic>=2.0.0", "aiosqlite>=0.20.0"]`<br>

<br>`# ///` |
| **4. Process Execution** | Lua Process Host | Boots the master daemon (if elected) via `uv run --quiet free_aider_daemon.py --master`. `uv` isolates and caches the script requirements silently on initial boot. |

---

## 4. JSON-RPC 2.0 Data Contract Examples

### Client Request: Submit Coding Prompt

```json
{
  "jsonrpc": "2.0",
  "method": "agent/submit_prompt",
  "params": {
    "project_path": "/Users/dev/src/utils",
    "prompt": "Refactor the compute_totals function to use vector operations",
    "active_files": ["math.py"]
  },
  "id": 1
}

```

### Server Notification: Inner Working Transparency Update

```json
{
  "jsonrpc": "2.0",
  "method": "ui/status_update",
  "params": {
    "status": "processing_stream",
    "model": "deepseek-v3",
    "key_index": 2,
    "tokens_per_second": 48.5,
    "phase": "file_modification"
  }
}

```

### Server Broadcast: Real-Time Key Cooldown Synchronization

```json
{
  "jsonrpc": "2.0",
  "method": "daemon/key_swapped",
  "params": {
    "current_key_index": 4,
    "cooldown_target": 3,
    "reason": "HTTP 429 Rate Limit Enforced"
  }
}

```

---

## 5. Key Rotation & Quota State Machine

To guarantee a premium experience on free-tier APIs, the central daemon isolates high-frequency operational tracking in memory while leveraging a shared database for background persistence.

### High-Frequency State Tracking & Persistence Safeties

* **In-Memory Quota Layer:** The Master Daemon maintains the absolute source of truth for trailing-window Request-Per-Minute (RPM) and Token-Per-Minute (TPM) allocation inside an atomic Python dictionary. This removes the latency penalty of disk access during token generation loops.
* **Deferred Database Commit:** Stream metrics are batched in memory and written to the SQLite ledger asynchronously every 2 seconds or at the immediate conclusion of a complete LLM block generation.
* **SQLite Connection Optimizations:** To completely eliminate database write-locks (`database is locked` exceptions), the shared database is initialized with strict structural pragmas:

```python
await db.execute("PRAGMA journal_mode = WAL;")
await db.execute("PRAGMA synchronous = NORMAL;")
await db.execute("PRAGMA busy_timeout = 5000;")

```

### Custom Routing Policy Matrix

The daemon routes processing across providers depending on task dimensions to minimize free-tier exhaustion:

| Task Phase | Primary Choice | Secondary Fallback | Context / Pruning Logic |
| --- | --- | --- | --- |
| **Repository Indexing & Mapping** | Gemini 2.5 Flash | OpenRouter (Large Free) | Maps whole project skeleton; takes advantage of Gemini's 1M token free-tier structure. |
| **Code Modification / Diff Creation** | DeepSeek-V3 | Qwen-2.5-Coder (via Groq) | Isolates target file segments using Tree-sitter to reduce prompt payload. |
| **Exploratory Architecture Chat** | Qwen-2.5-72B | Gemini 2.5 Flash | Generic code conversation with low token footprints. |

### Real-Time Key State Propagation Protocol

When a key encounters an HTTP `429` error via a `litellm` event hook, the master daemon applies a multi-tenant failover sequence:

1. **Instant Evaluation:** Marks the failing key as `Cooldowned` (e.g., for 60 seconds) inside the daemon's in-memory register.
2. **Global Broadcast:** Instantly sends a `daemon/key_swapped` JSON-RPC packet down *all* active IPC channels.
3. **UI Synchronization:** Connected NeoVim instances process the message on their background socket loops, immediately updating their respective `FreeAiderStatus()` strings. Statusline objects update globally across all open terminal windows, avoiding secondary stale key executions.

---

## 6. Buffer vs. Disk Synchronization Protocol (The Shadow Workspace Engine)

To resolve conflicts between NeoVim's in-memory buffer states and Aider's file-system-driven modification patterns, the system enforces a strict isolation protocol using independent shadow environments *partitioned by project*.

```
[NeoVim Buffer State] ───(JSON-RPC: Pre-Flight Sync)───> [Project Shadow Workspace]
                                                                  │
                                                           [Execute Aider]
                                                                  │
[Diff Approval Panel] <───(JSON-RPC: Unified Patch)────── [Shadow Git Diff]

```

### A. Isolation Mechanics

* **Session Partitioning:** The central daemon instantiates isolated shadow workspaces for each distinct project path received during client connection handshakes (e.g., hidden inside `.git/alchemist/shadow/` or a system temporary directory uniquely hashed by project root path).
* **Shallow Git Sandbox:** Each isolated shadow workspace maintains its own localized Git repository. This fulfills Aider’s functional reliance on Git history tracking, line hooks, and repository map graphs without injecting unapproved metadata into the user's production git repository history.

### B. Asynchronous Synchronization Lifecycle

1. **Pre-Flight Synchronization (Client-to-Daemon):** Before passing an execution prompt to an LLM, the client captures the raw in-memory string payloads of all target buffers (including unsaved modifications) and passes them to the daemon via JSON-RPC. The daemon writes these directly onto the shadow directory's files.
2. **Execution Sandbox:** The daemon executes the native `aider` engine strictly within the isolated shadow directory. Aider modifies the shadow workspace files and commits those changes internally to the shadow Git tracking ledger.
3. **Diff Calculation & Return:** Once execution finishes, the daemon executes a local `git diff HEAD~1` within the shadow repository to capture a programmatic unified diff, which is packaged inside a JSON-RPC response envelope and transmitted to the client.

### C. Specific Friction Mitigation Strategies

* **The Diff Approval Paradox:** The received unified diff is securely rendered inside an ephemeral scratch viewport managed by `nui.nvim`.
* **On Acceptance (`<Leader>ca`):** The Lua client applies the unified patch content directly to live editor buffers using `vim.api.nvim_buf_set_lines()` and flushes changes to the host disk via `:w`.
* **On Rejection (`<Leader>cr`):** The client closes the diff viewport, and the daemon runs a `git reset --hard HEAD~1` within the shadow sandbox to sync internal state back to alignment with the active editor state.


* **Out-of-Sync Buffers (Optimistic Locking):** To prevent race conditions if a user modifies text during generation, the client transmits a content hash during pre-flight sync. Upon receiving the diff payload, the client re-verifies the buffer hash. If the hashes do not match, the application triggers a three-way merge via `vim.diff()` or alerts the user before applying modifications.

---

## 7. User Interface Flows

* **Setup Panel (Configless Integration):** Typing `:FreeAiderSetup` spawns a tabbed configuration dashboard utilizing floating buffers. Users input keys into text widgets, which are instantly transmitted down the IPC pipe to update the master daemon's secure configuration layer.
* **Statusline Component:** The plugin exposes a Lua function `FreeAiderStatus()` returning a string formatted for popular statusline systems (e.g., `lualine.nvim`). It shows an active global ticker:
> `🤖 FreeAider [DeepSeek-V3 | Key #3]`


* **Diff Approval Panel:** Visualized utilizing split viewports or overlay layers within scratch buffers. It maps simple single-keystroke shortcuts to apply changes (`<Leader>ca`) or reject modifications (`<Leader>cr`).

---

## 8. Risks and Mitigation Strategies

* **Risk:** Upstream structural modifications or system prompt alterations to `aider-chat` break backend parsing models.
* *Mitigation:* Pin dependency ranges directly inside the PEP 723 inline script metadata configuration blocks (e.g., `aider-chat>=0.70.0,<0.71.0`) and handle ecosystem updates deterministically through rigorous regression checks.


* **Risk:** High-intensity processing files block standard input/output loops or freeze background processes.
* *Mitigation:* Decouple background networking, file processing, and API orchestration loops from the central server execution pipeline using native Python `asyncio` loop abstractions.


* **Risk:** Orphaned master processes remain alive after editor instances close, consuming resources.
* *Mitigation:* **Reference-Counted Shutdown Protocol**. Every connected client maintains an active stream channel. When a channel breaks, the daemon decrements its internal counter. If `active_clients == 0`, a **15-second grace period** begins. If no reconnection occurs, the daemon flushes telemetry data, closes socket files, and terminates cleanly via `sys.exit(0)`.



---

## 9. Tools and Technologies Stack

### NeoVim Lua Client (UI & Lifecycle Layer)

* **nui.nvim:** Drives structural UI layers, configuration modules, and floating split views for diff confirmations.
* **plenary.nvim:** Powers asynchronous process spawning and environment verification utilities during the master election phase.
* **lualine.nvim:** Integrates statusline tickers to propagate live backend health updates across all workspace panes.
* **vim.loop (libuv):** Manages local domain sockets and named pipes natively, handling multi-client JSON-RPC messaging streams without stalling the editor's main rendering thread.

### Python Orchestration Daemon (Backend Engine)

* **aider-chat:** Provides repository mapping, token processing, and file structural mutation engines.
* **litellm:** Standardizes API signatures across multiple upstream providers, managing operational failovers, key translation logic, and stream formatting hooks.
* **Pydantic:** Enforces data contract strictness for all inbound and outbound JSON-RPC 2.0 payloads, eliminating silent formatting failures across runtime interfaces.
* **asyncio:** Orchestrates multiplexed multi-client servers, token streams, and background timeout engines concurrently.

### Storage & Execution Management

* **uv (by Astral):** Handles isolated dependency resolutions and interpreter bootstrapping natively, ensuring zero-config environments.
* **aiosqlite:** Provides an asynchronous interface for logging historical metrics, telemetry trends, and structural configuration persistence with WAL synchronization pragmas.

### Testing & Verification

* **pytest & pytest-asyncio:** Tests state machine boundaries, concurrency behaviors, and multi-client connection handshakes under simulated `429` error conditions.
* **vusted:** Executes headless NeoVim continuous integration passes to test UI layouts, keymaps, and JSON-RPC pipe stability.
