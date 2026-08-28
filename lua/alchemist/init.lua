local M = {}

local state = require("alchemist.state")

--- User-facing setup function
---@param opts table|nil No required options for V1
function M.setup(opts)
  opts = opts or {}

  require("alchemist.commands").register()

  vim.defer_fn(function()
    require("alchemist.bootstrap").bootstrap(function(err)
      if err then
        state.update({ last_error = { code = "STARTUP", message = err } })
      end
    end)
  end, 100)

  vim.api.nvim_create_autocmd("VimLeavePre", {
    group = vim.api.nvim_create_augroup("AlchemistCleanup", { clear = true }),
    callback = function()
      local rpc = require("alchemist.rpc")
      if rpc.connection():is_connected() then
        rpc.connection():disconnect()
      end
      require("alchemist.bootstrap").release_lock()
    end,
  })
end

--- Statusline function
--- Returns a short, render-safe string for lualine/statusline integrations
---@return string
function M.status()
  local s = state.get()

  if not s.connected then
    return "🤖 Alchemist [offline]"
  end

  if s.setup_required then
    return "🤖 Alchemist [setup required]"
  end

  if s.last_error then
    local code = s.last_error.code or s.last_error.message or ""
    if code == "ALL_KEYS_EXHAUSTED" or code == "PROVIDER_RATE_LIMITED" then
      return "🤖 Alchemist [rate limited]"
    end
    return "🤖 Alchemist [error]"
  end

  if s.last_status and s.last_status.model then
    local model = s.last_status.model or "unknown"
    local key_idx = s.last_status.key_index
    if key_idx then
      return string.format("🤖 Alchemist [%s | Key #%d]", model, key_idx)
    end
    return string.format("🤖 Alchemist [%s]", model)
  end

  return "🤖 Alchemist [idle]"
end

return M
