local M = {}

local state = require("alchemist.state")
local methods = require("alchemist.methods")
local diag = require("alchemist.ui.diagnostics")

local function require_connected()
  if not state.get().connected then
    vim.notify("[Alchemist] Not connected to daemon. Run :AlchemistStart", vim.log.levels.ERROR)
    return false
  end
  return true
end

local function require_setup()
  if not require_connected() then return false end
  if state.get().setup_required then
    vim.notify("[Alchemist] No API keys configured. Run :AlchemistSetup first.", vim.log.levels.WARN)
    return false
  end
  return true
end

function M.register()
  local cmd = vim.api.nvim_create_user_command

  -- === Lifecycle/UI Commands ===

  cmd("AlchemistSetup", function()
    if not require_connected() then return end
    require("alchemist.ui.setup").open()
  end, { desc = "Open Alchemist API key setup" })

  cmd("AlchemistOpen", function()
    require("alchemist.ui.chat").open()
  end, { desc = "Open Alchemist chat panel" })

  cmd("AlchemistClose", function()
    require("alchemist.ui.chat").close()
  end, { desc = "Close Alchemist chat panel" })

  cmd("AlchemistStart", function()
    local bootstrap = require("alchemist.bootstrap")
    bootstrap.bootstrap(function(err)
      if err then
        vim.notify("[Alchemist] " .. err, vim.log.levels.ERROR)
      else
        vim.notify("[Alchemist] Connected to daemon.", vim.log.levels.INFO)
      end
    end)
  end, { desc = "Start/connect to Alchemist daemon" })

  cmd("AlchemistStop", function()
    if not require_connected() then return end
    methods.shutdown(function(err)
      if err then
        vim.notify("[Alchemist] Shutdown error: " .. (err.message or "unknown"),
          vim.log.levels.WARN)
      end
      require("alchemist.rpc").connection():disconnect()
      vim.notify("[Alchemist] Daemon stopped.", vim.log.levels.INFO)
    end)
  end, { desc = "Stop Alchemist daemon" })

  cmd("AlchemistRestart", function()
    local rpc = require("alchemist.rpc")
    local bootstrap = require("alchemist.bootstrap")

    if state.get().connected then
      methods.shutdown(function()
        rpc.connection():disconnect()
        vim.schedule(function()
          bootstrap.bootstrap(function(err)
            if err then
              vim.notify("[Alchemist] Restart failed: " .. err,
                vim.log.levels.ERROR)
            else
              vim.notify("[Alchemist] Restarted.", vim.log.levels.INFO)
            end
          end)
        end)
      end)
    else
      bootstrap.bootstrap(function(err)
        if err then
          vim.notify("[Alchemist] Start failed: " .. err, vim.log.levels.ERROR)
        else
          vim.notify("[Alchemist] Started.", vim.log.levels.INFO)
        end
      end)
    end
  end, { desc = "Restart Alchemist daemon" })

  cmd("AlchemistDoctor", function()
    diag.show_doctor()
  end, { desc = "Show Alchemist diagnostics" })

  cmd("AlchemistLogs", function()
    diag.show_logs()
  end, { desc = "Show Alchemist operational log" })

  cmd("AlchemistStatus", function()
    if not require_connected() then return end
    methods.agent_status(function(err, result)
      if err then
        diag.handle_error(err)
      else
        diag.show_status(result)
      end
    end)
  end, { desc = "Show current agent status" })

  -- === Agent Commands ===

  cmd("AlchemistChat", function(opts)
    if not require_setup() then return end
    require("alchemist.ui.chat").prompt("ask", opts.args)
  end, { nargs = "?", desc = "Send a chat message (ask mode)" })

  cmd("AlchemistAsk", function(opts)
    if not require_setup() then return end
    require("alchemist.ui.chat").prompt("ask", opts.args)
  end, { nargs = "?", desc = "Ask a question (read-only mode)" })

  cmd("AlchemistCode", function(opts)
    if not require_setup() then return end
    require("alchemist.ui.chat").prompt("code", opts.args)
  end, { nargs = "?", desc = "Request code modifications" })

  cmd("AlchemistArchitect", function(opts)
    if not require_setup() then return end
    require("alchemist.ui.chat").prompt("architect", opts.args)
  end, { nargs = "?", desc = "Architect-mode prompt" })

  cmd("AlchemistCancel", function()
    if not require_connected() then return end
    methods.cancel(function(err, result)
      if err then diag.handle_error(err) return end
      vim.notify("[Alchemist] " .. (result and result.state or "Cancelled"),
        vim.log.levels.INFO)
    end)
  end, { desc = "Cancel active agent operation" })

  cmd("AlchemistDiff", function()
    if not require_connected() then return end
    local diff_data = state.get().pending_diff
    if diff_data then
      require("alchemist.ui.diff").show(diff_data)
    else
      vim.notify("[Alchemist] No pending diff.", vim.log.levels.INFO)
    end
  end, { desc = "Show pending diff" })

  cmd("AlchemistApply", function()
    if not require_connected() then return end
    require("alchemist.ui.diff").apply()
  end, { desc = "Apply pending diff" })

  cmd("AlchemistReject", function()
    if not require_connected() then return end
    require("alchemist.ui.diff").reject()
  end, { desc = "Reject pending diff" })

  cmd("AlchemistReset", function()
    if not require_connected() then return end
    methods.reset(function(err)
      if err then diag.handle_error(err) return end
      vim.notify("[Alchemist] Session reset.", vim.log.levels.INFO)
    end)
  end, { desc = "Reset agent session" })

  cmd("AlchemistClear", function()
    if not require_connected() then return end
    methods.clear(function(err)
      if err then diag.handle_error(err) return end
      vim.notify("[Alchemist] Context cleared.", vim.log.levels.INFO)
    end)
  end, { desc = "Clear agent context" })

  -- === File/Context Commands ===

  cmd("AlchemistAdd", function(opts)
    if not require_connected() then return end
    local path = (opts.args and opts.args ~= "") and opts.args or vim.fn.expand("%:p")
    methods.add_file(path, function(err)
      if err then diag.handle_error(err) return end
      vim.notify("[Alchemist] Added: " .. vim.fn.fnamemodify(path, ":t"),
        vim.log.levels.INFO)
    end)
  end, { nargs = "?", complete = "file", desc = "Add file to agent context" })

  cmd("AlchemistReadOnly", function(opts)
    if not require_connected() then return end
    local path = (opts.args and opts.args ~= "") and opts.args or vim.fn.expand("%:p")
    methods.read_only(path, true, function(err)
      if err then diag.handle_error(err) return end
      vim.notify("[Alchemist] Read-only: " .. vim.fn.fnamemodify(path, ":t"),
        vim.log.levels.INFO)
    end)
  end, { nargs = "?", complete = "file", desc = "Add file as read-only" })

  cmd("AlchemistDrop", function(opts)
    if not require_connected() then return end
    local path = (opts.args and opts.args ~= "") and opts.args or vim.fn.expand("%:p")
    methods.drop_file(path, function(err)
      if err then diag.handle_error(err) return end
      vim.notify("[Alchemist] Dropped: " .. vim.fn.fnamemodify(path, ":t"),
        vim.log.levels.INFO)
    end)
  end, { nargs = "?", complete = "file", desc = "Remove file from context" })

  cmd("AlchemistFiles", function()
    if not require_connected() then return end
    methods.list_files(function(err, result)
      if err then diag.handle_error(err) return end
      diag.show_files(result)
    end)
  end, { desc = "List files in agent context" })

  cmd("AlchemistMap", function()
    if not require_connected() then return end
    methods.repo_map(function(err)
      if err then diag.handle_error(err) end
    end)
  end, { desc = "Show repository map" })

  cmd("AlchemistMapRefresh", function()
    if not require_connected() then return end
    methods.repo_map(function(err)
      if err then diag.handle_error(err) return end
      vim.notify("[Alchemist] Repository map refreshed.", vim.log.levels.INFO)
    end)
  end, { desc = "Refresh repository map" })

  -- === Execution/Support Commands ===

  cmd("AlchemistRun", function(opts)
    if not require_setup() then return end
    if not opts.args or opts.args == "" then
      vim.notify("[Alchemist] Usage: :AlchemistRun <command>",
        vim.log.levels.WARN)
      return
    end
    methods.run(opts.args, function(err)
      if err then diag.handle_error(err) end
    end)
  end, { nargs = "+", desc = "Run a shell command in agent context" })

  cmd("AlchemistTest", function()
    if not require_setup() then return end
    methods.test(function(err)
      if err then diag.handle_error(err) end
    end)
  end, { desc = "Run tests via agent" })

  cmd("AlchemistLint", function()
    if not require_setup() then return end
    methods.lint(function(err)
      if err then diag.handle_error(err) end
    end)
  end, { desc = "Run linting via agent" })

  cmd("AlchemistCommit", function()
    if not require_setup() then return end
    methods.run("git commit", function(err)
      if err then diag.handle_error(err) end
    end)
  end, { desc = "Commit via agent" })

  -- === Inspection Commands ===

  cmd("AlchemistModels", function()
    if not require_connected() then return end
    diag.show_models()
  end, { desc = "Show available models" })

  cmd("AlchemistSettings", function()
    if not require_connected() then return end
    diag.show_settings()
  end, { desc = "Show current settings" })
end

function M.unregister()
  local commands = {
    "AlchemistSetup", "AlchemistOpen", "AlchemistClose",
    "AlchemistStart", "AlchemistStop", "AlchemistRestart",
    "AlchemistDoctor", "AlchemistLogs", "AlchemistStatus",
    "AlchemistChat", "AlchemistAsk", "AlchemistCode",
    "AlchemistArchitect", "AlchemistCancel", "AlchemistDiff",
    "AlchemistApply", "AlchemistReject", "AlchemistReset",
    "AlchemistClear", "AlchemistAdd", "AlchemistReadOnly",
    "AlchemistDrop", "AlchemistFiles", "AlchemistMap",
    "AlchemistMapRefresh", "AlchemistRun", "AlchemistTest",
    "AlchemistLint", "AlchemistCommit", "AlchemistModels",
    "AlchemistSettings",
  }
  for _, name in ipairs(commands) do
    pcall(vim.api.nvim_del_user_command, name)
  end
end

return M
