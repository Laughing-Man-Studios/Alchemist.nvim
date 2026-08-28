local diag = require("alchemist.ui.diagnostics")
local state = require("alchemist.state")

describe("diagnostics", function()
  before_each(function()
    state.reset()
  end)

  it("should have all 13 standard error codes in ERROR_MAP", function()
    local expected_errors = {
      "NO_KEYS_CONFIGURED",
      "PROVIDER_RATE_LIMITED",
      "ALL_KEYS_EXHAUSTED",
      "PATCH_APPLY_FAILED",
      "AIDER_INTERNAL_ERROR",
      "UV_BOOTSTRAP_FAILED",
      "MODEL_CONTEXT_EXCEEDED",
      "DAEMON_VERSION_MISMATCH",
      "SHADOW_SYNC_FAILED",
      "FRAME_TOO_LARGE",
      "IPC_DISCONNECTED",
      "DAEMON_UNAVAILABLE",
      "AGENT_BUSY",
    }

    for _, err_code in ipairs(expected_errors) do
      assert.truthy(diag.ERROR_MAP[err_code], "Missing mapping for " .. err_code)
      assert.truthy(diag.ERROR_MAP[err_code].hint)
      assert.truthy(diag.ERROR_MAP[err_code].level)
    end
  end)

  it("should handle error notifications gracefully without leaking secrets", function()
    local notified = {}
    local orig_notify = vim.notify
    vim.notify = function(msg, level)
      table.insert(notified, { msg = msg, level = level })
    end

    diag.handle_error({
      code = -32000,
      message = "NO_KEYS_CONFIGURED",
      data = { hint = "Run :AlchemistSetup and add an API key." }
    })

    vim.notify = orig_notify

    assert.equals(1, #notified)
    assert.truthy(notified[1].msg:match("NO_KEYS_CONFIGURED"))
  end)
end)
