# High-Level Architecture Specification: Free-Tier AI Agent System (NeoVim + Automated Hybrid Daemon)

This specification outlines the architecture for a zero-config, native NeoVim AI assistant plugin. It wraps the `aider` agent core and `litellm` SDK into a single headless Python background daemon, managed invisibly via `uv`. The system maximizes free-tier LLM API usage through smart key rotation, adaptive token/quota management, and task-specific routing.

---

## 1. System Topology & Communication Model

The application is split into a lightweight **UI/Client Layer** (NeoVim/Lua) and a stateful **Orchestration/Proxy Layer** (Python Daemon).

```
┌────────────────────────┐              JSON-RPC               ┌────────────────────────┐
│  NeoVim Lua Client     │ ◄─────────────────────────────────► │  Python Hybrid Daemon  │
│  (UI, State Rendering) │         (Stdin / Stdout)            │  (Aider Core, LiteLLM) │
└────────────────────────┘                                     └───────────┬────────────┘
                                                                           │
                                                                           ▼
                                                               ┌────────────────────────┐
                                                               │  SQLite/JSON Storage   │
                                                               │  (Keys, Quotas, Logs)  │
                                                               └────────────────────────┘


```

* **Transport Mechanism:** Standard Input/Output (Stdin/Stdout) asynchronous streams managed via NeoVim's `vim.loop` (libuv) or `vim.fn.jobstart()`.
* **Protocol:** Structured JSON-RPC 2.0. No raw terminal parsing or ANSI character scraping is allowed.
* **Lifecycle:** The NeoVim client automatically spawns the background daemon on plugin initialization and sends a SIGTERM sequence to cleanly shut down the daemon when NeoVim exits.

---

## 2. Component Blueprints

### A. Core Python Daemon (`free_aider_daemon.py`)

The daemon acts as a headless server. Instead of rendering a terminal UI, it hooks into `aider.core` to consume commands and stream pristine token objects back to NeoVim.

* **PEP 723 Script Metadata:** The script declares its dependencies inline at the top of the file, allowing `uv` to handle instant virtual isolation on first execution.
* **Aider Core Wrap:** Inherits and overrides `aider.io.InputOutput` to redirect standard textual outputs into formatted JSON objects.
* **Intelligent Traffic Manager:** Intercepts outgoing `litellm.completion()` calls to dynamically swap API endpoints, inject keys, and track token velocity.

### B. NeoVim Lua Client

A clean UI wrapper that abstracts away configurations.

* **State Store:** Maintains an in-memory Lua table tracking current model status, daemon health, active operations, and errors.
* **UI Managers:** Floating text buffers (`nui.nvim` or standard floating windows) that act as conversation inputs and diff confirmation modules.

---

## 3. Automated Installation Blueprint (The Zero-Config Flow)

To eliminate configuration friction, dependency tracking is outsourced to Astral’s `uv` engine via a lazy-loaded build and run hook.

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
| **1. Hook Lifecycle** | NeoVim (`lazy.nvim`) | Triggers the `build` or `setup` configuration step. |
| **2. Engine Check** | Lua Host | Scans the system path for `uv`. If absent, downloads the native platform-specific single binary directly from GitHub releases to `stdpath("data")`. |
| **3. Dependencies** | Python Metadata | Python script utilizes inline PEP 723 definitions:<br>

<br>

<br>`# /// script`<br>

<br>

<br>`# dependencies = ["aider-chat>=0.70.0", "litellm>=1.0.0"]`<br>

<br>

<br>`# ///` |
| **4. Process Execution** | Lua Process Host | Boots the daemon asynchronously via `uv run --quiet free_aider_daemon.py`. `uv` isolates and caches libraries silently on the initial boot. |

---

## 4. JSON-RPC 2.0 Data Contract Examples

All communication flows through strict structural envelopes.

### Client Request: Submit Coding Prompt

```json
{
  "jsonrpc": "2.0",
  "method": "agent/submit_prompt",
  "params": {
    "prompt": "Refactor the compute_totals function to use vector operations",
    "active_files": ["src/utils/math.py"]
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

---

## 5. Key Rotation & Quota State Machine

To recreate a premium experience on free-tier APIs, the daemon maintains a local storage ledger (SQLite or local encrypted JSON) tracking key status and rate limitations.

```
               ┌────────────────────────┐
               │    Key Pool Request    │
               └───────────┬────────────┘
                           │
             ┌─────────────┴─────────────┐
    Yes      ▼                           ▼      No
┌────────────┴──────────┐    ┌───────────┴──────────┐
│ Key Cool? (RPM/TPM ok)│    │ Key Expired/Throttled│
└────────────┬──────────┘    └───────────┬──────────┘
             │                           │
             ▼                           ▼
┌────────────┴──────────┐    ┌───────────┴──────────┐
│   Execute Completion  │    │ Cool down (X seconds)│
└───────────────────────┘    │ Shift to Next Key    │
                             └──────────────────────┘


```

### Custom Routing Policy Matrix

The system optimizes economics and stability across different task dimensions:

| Task Phase | Primary Choice | Secondary Fallback | Context/Pruning Logic |
| --- | --- | --- | --- |
| **Repository Indexing & Mapping** | Gemini 2.5 Flash | OpenRouter (Large Free Context) | Map whole project skeleton; take advantage of Gemini's 1M token free-tier structure. |
| **Code Modification / Diff Creation** | DeepSeek-V3 | Qwen-2.5-Coder (via Groq/SambaNova) | Isolates target file segments using Tree-sitter to reduce prompt payload. |
| **Exploratory Architecture Chat** | Qwen-2.5-72B | Gemini 2.5 Flash | Generic code conversation with low token footprints. |

### Quota Tracking Mechanism

1. **Rate Limit Trailing Windows:** The daemon tracks Request-Per-Minute (RPM) and Token-Per-Minute (TPM) count per key.
2. **Adaptive Failover:** If an API endpoint yields an HTTP `429` error, the daemon flags that specific key for a calculated cooldown duration (e.g., 60 seconds), updates the database, and automatically restarts the network request using the next available key pool slot before Aider crashes.

---

## 6. User Interface Flows

* **Setup Panel (Configless Integration):** Typing `:FreeAiderSetup` spawns a tabbed configuration layout using standard floating buffers. Users paste keys into input boxes which are piped instantly to the daemon database. No file editing is required.
* **Statusline Component:** The plugin exposes a Lua function `FreeAiderStatus()` that returns a string formatted for popular statusline elements (e.g., `lualine.nvim`). It presents an active ticker showing current system health:

> `🤖 FreeAider [DeepSeek-V3 | Key #3]`

* **Diff Approval Panel:** When code changes are broadcast from the daemon, the plugin splits the active text viewport to generate standard side-by-side or inline diff layers with simple single-keystroke keymaps to accept (`<Leader>ca`) or reject (`<Leader>cr`) changes.

---

## 7. Risks and Mitigation Strategies

* **Risk:** System prompt changes or structural updates to upstream `aider-chat` break internal imports.
* **Mitigation:** Lock the dependency version ranges explicitly inside the PEP 723 inline script metadata header (e.g., `aider-chat>=0.70.0,<0.71.0`) and test upgrades deterministically.
* **Risk:** Persistent blocking of standard input loops on heavy text processing frames.
* **Mitigation:** Implement all background networking and task orchestration inside the Python daemon using native asynchronous libraries (`asyncio`). The communication thread must remain decoupled from the main execution queue.

---

## 8. Tools and Technologies Stack

### NeoVim Lua Client (UI & Lifecycle Layer)

* **nui.nvim:** Provides the foundational, highly customizable UI components needed for the zero-config setup panel and interactive diff confirmation buffers.
* **plenary.nvim:** Supplies essential asynchronous utilities and job control wrappers, making the management of the background daemon lifecycle more robust than raw `vim.fn` calls.
* **lualine.nvim:** Serves as the primary integration point for the health and active model ticker, leveraging its widespread adoption in the NeoVim community.
* **vim.loop (libuv):** Natively powers the non-blocking Stdin/Stdout communication pipes, ensuring the NeoVim editor thread remains entirely unblocked during heavy JSON-RPC message passing.

### Python Orchestration Daemon (Backend Engine)

* **aider-chat:** Functions as the core repository mapping and code modification engine, heavily customized via the overridden `InputOutput` class.
* **litellm:** Standardizes the API request formats across disparate providers (DeepSeek, Google, OpenRouter, Groq), enabling the dynamic routing and failover logic.
* **Pydantic:** Enforces strict data validation for all incoming and outgoing JSON-RPC 2.0 payloads, guaranteeing the data contract between Python and Lua never silently fails.
* **asyncio:** Manages concurrent API requests, token streaming, and network cooldown timers natively without locking the daemon process.

### Storage & Execution Management

* **uv (by Astral):** Acts as the underlying dependency resolver and execution environment, bypassing the need for standard virtual environments (`venv`) and fulfilling the zero-config installation mandate.
* **aiosqlite:** Provides an asynchronous, lightweight SQLite interface to act as the primary local ledger for tracking token velocity, RPM/TPM quotas, and automated key rotation logic.

### Testing & Verification

* **pytest & pytest-asyncio:** Facilitates deep testing of the Python daemon's state machine, specifically mocking HTTP `429` errors to verify the quota failover mechanics.
* **vusted:** Runs headless NeoVim instances in continuous integration to test the Lua client's UI rendering, keymaps, and JSON-RPC dispatching.
