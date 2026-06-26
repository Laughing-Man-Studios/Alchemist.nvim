Here is the fully updated `Roadmap.md` file, incorporating the missing security bounds for Phase 4. You can copy this directly into your editor:

# Alchemist.nvim: Product Roadmap

### **Phase 1–3: Core Engine & Synchronization (Completed)**

These foundational elements are already established, providing the architecture needed to safely manage file state and user interactions without blocking the main event loop.

* **Phase 1:** Multi-Instance Concurrency & SQLite WAL Ledger
* **Phase 2:** Buffer vs. Disk Synchronization (The Shadow Workspace)
* **Phase 3:** Interactive Upstream Prompting Bridge

---

### **Phase 4: Key Storage Security Bounds (Active Phase)**

This phase locks down credential hygiene and ensures API keys are never exposed in plaintext, fulfilling the V1 requirement for a hardened local vault.

* **Machine-Bound Secret Derivation:** Implement the hardware-bound master secret derivation using stable OS identifiers (e.g., `/etc/machine-id` on Linux, `IOPlatformUUID` on macOS).
* **HKDF Implementation:** Build the high-density key derivation math to generate $K_{\text{master}}$ and $K_{\text{crypt}}$:

$$Seed = \text{SystemUUID} \parallel \text{MachineID} \parallel \text{PlatformSalt}$$

$$K_{\text{master}} = \text{HKDF-Extract}(\text{Salt}=\text{None}, \text{IKM}=Seed)$$

$$K_{\mathrm{crypt}} = \mathrm{HKDF\!-\!Expand}\!\left(K_{\mathrm{master}},\; \mathrm{info} = \texttt{"alchemist\_storage\_key"},\; L = 32 \right)$$

* **Encrypted Local Ledger:** Build the AES-256-GCM encryption payload structure (12-byte IV, ciphertext, 16-byte auth tag) and enforce strict 0600 file permissions upon creation.
* **IPC & Memory Security Boundaries:** Enforce 0600 permissions and same-user validation on the Unix socket, and ensure the Lua client permanently drops credentials from memory after the initial setup transmission.
* **In-Memory Typestate Masking:** Enforce Pydantic `SecretStr` typing across all inbound JSON-RPC credential models so that debugging outputs return masked values.
* **Egress Sanitization:** Build the regex logging scrubbers and LiteLLM callback interceptors to replace bearer strings with `[REDACTED_CREDENTIAL]` before they hit the disk, the SQLite error ledger, or the JSON-RPC diagnostic payloads.

---

### **Phase 5: Quota State Machine & LLM Routing Policy**

With credentials secured, this session will focus on maximizing free-tier API usage without triggering blocking database locks.

* **In-Memory Quota Tracking:** Build the atomic Python dictionary to handle high-frequency Request-Per-Minute (RPM) and Token-Per-Minute (TPM) tracking.
* **Deferred SQLite Commits:** Implement the background asyncio worker that batches memory metrics and writes them to the SQLite WAL ledger every 2 seconds, or at the end of an LLM block.
* **Failover & Broadcast Mechanics:** Hook into LiteLLM `429` errors to trigger automatic key rotation, mark keys as `Cooldowned`, and instantly broadcast a `daemon/key_swapped` JSON-RPC packet to all connected Lua clients.
* **Task Routing Matrix:** Hardcode the fallback logic to route repository mapping to Gemini Flash-class models, code modifications to DeepSeek-V3, and exploratory chats to Qwen 72B-class models.

---

### **Phase 6: The `uv` Bootstrap & Daemon Lifecycle**

This phase implements the "zero-config" promise, ensuring the Lua client can seamlessly spawn and manage the Python environment.

* **Dependency Bootstrapping:** Write the Lua routine to check the system path for `uv` and prompt the user for download approval if missing.
* **Daemon Master Election:** Implement the lockfile acquisition logic (`alchemist.lock`) to prevent race conditions when multiple NeoVim instances open simultaneously.
* **Inline Metadata Handling:** Finalize the PEP 723 inline script requirements (`# /// script`) inside the Python daemon to ensure `uv` handles virtual environment isolation perfectly on the first run.
* **Reference-Counted Shutdown:** Implement the daemon lifecycle tracker that decrements active clients, triggering a 15-second grace period before securely flushing telemetry and terminating the process.

---

### **Phase 7: NeoVim Lua UI & State Management**

This session pulls the backend capabilities into the editor, translating JSON-RPC packets into native Vim experiences.

* **UI Dispatcher & Modals:** Wire up the `nui.nvim` floating text buffers to handle setup input (`:AlchemistSetup`) and server-initiated confirmation dialogs.
* **Statusline Integration:** Export the `require("alchemist").status()` Lua function to expose the active global ticker (e.g., `🤖 Alchemist [DeepSeek-V3 | Key #3]`).
* **Diff Review Execution:** Finalize the split-viewport rendering for the unified patches returned from the shadow workspace, mapping `<Leader>ca` to apply and `<Leader>cr` to reject.
* **Error Normalization Presentation:** Map the backend string errors (e.g., `ALL_KEYS_EXHAUSTED`, `PATCH_APPLY_FAILED`) to clean user-facing notifications with actionable remediation hints.

---

### **Phase 8: Post-V1 Hardening (Deferred Scope)**

Once V1 is stable, reliable, and functional on macOS/Linux, these modules can be planned for subsequent releases.

* **OS-Native Keyrings:** Transition from the localized vault to `Security.framework` on macOS and `dbus-fast` Secret Service on Linux.
* **Windows Architecture:** Implement named pipe IPC (`\\.\pipe\alchemist_$USER.pipe`), ACL hardening via SIDs, and DPAPI credential protection.
* **Concurrent Job Queues:** Move beyond the single global job limit to allow per-project concurrency constraints and isolated shadow worktrees.
