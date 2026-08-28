local commands = require("alchemist.commands")

describe("commands", function()
  before_each(function()
    commands.unregister()
  end)

  after_each(function()
    commands.unregister()
  end)

  it("should register all expected commands", function()
    commands.register()
    local expected = {
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
    for _, name in ipairs(expected) do
      local exists = vim.fn.exists(":" .. name) == 2
      assert.is_true(exists, "Expected command " .. name .. " to be registered")
    end
  end)
end)
