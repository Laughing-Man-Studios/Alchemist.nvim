local M = {}

local uv = vim.uv or vim.loop
local paths = require("alchemist.paths")
local state = require("alchemist.state")
local rpc_mod = require("alchemist.rpc")

local ffi = require("ffi")
ffi.cdef[[
  int open(const char *pathname, int flags, ...);
  int close(int fd);
  int flock(int fd, int operation);
]]
local LOCK_EX = 2    -- Exclusive lock
local LOCK_NB = 4    -- Non-blocking
local LOCK_UN = 8    -- Unlock

local function open_flags()
  if jit.os == "OSX" then
    return 0x0002 + 0x0200  -- O_RDWR=2, O_CREAT=512 on macOS
  else
    return 0x0002 + 0x0040  -- O_RDWR=2, O_CREAT=64 on Linux
  end
end

local lock_fd = nil

--- Check if `uv` is available on PATH
---@return boolean
function M.has_uv()
  return vim.fn.executable("uv") == 1
end

--- Prompt user for uv download approval
---@param callback fun(approved: boolean)
function M.prompt_uv_download(callback)
  vim.ui.select(
    { "Yes, download uv", "No, I'll install it myself" },
    {
      prompt = "[Alchemist] 'uv' is required but not found on PATH.\n"
        .. "Source: https://github.com/astral-sh/uv\n"
        .. "Binary: uv (Python package manager)\n\n"
        .. "Allow download?",
    },
    function(choice)
      callback(choice == "Yes, download uv")
    end
  )
end

--- Install uv via the official installer
---@param callback fun(err: string|nil)
function M.install_uv(callback)
  vim.notify("[Alchemist] Downloading uv...", vim.log.levels.INFO)
  vim.fn.jobstart({ "sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh" }, {
    on_exit = function(_, exit_code)
      vim.schedule(function()
        if exit_code == 0 then
          vim.notify("[Alchemist] uv installed successfully.", vim.log.levels.INFO)
          callback(nil)
        else
          callback("UV_BOOTSTRAP_FAILED: uv installation exited with code " .. exit_code)
        end
      end)
    end,
  })
end

--- Try to acquire the daemon lockfile
---@return boolean success
function M.acquire_lock()
  local lock_path = paths.lock_path()
  paths.ensure_dir(vim.fn.fnamemodify(lock_path, ":h"), tonumber("700", 8))

  local fd = ffi.C.open(lock_path, open_flags(), tonumber("600", 8))
  if fd < 0 then return false end

  local result = ffi.C.flock(fd, LOCK_EX + LOCK_NB)
  if result ~= 0 then
    ffi.C.close(fd)
    return false
  end

  lock_fd = fd
  return true
end

--- Release the daemon lockfile
function M.release_lock()
  if lock_fd then
    ffi.C.flock(lock_fd, LOCK_UN)
    ffi.C.close(lock_fd)
    lock_fd = nil
  end
end

--- Check if the socket exists and a daemon is listening
---@param callback fun(listening: boolean)
function M.check_socket(callback)
  local socket_path = paths.socket_path()
  local stat = uv.fs_stat(socket_path)
  if not stat then
    callback(false)
    return
  end

  local pipe = uv.new_pipe(false)
  pipe:connect(socket_path, function(err)
    if err then
      if pipe and not pipe:is_closing() then
        pipe:close()
      end
      callback(false)
    else
      if pipe and not pipe:is_closing() then
        pipe:close()
      end
      callback(true)
    end
  end)
end

--- Remove a stale socket file
function M.cleanup_stale_socket()
  local socket_path = paths.socket_path()
  pcall(os.remove, socket_path)
end

--- Spawn the daemon process via `uv run`
---@param callback fun(err: string|nil)
function M.spawn_daemon(callback)
  local daemon_script = paths.daemon_script()

  local job_id = vim.fn.jobstart({
    "uv", "run", daemon_script,
  }, {
    detach = true,
    on_stderr = function(_, data)
      if data and #data > 0 then
        local msg = table.concat(data, "\n")
        if msg:match("ERROR") or msg:match("FATAL") then
          vim.schedule(function()
            vim.notify("[Alchemist Daemon] " .. msg, vim.log.levels.WARN)
          end)
        end
      end
    end,
    on_exit = function(_, exit_code)
      vim.schedule(function()
        if exit_code ~= 0 then
          state.update({ daemon_pid = nil })
        end
      end)
    end,
  })

  if job_id <= 0 then
    callback("Failed to spawn daemon process")
    return
  end

  state.update({ daemon_pid = vim.fn.jobpid(job_id) })
  callback(nil)
end

--- Wait for socket to become available with retries
---@param max_retries integer
---@param interval_ms integer
---@param callback fun(available: boolean)
function M.wait_for_socket(max_retries, interval_ms, callback)
  local attempts = 0
  local timer = uv.new_timer()

  timer:start(0, interval_ms, function()
    attempts = attempts + 1
    M.check_socket(function(listening)
      if listening then
        timer:stop()
        if not timer:is_closing() then timer:close() end
        vim.schedule(function() callback(true) end)
      elseif attempts >= max_retries then
        timer:stop()
        if not timer:is_closing() then timer:close() end
        vim.schedule(function() callback(false) end)
      end
    end)
  end)
end

--- Full bootstrap sequence: check uv, acquire lock, spawn daemon, connect, initialize
---@param callback fun(err: string|nil)
function M.bootstrap(callback)
  M.check_socket(function(listening)
    if listening then
      M._connect_and_initialize(callback)
      return
    end

    vim.schedule(function()
      if not M.has_uv() then
        M.prompt_uv_download(function(approved)
          if not approved then
            callback("UV_BOOTSTRAP_FAILED: uv is required. "
              .. "Install from https://github.com/astral-sh/uv")
            return
          end
          M.install_uv(function(err)
            if err then callback(err) return end
            M._do_spawn_and_connect(callback)
          end)
        end)
        return
      end

      M._do_spawn_and_connect(callback)
    end)
  end)
end

--- Internal: acquire lock, clean stale socket, spawn, wait, connect
function M._do_spawn_and_connect(callback)
  if not M.acquire_lock() then
    vim.notify("[Alchemist] Another instance is starting the daemon, waiting...",
      vim.log.levels.INFO)
    M.wait_for_socket(30, 500, function(available)
      M.release_lock()
      if available then
        M._connect_and_initialize(callback)
      else
        callback("DAEMON_UNAVAILABLE: Timed out waiting for daemon to start")
      end
    end)
    return
  end

  M.check_socket(function(alive)
    if not alive then
      M.cleanup_stale_socket()
    end

    vim.schedule(function()
      M.spawn_daemon(function(err)
        if err then
          M.release_lock()
          callback(err)
          return
        end

        M.wait_for_socket(20, 250, function(available)
          M.release_lock()
          if available then
            M._connect_and_initialize(callback)
          else
            callback("DAEMON_UNAVAILABLE: Daemon started but socket not available")
          end
        end)
      end)
    end)
  end)
end

--- Internal: connect socket and run initialize handshake
function M._connect_and_initialize(callback)
  local conn = rpc_mod.connection()

  conn:connect(function(err)
    if err then
      callback(err)
      return
    end

    vim.schedule(function()
      local methods = require("alchemist.methods")
      M._register_all_handlers()

      methods.initialize(function(init_err, result)
        if init_err then
          if init_err.message == "DAEMON_VERSION_MISMATCH" then
            callback("DAEMON_VERSION_MISMATCH: Update the plugin and rerun setup.")
          else
            callback("Initialize failed: " .. (init_err.message or "unknown"))
          end
          return
        end

        if result and result.status == "no_keys_configured" then
          state.update({ setup_required = true })
          vim.schedule(function()
            vim.notify("[Alchemist] No API keys configured. "
              .. "Run :AlchemistSetup to add a provider key.", vim.log.levels.WARN)
          end)
        end

        callback(nil)
      end)
    end)
  end)
end

--- Register all daemon→client handlers
function M._register_all_handlers()
  local methods = require("alchemist.methods")
  methods.register_handlers({
    ["ui/status_update"] = function(params)
      state.update({ last_status = params })
      local chat = require("alchemist.ui.chat")
      chat.on_status_update(params)
    end,

    ["ui/diff_ready"] = function(params)
      state.update({ pending_diff = params })
      vim.schedule(function()
        local diff_ui = require("alchemist.ui.diff")
        diff_ui.show(params)
      end)
    end,

    ["ui/clear_prompt"] = function(_params)
      -- Clear any active prompt UI
    end,

    ["agent/stream_delta"] = function(params)
      vim.schedule(function()
        local chat = require("alchemist.ui.chat")
        chat.on_stream_delta(params)
      end)
    end,

    ["server/request_confirmation"] = function(params)
      local prompts = require("alchemist.ui.prompts")
      return prompts.handle_confirmation(params)
    end,

    ["daemon/key_swapped"] = function(params)
      state.update({ last_status = vim.tbl_extend("force",
        state.get().last_status or {}, {
          provider = params.provider,
          model = params.model,
          key_index = params.current_key_index,
        })
      })
      vim.schedule(function()
        vim.notify(string.format(
          "[Alchemist] Key rotated: %s %s → Key #%d (%s)",
          params.provider, params.model,
          params.current_key_index, params.reason
        ), vim.log.levels.INFO)
      end)
    end,

    ["daemon/error"] = function(params)
      state.update({ last_error = params })
      vim.schedule(function()
        local diag = require("alchemist.ui.diagnostics")
        diag.handle_error(params)
      end)
    end,

    ["daemon/exhausted"] = function(_params)
      state.update({ last_error = {
        code = "ALL_KEYS_EXHAUSTED",
        message = "All provider keys exhausted",
        hint = "Add another key or wait for provider quota reset.",
      }})
      vim.schedule(function()
        vim.notify("[Alchemist] All API keys exhausted. "
          .. "Add another key via :AlchemistSetup or wait for quota reset.",
          vim.log.levels.ERROR)
      end)
    end,
  })
end

--- Attempt reconnection after disconnect
---@param callback fun(err: string|nil)
function M.reconnect(callback)
  rpc_mod.reset()
  state.update({
    connected = false,
    active_job = nil,
    pending_diff = nil,
  })

  M.check_socket(function(listening)
    if listening then
      M._connect_and_initialize(callback)
    else
      M.bootstrap(callback)
    end
  end)
end

return M
