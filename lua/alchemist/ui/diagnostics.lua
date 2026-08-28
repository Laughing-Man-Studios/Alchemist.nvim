local M = {}

local state = require("alchemist.state")

local ERROR_MAP = {
  NO_KEYS_CONFIGURED = {
    level = vim.log.levels.WARN,
    hint = "Run :AlchemistSetup and add an API key.",
  },
  PROVIDER_RATE_LIMITED = {
    level = vim.log.levels.WARN,
    hint = "Provider is rate-limited. Waiting for cooldown.",
  },
  ALL_KEYS_EXHAUSTED = {
    level = vim.log.levels.ERROR,
    hint = "Add another key via :AlchemistSetup or wait for provider quota reset.",
  },
  PATCH_APPLY_FAILED = {
    level = vim.log.levels.ERROR,
    hint = "Buffers were restored from snapshots. Reopen the diff or retry.",
  },
  AIDER_INTERNAL_ERROR = {
    level = vim.log.levels.ERROR,
    hint = "Aider encountered an internal error. Run :AlchemistDoctor.",
  },
  UV_BOOTSTRAP_FAILED = {
    level = vim.log.levels.ERROR,
    hint = "uv environment setup failed. Run :AlchemistRestart.",
  },
  MODEL_CONTEXT_EXCEEDED = {
    level = vim.log.levels.WARN,
    hint = "Prompt is too long for the selected model. Reduce context.",
  },
  DAEMON_VERSION_MISMATCH = {
    level = vim.log.levels.ERROR,
    hint = "Update the plugin and run :AlchemistRestart.",
  },
  SHADOW_SYNC_FAILED = {
    level = vim.log.levels.ERROR,
    hint = "Shadow workspace sync failed. Save your buffers and retry.",
  },
  FRAME_TOO_LARGE = {
    level = vim.log.levels.ERROR,
    hint = "IPC frame exceeded 16 MiB limit. This is likely a bug.",
  },
  IPC_DISCONNECTED = {
    level = vim.log.levels.WARN,
    hint = "Connection to daemon lost. Run :AlchemistStart.",
  },
  DAEMON_UNAVAILABLE = {
    level = vim.log.levels.ERROR,
    hint = "Daemon is not running. Start it with :AlchemistStart.",
  },
  AGENT_BUSY = {
    level = vim.log.levels.WARN,
    hint = "Agent is busy. Cancel with :AlchemistCancel or wait.",
  },
}

local log_entries = {}
local MAX_LOG_ENTRIES = 100

local function add_log(level, code, message, hint)
  table.insert(log_entries, {
    timestamp = os.date("%Y-%m-%d %H:%M:%S"),
    level = level,
    code = code or "",
    message = message,
    hint = hint or "",
  })
  if #log_entries > MAX_LOG_ENTRIES then
    table.remove(log_entries, 1)
  end
end

--- Handle an error from the daemon (daemon/error notification or RPC error)
---@param err table {code: any, message: any, data?: table, retryable?: boolean, hint?: string}
function M.handle_error(err)
  local code = err.message or err.code or "UNKNOWN"
  local mapping = ERROR_MAP[code]
  local level = mapping and mapping.level or vim.log.levels.ERROR
  local hint = (err.data and err.data.hint) or (mapping and mapping.hint) or ""

  local safe_message = tostring(code)
  if err.data and err.data.hint then
    safe_message = safe_message .. ": " .. err.data.hint
  elseif hint ~= "" then
    safe_message = safe_message .. ": " .. hint
  end

  add_log(level, tostring(code), safe_message, hint)
  vim.notify("[Alchemist] " .. safe_message, level)
end

--- Show :AlchemistDoctor panel
function M.show_doctor()
  local s = state.get()
  local lines = {
    "=== Alchemist Doctor ===",
    "",
    "Connection:     " .. (s.connected and "Connected" or "Disconnected"),
    "Daemon Version: " .. (s.daemon_version or "unknown"),
    "Protocol:       " .. (s.protocol_version or "unknown"),
    "Aider Version:  " .. (s.aider_version or "unknown"),
    "Client ID:      " .. s.client_id,
    "Session ID:     " .. (s.active_session_id or "none"),
    "Project ID:     " .. (s.active_project_id or "none"),
    "Setup Required: " .. (s.setup_required and "Yes" or "No"),
    "",
    "Active Job:     " .. (s.active_job and "Yes" or "None"),
    "Pending Diff:   " .. (s.pending_diff and "Yes" or "None"),
    "Pending RPCs:   " .. vim.tbl_count(s.pending_requests),
    "",
    "uv Available:   " .. (vim.fn.executable("uv") == 1 and "Yes" or "No"),
    "Socket Path:    " .. require("alchemist.paths").socket_path(),
    "Daemon Script:  " .. require("alchemist.paths").daemon_script(),
    "",
  }

  if s.last_error then
    table.insert(lines, "Last Error: " .. (s.last_error.code or s.last_error.message or "unknown"))
    if s.last_error.hint then
      table.insert(lines, "  Hint: " .. s.last_error.hint)
    end
  end

  M._show_scratch_buffer("alchemist-doctor", lines)
end

--- Show :AlchemistLogs panel
function M.show_logs()
  local lines = { "=== Alchemist Logs ===", "" }
  if #log_entries == 0 then
    table.insert(lines, "  (no log entries)")
  else
    for _, entry in ipairs(log_entries) do
      table.insert(lines, string.format("[%s] %s %s",
        entry.timestamp, entry.code, entry.message))
      if entry.hint ~= "" then
        table.insert(lines, "  -> " .. entry.hint)
      end
    end
  end
  M._show_scratch_buffer("alchemist-logs", lines)
end

--- Show agent status
function M.show_status(result)
  local lines = {
    "=== Agent Status ===",
    "",
    "Status: " .. (result.status or "unknown"),
  }
  if result.active_job then
    table.insert(lines, "Active Job: Yes")
  else
    table.insert(lines, "Active Job: None")
  end
  M._show_scratch_buffer("alchemist-status", lines)
end

--- Show file listing
function M.show_files(result)
  local lines = { "=== Agent Files ===", "" }
  if result.editable and #result.editable > 0 then
    table.insert(lines, "Editable:")
    for _, f in ipairs(result.editable) do
      table.insert(lines, "  " .. f)
    end
  end
  if result.read_only and #result.read_only > 0 then
    table.insert(lines, "Read-only:")
    for _, f in ipairs(result.read_only) do
      table.insert(lines, "  " .. f)
    end
  end
  if (not result.editable or #result.editable == 0)
    and (not result.read_only or #result.read_only == 0) then
    table.insert(lines, "  (no files in context)")
  end
  M._show_scratch_buffer("alchemist-files", lines)
end

--- Show models
function M.show_models()
  vim.notify("[Alchemist] Model routing is automatic in V1. "
    .. "The daemon selects models based on task type.", vim.log.levels.INFO)
end

--- Show settings
function M.show_settings()
  M.show_doctor()
end

--- Helper: open a scratch buffer with content
function M._show_scratch_buffer(name, lines)
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_valid(buf)
      and vim.api.nvim_buf_get_name(buf):match(name) then
      vim.api.nvim_set_option_value("modifiable", true, { buf = buf })
      vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
      vim.api.nvim_set_option_value("modifiable", false, { buf = buf })
      for _, win in ipairs(vim.api.nvim_list_wins()) do
        if vim.api.nvim_win_get_buf(win) == buf then
          vim.api.nvim_set_current_win(win)
          return
        end
      end
      vim.cmd("sbuffer " .. buf)
      return
    end
  end

  vim.cmd("botright new")
  local buf = vim.api.nvim_get_current_buf()
  vim.api.nvim_buf_set_name(buf, name)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.api.nvim_set_option_value("buftype", "nofile", { buf = buf })
  vim.api.nvim_set_option_value("bufhidden", "wipe", { buf = buf })
  vim.api.nvim_set_option_value("swapfile", false, { buf = buf })
  vim.api.nvim_set_option_value("modifiable", false, { buf = buf })
  vim.api.nvim_set_option_value("filetype", "alchemist", { buf = buf })

  vim.api.nvim_buf_set_keymap(buf, "n", "q", ":bwipeout<CR>",
    { noremap = true, silent = true })
end

M.ERROR_MAP = ERROR_MAP

return M
