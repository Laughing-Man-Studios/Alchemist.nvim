local M = {}

local rpc = require("alchemist.rpc")
local state = require("alchemist.state")
local paths = require("alchemist.paths")

-- === Lifecycle Methods ===

function M.initialize(callback)
  local conn = rpc.connection()
  conn:request("client/initialize", {
    client_id = state.client_id(),
    cwd = paths.cwd(),
    nvim_pid = vim.fn.getpid(),
    protocol_version = "1.0.0",
  }, function(result)
    state.update({
      daemon_version = result.daemon_version,
      protocol_version = result.protocol_version,
      aider_version = result.aider_version,
      setup_required = (result.status == "no_keys_configured"),
    })
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.shutdown(callback)
  local conn = rpc.connection()
  conn:request("client/shutdown", {
    client_id = state.client_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.version(callback)
  local conn = rpc.connection()
  conn:request("daemon/version", {
    client_id = state.client_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.health(callback)
  local conn = rpc.connection()
  conn:request("daemon/health", {
    client_id = state.client_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

-- === Agent Methods ===

---@param opts {mode: string, prompt: string, active_files: string[], buffers: table[]}
---@param callback fun(err: table|nil, result: table|nil)|nil
function M.submit_prompt(opts, callback)
  local conn = rpc.connection()
  conn:request("agent/submit_prompt", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
    project_path = paths.cwd(),
    mode = opts.mode,
    prompt = opts.prompt,
    active_files = opts.active_files or {},
    buffers = opts.buffers or {},
  }, function(result)
    state.update({ active_job = result })
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end, 120000) -- 2 min timeout for prompt submission
end

function M.cancel(callback)
  local conn = rpc.connection()
  conn:request("agent/cancel", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    state.update({ active_job = nil })
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.agent_status(callback)
  local conn = rpc.connection()
  conn:request("agent/status", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.reset(callback)
  local conn = rpc.connection()
  conn:request("agent/reset", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    state.update({ active_job = nil, pending_diff = nil })
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.clear(callback)
  local conn = rpc.connection()
  conn:request("agent/clear", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

-- === File/Context Methods ===

function M.add_file(path, callback)
  local conn = rpc.connection()
  conn:request("agent/add_file", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
    path = path,
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.drop_file(path, callback)
  local conn = rpc.connection()
  conn:request("agent/drop_file", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
    path = path,
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.list_files(callback)
  local conn = rpc.connection()
  conn:request("agent/list_files", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.read_only(path, enabled, callback)
  local conn = rpc.connection()
  conn:request("agent/read_only", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
    path = path,
    enabled = enabled,
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.repo_map(callback)
  local conn = rpc.connection()
  conn:request("agent/repo_map", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

-- === Execution Methods ===

function M.run(command, callback)
  local conn = rpc.connection()
  conn:request("agent/run", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
    command = command,
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.test(callback)
  local conn = rpc.connection()
  conn:request("agent/test", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.lint(callback)
  local conn = rpc.connection()
  conn:request("agent/lint", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

-- === Diff Accept/Reject ===

function M.accept_diff(callback)
  local conn = rpc.connection()
  conn:request("agent/accept_diff", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    state.update({ active_job = nil, pending_diff = nil })
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.reject_diff(callback)
  local conn = rpc.connection()
  conn:request("agent/reject_diff", {
    client_id = state.client_id(),
    session_id = state.session_id(),
    project_id = state.project_id(),
  }, function(result)
    state.update({ active_job = nil, pending_diff = nil })
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

-- === Config Methods ===

---@param provider string
---@param key string API key (will be dropped from Lua state after send)
---@param callback fun(err: table|nil, result: table|nil)|nil
function M.set_key(provider, key, callback)
  local conn = rpc.connection()
  conn:request("config/set_key", {
    client_id = state.client_id(),
    provider = provider,
    key = key,
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.list_providers(callback)
  local conn = rpc.connection()
  conn:request("config/list_providers", {
    client_id = state.client_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

function M.list_keys(callback)
  local conn = rpc.connection()
  conn:request("config/list_keys", {
    client_id = state.client_id(),
  }, function(result)
    if callback then callback(nil, result) end
  end, function(err)
    if callback then callback(err, nil) end
  end)
end

-- === Daemon → Client Notification Registration ===

--- Wire all daemon→client notification and request handlers
---@param handlers table<string, function> Map of method -> handler function
function M.register_handlers(handlers)
  local conn = rpc.connection()

  local notifications = {
    "ui/status_update",
    "ui/diff_ready",
    "ui/clear_prompt",
    "agent/stream_delta",
    "daemon/key_swapped",
    "daemon/error",
    "daemon/exhausted",
  }

  for _, method in ipairs(notifications) do
    if handlers[method] then
      conn:on_notification(method, handlers[method])
    end
  end

  if handlers["server/request_confirmation"] then
    conn:on_request("server/request_confirmation",
      handlers["server/request_confirmation"])
  end
end

return M
