local M = {}

local uv = vim.uv or vim.loop
local state = require("alchemist.state")
local paths = require("alchemist.paths")

local MAX_FRAME_SIZE = 16 * 1024 * 1024 -- 16 MiB

--- @class RpcConnection
--- @field pipe userdata|nil libuv pipe handle
--- @field buffer string accumulated read buffer
--- @field connected boolean
--- @field pending table<string, {resolve: function, reject: function, timer: userdata}>
--- @field notification_handlers table<string, function>
--- @field request_handlers table<string, function>
local RpcConnection = {}
RpcConnection.__index = RpcConnection

function RpcConnection.new()
  local self = setmetatable({}, RpcConnection)
  self.pipe = nil
  self.buffer = ""
  self.connected = false
  self.pending = {}
  self.notification_handlers = {}
  self.request_handlers = {}
  return self
end

--- Connect to the daemon socket
---@param callback fun(err: string|nil)
function RpcConnection:connect(callback)
  local socket_path = paths.socket_path()
  self.pipe = uv.new_pipe(false)
  self.buffer = ""

  self.pipe:connect(socket_path, function(err)
    if err then
      if self.pipe and not self.pipe:is_closing() then
        self.pipe:close()
      end
      self.pipe = nil
      callback("Failed to connect to daemon socket: " .. tostring(err))
      return
    end

    self.connected = true
    state.update({ connected = true })

    -- Start reading
    self.pipe:read_start(function(read_err, data)
      if read_err then
        vim.schedule(function()
          self:_handle_disconnect("Read error: " .. tostring(read_err))
        end)
        return
      end

      if data then
        self:_on_data(data)
      else
        -- EOF
        vim.schedule(function()
          self:_handle_disconnect("Connection closed by daemon")
        end)
      end
    end)

    callback(nil)
  end)
end

--- Process incoming data, buffer until newline, parse frames
---@param data string
function RpcConnection:_on_data(data)
  self.buffer = self.buffer .. data

  -- Check frame size limit
  if #self.buffer > MAX_FRAME_SIZE then
    vim.schedule(function()
      self:_handle_disconnect("FRAME_TOO_LARGE: buffer exceeded 16 MiB")
    end)
    return
  end

  -- Extract complete frames (delimited by \n)
  while true do
    local newline_pos = self.buffer:find("\n", 1, true)
    if not newline_pos then break end

    local frame = self.buffer:sub(1, newline_pos - 1)
    self.buffer = self.buffer:sub(newline_pos + 1)

    -- Skip empty lines
    if #frame > 0 then
      self:_handle_frame(frame)
    end
  end
end

--- Parse and dispatch a single JSON frame
---@param frame string
function RpcConnection:_handle_frame(frame)
  local ok, msg = pcall(vim.json.decode, frame)
  if not ok then
    vim.notify("[Alchemist] Malformed JSON from daemon", vim.log.levels.WARN)
    return
  end

  if type(msg) ~= "table" then return end

  -- Response to our request (has "id" and "result" or "error")
  if msg.id and (msg.result ~= nil or msg.error ~= nil) then
    self:_handle_response(msg)
  -- Server-initiated request (has "id" and "method")
  elseif msg.id and msg.method then
    self:_handle_server_request(msg)
  -- Notification (has "method" but no "id")
  elseif msg.method and not msg.id then
    self:_handle_notification(msg)
  end
end

--- Handle a response to one of our pending requests
---@param msg table
function RpcConnection:_handle_response(msg)
  local id = tostring(msg.id)
  local pending = self.pending[id]
  if not pending then return end

  -- Cancel timeout timer
  if pending.timer then
    pending.timer:stop()
    if not pending.timer:is_closing() then
      pending.timer:close()
    end
  end

  self.pending[id] = nil
  state.remove_pending(id)

  if msg.error then
    pending.reject(msg.error)
  else
    pending.resolve(msg.result)
  end
end

--- Handle a server-initiated request (e.g., server/request_confirmation)
---@param msg table
function RpcConnection:_handle_server_request(msg)
  local handler = self.request_handlers[msg.method]
  if handler then
    local ok, result = pcall(handler, msg.params)
    if ok then
      self:_send_response(msg.id, result, nil)
    else
      self:_send_response(msg.id, nil, {
        code = -32603,
        message = "Internal error handling server request",
      })
    end
  else
    self:_send_response(msg.id, nil, {
      code = -32601,
      message = "Method not found: " .. (msg.method or "unknown"),
    })
  end
end

--- Handle a notification from the daemon
---@param msg table
function RpcConnection:_handle_notification(msg)
  local handler = self.notification_handlers[msg.method]
  if handler then
    pcall(handler, msg.params)
  end
end

--- Send a JSON-RPC request and return result via callbacks
---@param method string
---@param params table|nil
---@param on_result fun(result: any)
---@param on_error fun(err: table)
---@param timeout_ms integer|nil (default 30000)
function RpcConnection:request(method, params, on_result, on_error, timeout_ms)
  if not self.connected or not self.pipe then
    on_error({
      code = -32010,
      message = "IPC_DISCONNECTED",
      data = { hint = "Connection to daemon lost. Restart with :AlchemistStart." }
    })
    return
  end

  local id = state.uuid()
  timeout_ms = timeout_ms or 30000

  local timer = uv.new_timer()
  timer:start(timeout_ms, 0, function()
    vim.schedule(function()
      local p = self.pending[id]
      if p then
        self.pending[id] = nil
        state.remove_pending(id)
        if p.timer and not p.timer:is_closing() then
          p.timer:close()
        end
        on_error({ code = -32603, message = "Request timed out", data = { method = method } })
      end
    end)
  end)

  self.pending[id] = {
    resolve = on_result,
    reject = on_error,
    timer = timer,
  }
  state.add_pending(id, method)

  local envelope = {
    jsonrpc = "2.0",
    id = id,
    method = method,
    params = params,
  }

  self:_send_frame(envelope)
end

--- Send a JSON-RPC notification (no response expected)
---@param method string
---@param params table|nil
function RpcConnection:notify(method, params)
  if not self.connected or not self.pipe then return end

  local envelope = {
    jsonrpc = "2.0",
    method = method,
    params = params,
  }

  self:_send_frame(envelope)
end

--- Send a response to a server-initiated request
---@param id string|number
---@param result any
---@param error table|nil
function RpcConnection:_send_response(id, result, error)
  local envelope = { jsonrpc = "2.0", id = id }
  if error then
    envelope.error = error
  else
    envelope.result = result
  end
  self:_send_frame(envelope)
end

--- Serialize and write a JSON-RPC frame over the socket
---@param envelope table
function RpcConnection:_send_frame(envelope)
  if not self.pipe then return end

  local ok, json = pcall(vim.json.encode, envelope)
  if not ok then
    vim.notify("[Alchemist] Failed to encode JSON frame", vim.log.levels.ERROR)
    return
  end

  self.pipe:write(json .. "\n", function(err)
    if err then
      vim.schedule(function()
        self:_handle_disconnect("Write error: " .. tostring(err))
      end)
    end
  end)
end

--- Handle disconnection
---@param reason string
function RpcConnection:_handle_disconnect(reason)
  local was_connected = self.connected
  self.connected = false

  for id, pending in pairs(self.pending) do
    if pending.timer and not pending.timer:is_closing() then
      pending.timer:stop()
      pending.timer:close()
    end
    pcall(pending.reject, {
      code = -32010,
      message = "IPC_DISCONNECTED",
      data = { hint = "Connection to daemon lost. Restart with :AlchemistStart." },
    })
  end
  self.pending = {}

  if self.pipe then
    if not self.pipe:is_closing() then
      self.pipe:read_stop()
      self.pipe:close()
    end
    self.pipe = nil
  end

  state.update({
    connected = false,
    active_job = nil,
    pending_requests = {},
  })

  if was_connected then
    vim.notify("[Alchemist] " .. reason, vim.log.levels.WARN)
  end
end

--- Register a notification handler
---@param method string
---@param handler fun(params: table)
function RpcConnection:on_notification(method, handler)
  self.notification_handlers[method] = handler
end

--- Register a server-initiated request handler
---@param method string
---@param handler fun(params: table): table
function RpcConnection:on_request(method, handler)
  self.request_handlers[method] = handler
end

--- Disconnect cleanly
function RpcConnection:disconnect()
  if self.connected then
    self:notify("client/shutdown", {
      client_id = state.client_id(),
    })
  end
  self:_handle_disconnect("Client disconnected")
end

--- Check if connected
---@return boolean
function RpcConnection:is_connected()
  return self.connected
end

M.RpcConnection = RpcConnection

-- Module-level singleton
M._conn = nil

--- Get or create the singleton connection
---@return RpcConnection
function M.connection()
  if not M._conn then
    M._conn = RpcConnection.new()
  end
  return M._conn
end

--- Reset the singleton (for testing)
function M.reset()
  if M._conn then
    M._conn:disconnect()
  end
  M._conn = nil
end

return M
