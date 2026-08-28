local M = {}

---@class AlchemistState
---@field client_id string UUID for this NeoVim client
---@field connected boolean Whether socket is connected
---@field daemon_version string|nil Daemon version from initialize
---@field protocol_version string|nil Protocol version from initialize
---@field aider_version string|nil Aider version from initialize
---@field active_project_id string|nil Current project UUID
---@field active_session_id string|nil Current session UUID
---@field active_job table|nil Current active job info
---@field pending_requests table<string, table> Map of request_id -> {method, timestamp}
---@field last_status table|nil Last ui/status_update payload
---@field last_error table|nil Last error
---@field pending_diff table|nil Pending ui/diff_ready payload
---@field setup_required boolean Whether setup flow is needed
---@field daemon_pid integer|nil PID of the daemon process we spawned

--- Internal state (not exported directly)
local state = {}

--- Callbacks registered for state changes
local watchers = {}

--- Generate a UUID v4
---@return string
local function uuid()
  local bytes = {}
  for i = 1, 16 do
    bytes[i] = math.random(0, 255)
  end
  -- Set version (4) and variant (RFC 4122)
  bytes[7] = bit.bor(bit.band(bytes[7], 0x0f), 0x40)
  bytes[9] = bit.bor(bit.band(bytes[9], 0x3f), 0x80)
  return string.format(
    "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
    bytes[1], bytes[2], bytes[3], bytes[4],
    bytes[5], bytes[6],
    bytes[7], bytes[8],
    bytes[9], bytes[10],
    bytes[11], bytes[12], bytes[13], bytes[14], bytes[15], bytes[16]
  )
end

--- Reset state to defaults
function M.reset()
  state = {
    client_id = uuid(),
    connected = false,
    daemon_version = nil,
    protocol_version = nil,
    aider_version = nil,
    active_project_id = nil,
    active_session_id = nil,
    active_job = nil,
    pending_requests = {},
    last_status = nil,
    last_error = nil,
    pending_diff = nil,
    setup_required = false,
    daemon_pid = nil,
  }
end

--- Get the current state (read-only snapshot)
---@return AlchemistState
function M.get()
  return vim.deepcopy(state)
end

--- Update one or more state fields (NeoVim-safe via vim.schedule)
---@param updates table<string, any>
function M.update(updates)
  vim.schedule(function()
    for key, value in pairs(updates) do
      state[key] = value
    end
    for _, cb in ipairs(watchers) do
      pcall(cb, updates, state)
    end
  end)
end

--- Update synchronously (for use inside vim.schedule callbacks)
---@param updates table<string, any>
function M.update_sync(updates)
  for key, value in pairs(updates) do
    state[key] = value
  end
  for _, cb in ipairs(watchers) do
    pcall(cb, updates, state)
  end
end

--- Explicitly set a state field (supports nil values)
---@param key string
---@param value any
function M.set(key, value)
  state[key] = value
  for _, cb in ipairs(watchers) do
    pcall(cb, { [key] = value }, state)
  end
end

--- Register a state change watcher
---@param callback fun(updates: table, state: AlchemistState)
---@return fun() unsubscribe function
function M.watch(callback)
  table.insert(watchers, callback)
  return function()
    for i, cb in ipairs(watchers) do
      if cb == callback then
        table.remove(watchers, i)
        return
      end
    end
  end
end

--- Get client_id directly (frequently needed for RPC envelopes)
---@return string
function M.client_id()
  return state.client_id
end

--- Get session_id, creating one if none exists
---@return string
function M.session_id()
  if not state.active_session_id then
    state.active_session_id = uuid()
  end
  return state.active_session_id
end

--- Get project_id, creating one if none exists
---@return string
function M.project_id()
  if not state.active_project_id then
    state.active_project_id = uuid()
  end
  return state.active_project_id
end

--- Track a pending request
---@param request_id string
---@param method string
function M.add_pending(request_id, method)
  local uv = vim.uv or vim.loop
  state.pending_requests[request_id] = {
    method = method,
    timestamp = uv.now(),
  }
end

--- Remove a pending request
---@param request_id string
function M.remove_pending(request_id)
  state.pending_requests[request_id] = nil
end

--- Generate a new UUID
---@return string
M.uuid = uuid

-- Initialize on load
M.reset()

return M
