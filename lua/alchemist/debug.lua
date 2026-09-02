local M = {}

local state = require("alchemist.state")
local bootstrap = require("alchemist.bootstrap")
local diag = require("alchemist.ui.diagnostics")

-- Default debug configuration
local DEFAULT_DEBUG_CONFIG = {
  enabled = false,
  port = 5678,
  wait_for_client = true,
  debugger = "debugpy", -- or "pdb", "ipdb", etc.
  log_level = "info", -- "debug", "info", "warning", "error"
  lua_debug = false, -- Enable Lua client debugging
}

-- Debug state
local debug_state = {
  active = false,
  port = nil,
  debugger = nil,
  started_at = nil,
  debug_logs = {},
}

--- Get the current debug configuration
---@return table
function M.get_config()
  -- Support both old style (boolean) and new style (table) configuration
  if vim.g.alchemist_debug and type(vim.g.alchemist_debug) == "table" then
    -- Merge user config with defaults
    return vim.tbl_extend("force", vim.deepcopy(DEFAULT_DEBUG_CONFIG), vim.g.alchemist_debug)
  elseif vim.g.alchemist_debug then
    -- Legacy boolean style - convert to new format
    return vim.tbl_extend("force", vim.deepcopy(DEFAULT_DEBUG_CONFIG), {
      enabled = true,
      wait_for_client = vim.g.alchemist_debug_wait or false,
    })
  else
    return vim.deepcopy(DEFAULT_DEBUG_CONFIG)
  end
end

--- Check if debug mode is enabled
---@return boolean
function M.is_enabled()
  local config = M.get_config()
  return config.enabled
end

--- Check if we should wait for client connection
---@return boolean
function M.should_wait_for_client()
  local config = M.get_config()
  return config.wait_for_client
end

--- Get the debug port
---@return integer
function M.get_port()
  local config = M.get_config()
  return config.port
end

--- Get the debugger type
---@return string
function M.get_debugger()
  local config = M.get_config()
  return config.debugger or "debugpy"
end

--- Get the log level
---@return string
function M.get_log_level()
  local config = M.get_config()
  return config.log_level or "info"
end

--- Check if Lua debugging is enabled
---@return boolean
function M.is_lua_debug_enabled()
  local config = M.get_config()
  return config.lua_debug or false
end

--- Start daemon in debug mode
---@param port number|nil Optional port override
---@param callback fun(err: string|nil)
function M.start_debug(port, callback)
  if type(port) == "function" then
    -- Handle callback as first argument
    callback = port
    port = nil
  end

  -- Set debug configuration
  if port then
    vim.g.alchemist_debug = vim.tbl_extend("force", M.get_config(), {
      enabled = true,
      port = port,
    })
  else
    -- Enable debug mode with current or default config
    local current_config = M.get_config()
    vim.g.alchemist_debug = vim.tbl_extend("force", current_config, {
      enabled = true,
    })
  end

  -- Update debug state
  debug_state.active = true
  debug_state.port = port or M.get_port()
  debug_state.debugger = M.get_debugger()
  debug_state.started_at = os.date("%Y-%m-%d %H:%M:%S")

  -- Add debug log entry
  M.add_debug_log("info", "Debug mode started", {
    port = debug_state.port,
    debugger = debug_state.debugger,
  })

  -- Start the daemon with debug configuration
  bootstrap.bootstrap(function(err)
    if err then
      M.add_debug_log("error", "Debug daemon startup failed", { error = err })
      callback(err)
    else
      M.add_debug_log("info", "Debug daemon started successfully")
      callback(nil)
    end
  end)
end

--- Stop debug session
---@param callback fun(err: string|nil)
function M.stop_debug(callback)
  -- Clear debug configuration
  vim.g.alchemist_debug = nil
  vim.g.alchemist_debug_wait = nil

  -- Update debug state
  debug_state.active = false
  debug_state.port = nil
  debug_state.debugger = nil

  -- Add debug log entry
  M.add_debug_log("info", "Debug mode stopped")

  -- Stop the daemon
  local methods = require("alchemist.methods")
  local rpc = require("alchemist.rpc")
  
  if state.get().connected then
    methods.shutdown(function(err)
      if err then
        M.add_debug_log("error", "Debug daemon shutdown failed", { error = err.message or err })
      end
      rpc.connection():disconnect()
      if callback then callback(err) end
    end)
  else
    if callback then callback(nil) end
  end
end

--- Get debug status
---@return table
function M.get_debug_status()
  local config = M.get_config()
  return {
    enabled = config.enabled,
    active = debug_state.active,
    port = debug_state.port or config.port,
    debugger = debug_state.debugger or config.debugger,
    wait_for_client = config.wait_for_client,
    log_level = config.log_level,
    lua_debug = config.lua_debug,
    started_at = debug_state.started_at,
    daemon_pid = state.get().daemon_pid,
  }
end

--- Add a debug-specific log entry
---@param level string
---@param message string
---@param context table|nil
function M.add_debug_log(level, message, context)
  local entry = {
    timestamp = os.date("%Y-%m-%d %H:%M:%S"),
    level = level,
    message = message,
    context = context or {},
  }
  
  table.insert(debug_state.debug_logs, 1, entry)
  if #debug_state.debug_logs > 100 then
    table.remove(debug_state.debug_logs, #debug_state.debug_logs)
  end
  
  -- Also add to main log for consistency using the public interface
  diag.handle_error({
    code = "DEBUG_" .. level:upper(),
    message = "[DEBUG] " .. message,
    data = { hint = vim.json.encode(context) }
  })
end

--- Get debug logs
---@return table
function M.get_debug_logs()
  return debug_state.debug_logs
end

--- Clear debug logs
function M.clear_debug_logs()
  debug_state.debug_logs = {}
end

--- Build debugpy command arguments
---@return table
function M.build_debug_command()
  local config = M.get_config()
  local cmd = {}
  
  if config.debugger == "debugpy" then
    table.insert(cmd, "python")
    table.insert(cmd, "-m")
    table.insert(cmd, "debugpy")
    table.insert(cmd, "--listen")
    table.insert(cmd, "127.0.0.1:" .. config.port)
    
    if config.wait_for_client then
      table.insert(cmd, "--wait-for-client")
    end
    
    -- Add debugpy log level if configured
    if config.log_level and config.log_level ~= "info" then
      table.insert(cmd, "--log-level")
      table.insert(cmd, config.log_level)
    end
  elseif config.debugger == "pdb" then
    table.insert(cmd, "python")
    table.insert(cmd, "-m")
    table.insert(cmd, "pdb")
  elseif config.debugger == "ipdb" then
    table.insert(cmd, "python")
    table.insert(cmd, "-m")
    table.insert(cmd, "IPython.terminal.ipapp")
  else
    -- Default to debugpy
    table.insert(cmd, "python")
    table.insert(cmd, "-m")
    table.insert(cmd, "debugpy")
    table.insert(cmd, "--listen")
    table.insert(cmd, "127.0.0.1:" .. config.port)
    
    if config.wait_for_client then
      table.insert(cmd, "--wait-for-client")
    end
  end
  
  return cmd
end

--- Show debug status in a buffer
function M.show_debug_status()
  local status = M.get_debug_status()
  local lines = {
    "=== Alchemist Debug Status ===",
    "",
    "Debug Enabled:    " .. (status.enabled and "Yes" or "No"),
    "Debug Active:     " .. (status.active and "Yes" or "No"),
    "Port:             " .. status.port,
    "Debugger:         " .. status.debugger,
    "Wait for Client:  " .. (status.wait_for_client and "Yes" or "No"),
    "Log Level:        " .. status.log_level,
    "Lua Debug:        " .. (status.lua_debug and "Yes" or "No"),
    "Started At:       " .. (status.started_at or "N/A"),
    "Daemon PID:       " .. (status.daemon_pid and tostring(status.daemon_pid) or "N/A"),
    "",
  }
  
  diag._show_scratch_buffer("alchemist-debug-status", lines)
end

--- Show debug logs in a buffer
function M.show_debug_logs()
  local logs = M.get_debug_logs()
  local lines = {"=== Alchemist Debug Logs ===", ""}
  
  if #logs == 0 then
    table.insert(lines, "  (no debug log entries)")
  else
    for _, entry in ipairs(logs) do
      local level_icons = {
        debug = "[D]",
        info = "[I]",
        warning = "[W]",
        error = "[E]",
      }
      local level_icon = level_icons[entry.level] or "[?]"
      
      table.insert(lines, string.format("[%s] %s %s", entry.timestamp, level_icon, entry.message))
      
      if entry.context and not vim.tbl_isempty(entry.context) then
        for k, v in pairs(entry.context) do
          table.insert(lines, string.format("    %s: %s", k, vim.inspect(v)))
        end
      end
    end
  end
  
  diag._show_scratch_buffer("alchemist-debug-logs", lines)
end

--- Setup debug module
function M.setup()
  -- Add debug status to doctor output
  -- This will be integrated into the main doctor function
end

return M