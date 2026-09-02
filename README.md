# Alchemist.nvim

### Zero-config, native Neovim AI coding assistant with Aider orchestration and quota-aware LLM routing

---

## Overview

**Alchemist.nvim** is a zero-configuration, native Neovim plugin that integrates the Aider agent core and LiteLLM SDK directly into your editor via a lightweight, headless Python background daemon. Managed transparently through Astral's `uv`, Alchemist coordinates single or multiple Neovim instances through a centralized, master daemon over local Unix domain socket IPC. It translates structured JSON-RPC 2.0 frames into native Vim buffers, streaming windows, and split-diff review workflows without pseudo-TTY scraping or raw terminal multiplexing.

The plugin provides full Aider-style coding capabilities while abstracting away Python virtual environments, manual dependency setup, API key management, model selection, quota limits, and provider failover. By executing agent instructions inside an isolated shadow Git repository, Alchemist ensures that your live code and unsaved buffers remain completely untouched until you review and explicitly accept unified diffs.

### Key Features

* **Zero-Config Daemon Lifecycle:** Automatic dependency resolution, master election via lockfiles, and background daemon spawning powered by Astral's `uv`. No manual virtualenvs or pip installs required.
* **Isolated Shadow Workspace:** Executes agent actions inside a sandbox (`.git/alchemist/shadow`) with pre-flight in-memory buffer synchronization, leaving your working tree clean.
* **Interactive & Split Diff Review:** Side-by-side native Neovim diff comparisons for proposed changes with one-key apply (`<Leader>ca`) and reject (`<Leader>cr`) bindings.
* **Optimistic Locking & Transactional Patches:** Compares live SHA-256 buffer hashes against pre-flight states before applying edits, automatically rolling back on write conflicts or failures.
* **Free-Tier Quota Optimization & Key Rotation:** Real-time in-memory tracking of RPM/TPM usage, proactive key swapping, and automatic failover on HTTP 429 rate limits.
* **Strict Credential Hygiene:** Encrypted local key storage with immediate in-memory dropping of API credentials in the Lua client and strict log/diagnostic sanitization.
* **Interactive Upstream Prompting:** Asynchronous handling of upstream Aider confirmation, text, and selection dialogs directly inside Neovim without blocking the event loop.
* **Statusline & Diagnostics Integration:** Exported statusline helper (`require("alchemist").status()`) with live model and rotation state, paired with built-in `:AlchemistDoctor` and `:AlchemistLogs` inspectors.

---

## Installation Guide

Follow these steps to install and set up Alchemist.nvim.

### Prerequisites

* **Neovim** >= 0.9.0
* **Git** (installed and available on your `$PATH`)
* **astral-sh/uv** (optional; Alchemist will prompt and install `uv` automatically if not found)
* **nui.nvim** (recommended for floating UI inputs; falls back to native UI if omitted)

### Step 1: Install via Plugin Manager

#### Using [lazy.nvim](https://github.com/folke/lazy.nvim)

```lua
{
  "Laughing-Man-Studios/Alchemist.nvim",
  dependencies = {
    "MunifTanjim/nui.nvim", -- Optional: for enhanced UI popups
    "nvim-lua/plenary.nvim", -- Optional: for running the test harness
  },
  config = function()
    require("alchemist").setup()
  end,
}
```

#### Using [packer.nvim](https://github.com/wbthomason/packer.nvim)

```lua
use {
  "Laughing-Man-Studios/Alchemist.nvim",
  requires = { "MunifTanjim/nui.nvim" },
  config = function()
    require("alchemist").setup()
  end,
}
```

#### Using [vim-plug](https://github.com/junegunn/vim-plug)

```vim
Plug 'MunifTanjim/nui.nvim'
Plug 'Laughing-Man-Studios/Alchemist.nvim'

" In your init.lua or after plug#end():
lua require('alchemist').setup()
```

### Step 2: Configure Statusline (Optional)

Add the statusline component to your configuration (e.g., in [lualine.nvim](https://github.com/nvim-lualine/lualine.nvim)):

```lua
require('lualine').setup {
  sections = {
    lualine_x = {
      {
        function()
          return require("alchemist").status()
        end,
      }
    }
  }
}
```

### Step 3: Run Initial Setup & Add Provider Keys

Open Neovim and run `:AlchemistSetup` to configure your API keys (e.g., Gemini, DeepSeek, Qwen, OpenAI, Anthropic). Once at least one valid key is saved, agent features become immediately available.

---

## User Manual

Alchemist.nvim transforms Neovim into an AI pair-programmer through intuitive commands, dedicated buffers, and safe patch application flows.

### 1. Basic Agent Workflows

* **Refactoring and Editing Code:**
  Open your project files and run `:AlchemistCode <prompt>` or `:AlchemistCode`. Alchemist syncs all open and unsaved buffers to the shadow workspace, instructs the agent, and streams the output to a side split panel.
* **Asking Questions & Researching:**
  Use `:AlchemistAsk <question>` or `:AlchemistChat <question>` to query the assistant about your codebase. In `ask` mode, the agent operates in read-only mode and will not mutate code.
* **Architectural Discussions:**
  Use `:AlchemistArchitect <prompt>` for complex system design, high-level refactor planning, and multi-file architectural reviews.
* **Cancelling Requests:**
  If an operation takes too long or you want to abort, run `:AlchemistCancel`.

### 2. Diff Review and Patch Acceptance

When code modifications complete, Alchemist generates a unified diff and presents it in side-by-side native Neovim diff mode:

* **Apply Diff (`<Leader>ca` or `:AlchemistApply`):**
  Verifies that no files were altered in the live editor since diff generation, transactionally writes the changes across all affected buffers, saves them to disk, and updates the shadow baseline.
* **Reject Diff (`<Leader>cr` or `:AlchemistReject`):**
  Discards the proposed changes, closes the diff view, and rewinds the shadow workspace Git sandbox to the pre-prompt baseline.
* **Reopen Diff View:**
  If you closed the diff window without applying or rejecting, run `:AlchemistDiff` to reopen the pending review.

### 3. Context and File Management

Control what context the assistant sees using dedicated context commands:

* `:AlchemistAdd [path]` — Adds the current buffer (or specified file path) to editable context.
* `:AlchemistReadOnly [path]` — Adds a file to agent context as read-only.
* `:AlchemistDrop [path]` — Removes a file from active agent context.
* `:AlchemistFiles` — Displays a scratch buffer listing all currently tracked editable and read-only files.
* `:AlchemistMap` / `:AlchemistMapRefresh` — Inspects or forces a refresh of the repository structure map.

### 4. Lifecycle, Diagnostics, and Logs

* `:AlchemistSetup` — Opens the floating configuration dialog to add or update LLM provider API keys with concealed input.
* `:AlchemistDoctor` — Opens the diagnostic panel showing daemon status, socket paths, protocol handshake versions, and environment health.
* `:AlchemistLogs` — Inspects the in-memory privacy-safe operational log entries.
* `:AlchemistStart` / `:AlchemistStop` / `:AlchemistRestart` — Manually manages the background daemon process and socket connections.
* `:AlchemistOpen` / `:AlchemistClose` — Opens or hides the streaming chat and output split panel.

### 5. Debugging and Development

Alchemist provides comprehensive debugging capabilities for both development and troubleshooting:

#### Debug Configuration

Configure debug settings in your Neovim configuration:

```lua
-- Enable basic debugging with default settings (debugpy on port 5678)
vim.g.alchemist_debug = true

-- Or use enhanced configuration for full control
vim.g.alchemist_debug = {
  enabled = true,           -- Enable debug mode
  port = 5678,             -- Debug server port (default: 5678)
  debugger = "debugpy",     -- Debugger: "debugpy", "pdb", or "ipdb"
  wait_for_client = true,  -- Wait for debugger client connection
  log_level = "info",      -- Log level: "debug", "info", "warning", "error"
  lua_debug = false,       -- Enable Lua client debugging (future)
}
```

#### Debug Commands

* **`:AlchemistDebugStart [port]`** — Start the daemon in debug mode. Optionally specify a custom port.
  ```vim
  :AlchemistDebugStart        " Use default configuration
  :AlchemistDebugStart 9999  " Start on custom port
  ```

* **`:AlchemistDebugStop`** — Stop the debug session and clean up configuration.

* **`:AlchemistDebugStatus`** — Display current debug configuration, port, debugger type, and session status.

* **`:AlchemistDebugLogs`** — Show debug-specific logs with timestamps, severity levels, and context.

* **`:AlchemistDoctor`** — Now includes debug status information alongside regular diagnostics.

#### Debugging Alternative Debuggers

Alchemist supports multiple Python debuggers:

* **debugpy** (recommended): Default debugger
* **pdb**: Standard Python debugger
* **ipdb**: IPython-enhanced debugger

Configure your preferred debugger:

```lua
vim.g.alchemist_debug = {
  enabled = true,
  debugger = "pdb",  -- or "ipdb"
  wait_for_client = false
}
```

#### Troubleshooting Tips

1. **Connection Issues**: If the debugger isn't connecting:
   - Verify the port is available: `lsof -i :5678`
   - Check firewall settings
   - Ensure your debugger client is configured for the same port

2. **Daemon Not Starting**: Run `:AlchemistDebugLogs` to see detailed error messages.

3. **Configuration Problems**: Use `:AlchemistDebugStatus` to verify your current debug configuration.

4. **Performance Issues**: Reduce log level to "warning" or "error" for less verbose output:
   ```lua
   vim.g.alchemist_debug = {
     enabled = true,
     log_level = "warning"
   }
   ```

#### Development Workflow

For contributors working on Alchemist itself:

1. **Lua Client Development**: Use standard Neovim debugging tools
2. **Python Daemon Development**: Use `:AlchemistDebugStart` with your preferred debugger
3. **Integration Testing**: Use `:AlchemistDebugStatus` to verify debug state
4. **Error Analysis**: Use `:AlchemistDebugLogs` for detailed debugging information


---
