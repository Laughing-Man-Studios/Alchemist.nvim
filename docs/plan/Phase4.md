# Phase 4: NeoVim Lua Client Implementation Plan

This phase brings the backend capabilities into the editor, translating JSON-RPC packets into native Vim experiences. The focus is on wiring up the core architecture, establishing the daemon socket connection, and building the user-facing UI for setup, status, and diff review.

---

## 1. Core Architecture & Daemon Lifecycle Orchestration

The Lua client must seamlessly manage the Python daemon's lifecycle, ensuring zero-config initialization without requiring manual environment setup.

### Requirements

* Expose a minimal setup function via `require("alchemist").setup()` with no required options for V1.
* Keep the client surface canonical to **Alchemist** naming; do not retain legacy placeholder command/function names.
* Implement the full V1 command vocabulary from the specification, grouped as:
  * Lifecycle/UI: `:AlchemistSetup`, `:AlchemistOpen`, `:AlchemistClose`, `:AlchemistStart`, `:AlchemistStop`, `:AlchemistRestart`, `:AlchemistDoctor`, `:AlchemistLogs`, `:AlchemistStatus`.
  * Agent: `:AlchemistChat`, `:AlchemistAsk`, `:AlchemistCode`, `:AlchemistArchitect`, `:AlchemistCancel`, `:AlchemistDiff`, `:AlchemistApply`, `:AlchemistReject`, `:AlchemistReset`, `:AlchemistClear`.
  * File/context: `:AlchemistAdd`, `:AlchemistReadOnly`, `:AlchemistDrop`, `:AlchemistFiles`, `:AlchemistMap`, `:AlchemistMapRefresh`.
  * Execution/support: `:AlchemistRun`, `:AlchemistTest`, `:AlchemistLint`, `:AlchemistCommit`.
  * Inspection: `:AlchemistModels`, `:AlchemistSettings`.
* Make `:AlchemistOpen` / `:AlchemistClose` control the UI panel, not daemon lifecycle.
* Compute the daemon socket path, defaulting to `$XDG_RUNTIME_DIR/alchemist.sock` with a fallback to `/tmp/alchemist_$USER.sock`.
* Treat the Unix socket as local-only and validate the expected restrictive-permission/same-user boundary from the client side where observable.
* Check the system path for `uv` during bootstrap; if missing, show what will be downloaded and require explicit user approval before proceeding. Never silently download.
* Prevent race conditions by acquiring `alchemist.lock` before spawning the daemon via `uv run`; only the lock holder may spawn.
* Handle stale sockets by retrying briefly, verifying no daemon is listening before cleanup, then notifying the user.
* On first use, connect if possible; otherwise bootstrap the daemon, initialize the protocol, and automatically enter setup when the daemon reports `NO_KEYS_CONFIGURED`.
* Never require manual Python, virtualenv, dependency, or config-file setup from the user.
* On daemon/plugin version mismatch, notify the user and prevent agent execution until the client and daemon are compatible. When a plugin update detects a script/daemon mismatch, attempt a controlled restart; route persistent failures to `:AlchemistDoctor`.
* Centralize path normalization behind a utility boundary so future Windows support does not require protocol/UI rewrites.
* Distinguish connection loss from ordinary daemon shutdown and support client-side reconnect/reinitialize behavior after daemon crashes without promising replay of in-flight requests.

### Deliverables

* `init.lua` exposing the public setup and statusline API.
* `commands.lua` to register the complete V1 `:Alchemist*` command surface.
* `bootstrap.lua` containing the `uv` check, explicit approval flow, lockfile acquisition, daemon spawning, version checks, stale socket recovery, and crash/reconnect handling.
* `paths.lua` or equivalent utility for centralized socket/project/path normalization.
* Tests verifying safe daemon startup, stale socket cleanup, version negotiation, first-run setup gating, plugin/daemon mismatch handling, daemon crash recovery, and explicit `uv` download prompting.

---
---

## 2. State Management & JSON-RPC 2.0 Dispatch

The client must maintain an accurate local representation of the active session and route newline-delimited JSON frames over the local Unix domain socket.

### Requirements

* Implement an NDJSON parser and writer for JSON-RPC 2.0 over the Unix domain socket.
* Buffer incrementally until `
`, JSON-decode one frame at a time, reject malformed JSON with a JSON-RPC parse error, and never parse terminal/ANSI output as protocol.
* Enforce the 16 MiB maximum frame size and surface `FRAME_TOO_LARGE` with a remediation hint.
* Maintain an in-memory state table tracking `client_id`, `active_project_id`, `active_session_id`, `active_job`, `connected`, `daemon_version`, `protocol_version`, `pending_requests`, `last_status`, and `last_error`.
* Inject `client_id`, `session_id`, and `project_id` where applicable rather than blindly adding fields to methods that do not use them.
* Generate UUID request IDs and correlate responses deterministically, including server-initiated requests that use their own IDs.
* Implement connection/disconnection state transitions, request cleanup on disconnect, and safe reconnect/reinitialize behavior.
* During `client/initialize`, send the expected client metadata (`client_id`, `cwd`, `nvim_pid`, `protocol_version`) and validate daemon version, protocol version, Aider version, and readiness.
* Route daemon-to-client notifications for `ui/status_update`, `ui/diff_ready`, `ui/clear_prompt`, `agent/stream_delta`, `server/request_confirmation`, `daemon/key_swapped`, `daemon/error`, and `daemon/exhausted`.
* Route the complete specified client-to-daemon method set through a centralized dispatch layer, including agent, file/context, execution, and config methods.
* Reject unsupported/unknown methods cleanly and preserve a centralized method registry so future Aider parity additions do not break the public API.
* Ensure all RPC callbacks run through NeoVim-safe scheduling and never block the main Vim event loop.

### Deliverables

* `rpc.lua` handling the low-level Unix socket connection, byte buffering, NDJSON framing, initialize handshake, disconnect/reconnect, and request correlation.
* `state.lua` providing the centralized Vim-scheduled client state store.
* `methods.lua` or equivalent centralized method/notification registry.
* Envelope/correlation utility for UUID generation and context injection.
* Headless tests verifying parse errors, frame limits, request/response correlation, server-initiated requests, initialization/version validation, notification routing, disconnect handling, and reconnect behavior.

---
---

## 3. UI, Interactive Prompts & Setup Flow

Alchemist strictly relies on interactive UI flows rather than configuration files for tasks like adding API keys and handling blocking Aider prompts.

### Requirements

* Implement the setup UI to capture provider API keys via `:AlchemistSetup`, passing them to the daemon while ensuring the Lua client drops credential references after the initial transmission.
* Do not echo credentials in normal UI, notifications, errors, statusline text, debug output, or serialized client state.
* Reflect the zero-config first-run behavior: if the daemon reports no usable keys, guide the user into setup and keep agent features gated until at least one key is configured.
* Utilize `nui.nvim` floating text buffers if present/bundled, with native floating windows as the fallback.
* Keep `:AlchemistOpen` / `:AlchemistClose` independent from daemon start/stop.
* Wire `server/request_confirmation` to support `boolean`, `text`, and `selection` prompts.
* Route server-initiated prompts only to the NeoVim client that started the active operation.
* Honor the fixed 60-second V1 prompt timeout and handle conservative fallback when the user does not answer.
* Handle initiating-client disconnects while a prompt is pending: resolve the UI request without hanging the daemon and do not allow another client to answer it.
* Support prompt response caching for the duration of a single operation where appropriate.
* Add native NeoVim UI for incremental `agent/stream_delta` output so users can see ongoing Aider activity instead of only receiving the final diff.
* Keep a clean separation between temporary prompt/stream buffers and the main editing buffers.

### Deliverables

* `ui/setup.lua` managing the `:AlchemistSetup` interactive flow and secret-input behavior.
* `ui/prompts.lua` handling boolean/text/selection server requests, timeout, disconnect, and response dispatch.
* `ui/chat.lua` or equivalent for streaming agent output/status presentation.
* Headless tests confirming setup gating, secret handling, server-initiated UI requests, timeout/disconnect behavior, and streaming updates.

---
---

## 4. Statusline Integration & Error Normalization

Users need immediate, passive visibility into the agent's status, active model, and clear paths to remediate operational failures.

### Requirements

* Export a `require("alchemist").status()` Lua function returning a short, render-safe string suitable for integrations such as `lualine`.
* Represent at least the specified V1 states: `offline`, `setup required`, `idle`, active model/key, `rate limited`, and `error`.
* Consume `ui/status_update` in real time, including provider, model, key index, processing phase, and tokens-per-second where present.
* Update status when a `daemon/key_swapped` notification arrives so the user can see failover without needing to reopen a panel.
* Map the full required V1 error set to clean user-facing notifications and normalized remediation hints, including `NO_KEYS_CONFIGURED`, `PROVIDER_RATE_LIMITED`, `ALL_KEYS_EXHAUSTED`, `PATCH_APPLY_FAILED`, `AIDER_INTERNAL_ERROR`, `UV_BOOTSTRAP_FAILED`, `MODEL_CONTEXT_EXCEEDED`, `DAEMON_VERSION_MISMATCH`, `SHADOW_SYNC_FAILED`, `FRAME_TOO_LARGE`, `IPC_DISCONNECTED`, `DAEMON_UNAVAILABLE`, and `AGENT_BUSY`.
* Ensure every user-facing error includes a next action and never exposes raw credentials, prompts, code payloads, or provider authorization headers.
* Provide `:AlchemistDoctor` and `:AlchemistLogs` panels for normalized operational diagnostics. Disk logs remain disabled by default; the in-editor panel must remain privacy-safe.
* Surface the daemon's generic busy state to other NeoVim clients without exposing another client's full job details.
* Make crash recovery visible and actionable when reconnect/reinitialize succeeds or fails.

### Deliverables

* `status.lua` implementing the status ticker and state translations.
* `diagnostics.lua` handling error normalization, Vim notifications, `:AlchemistDoctor`, and `:AlchemistLogs`.
* Tests validating all documented status states, key-swap transitions, error/remediation mappings, busy-state privacy, and disconnect/recovery presentation.

---
---

## 5. Diff Review & Patch Application Flow

Translating the daemon's shadow workspace diffs into a safe, transactional Vim review experience is the final critical path for the user workflow.

### Requirements

* Implement split-viewport rendering for unified patches returned in `ui/diff_ready`.
* Support multi-file diffs, including file creation, deletion, rename, and mode-change metadata where supplied by the backend.
* Prefer native NeoVim diff behavior; use a lightweight plugin if selected, with a scratch-buffer fallback.
* Keep hunk-level custom editing out of V1 scope; full-diff application is acceptable unless the chosen diff UI already supports safer hunk operations.
* Map `<Leader>ca` to apply and `<Leader>cr` to reject the pending diff.
* Make the diff UI safe when no diff is pending, when a diff is replaced, or when an operation has been cancelled.
* Before applying, recompute live-buffer SHA-256 hashes and compare them with the `base_hashes` from the `ui/diff_ready` payload.
* On optimistic-lock mismatch, do not mutate live buffers; instead open conflict/diff resolution UI or show a clear remediation message.
* Snapshot all affected live buffers before applying and record cursor/window state where practical.
* Apply transactionally: if any file fails, restore all affected buffers, do not write partial changes to disk, and emit `PATCH_APPLY_FAILED`.
* Use the specification's patch application priority: Aider-native mechanism when safe, then `git apply` against a temporary index/worktree, then Lua-side buffer patching.
* After successful acceptance, write updated buffers to disk and notify the daemon so the shadow baseline can be advanced.
* On rejection, close the UI and notify the daemon so the shadow workspace can be rewound/reset.
* Prevent a cancelled job, disconnected daemon, or stale diff from being applied.

### Deliverables

* `ui/diff.lua` handling split/multi-file rendering, lifecycle state, and apply/reject keymaps.
* `patch.lua` managing optimistic locking, transactional snapshots, patch application, conflict detection, and post-apply synchronization.
* `hash.lua` providing deterministic SHA-256 hashing for in-memory buffer contents.
* Tests verifying multi-file rendering, file operations, optimistic-lock failure, transactional rollback, apply/reject dispatch, cancelled/stale diff protection, and successful shadow-baseline notification.

---
---

## 6. Suggested File Layout

Building upon the Lua architecture, organize the client module as follows:

```text
lua/
  alchemist/
    init.lua                 # Setup, Statusline API, and configuration
    commands.lua             # :Alchemist* user command registry
    bootstrap.lua            # uv check, lockfile, daemon spawning
    rpc.lua                  # Unix socket, NDJSON reader/writer
    state.lua                # In-memory client state store
    methods.lua              # JSON-RPC method/notification registry
    paths.lua                # Canonical path/socket normalization
    ui/
      setup.lua              # Floating window setup / key entry
      prompts.lua            # Dispatcher for server_request_confirmation
      diff.lua               # Split-viewport diff review
      diagnostics.lua        # Log panels, error normalization, doctor
      chat.lua               # Streaming agent output/status presentation
    utils/
      patch.lua              # Optimistic locking and transactional buffer apply
      hash.lua               # Buffer SHA-256 generation

```

---

## 7. Phase 4 Acceptance Criteria

Phase 4 is complete when:

* Running `require("alchemist").setup()` with no options resolves canonical paths, checks for `uv`, obtains explicit approval before any download, acquires `alchemist.lock`, starts/connects to the daemon, and initializes the JSON-RPC session without blocking NeoVim.
* First-run behavior matches the specification: if no provider keys are configured, setup is opened/guided automatically and agent execution remains gated until configuration exists.
* The full V1 command surface is registered and mapped to the appropriate RPC/UI actions, including lifecycle, agent, file/context, execution/support, and inspection commands.
* `:AlchemistOpen` / `:AlchemistClose` operate as UI controls and do not inadvertently stop/start the daemon.
* The client validates `daemon_version`, `protocol_version`, and readiness during `client/initialize`, and blocks execution on incompatibility.
* Daemon crashes/disconnects are detected, the client can reconnect/reinitialize or present a deterministic recovery path, and in-flight requests are not incorrectly replayed.
* NDJSON framing correctly handles partial reads, malformed JSON, request/response correlation, server-initiated requests, and the 16 MiB frame limit.
* Every routed RPC callback is NeoVim-safe and does not block the main event loop.
* The `:AlchemistSetup` command captures provider keys through a secret UI, transmits them once, removes credential references from client state, and never renders them through status/error/log paths.
* `ui/status_update`, `agent/stream_delta`, and `daemon/key_swapped` produce the expected live UI/status changes.
* `require("alchemist").status()` correctly represents at least `offline`, `setup required`, `idle`, active-model/key, `rate limited`, and `error`.
* Required normalized errors include actionable remediation hints and never contain raw credentials, prompts, code content, or provider authorization headers.
* `:AlchemistDoctor` and `:AlchemistLogs` show privacy-safe normalized diagnostics; disk logs remain disabled by default.
* Server-initiated `boolean`, `text`, and `selection` prompts route only to the initiating client, honor the fixed 60-second timeout, recover from disconnects, and return the correct JSON-RPC response.
* Diffs from `ui/diff_ready` correctly render multi-file changes and relevant file operations; `<Leader>ca` applies and `<Leader>cr` rejects.
* Apply verifies `base_hashes` before mutation, protects against stale/cancelled diffs, snapshots affected buffers, applies transactionally, and restores all snapshots on failure without partial disk writes.
* Optimistic-lock conflicts are surfaced without mutating live buffers, and successful acceptance notifies the daemon so the shadow baseline can advance.
* UI/client tests run under headless NeoVim using the selected test framework and cover setup, missing-key gating, statusline, diff apply/reject, and server prompt UI.
* The Phase 4 client passes the specification's V1 acceptance standard: deterministic daemon/client behavior, functional parity for the selected Aider command subset, and no credential leakage.