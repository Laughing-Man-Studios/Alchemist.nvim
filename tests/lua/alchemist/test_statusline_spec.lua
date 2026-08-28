local alchemist = require("alchemist")
local state = require("alchemist.state")

describe("statusline", function()
  before_each(function()
    state.reset()
  end)

  it("should return offline when disconnected", function()
    state.update_sync({ connected = false })
    assert.equals("🤖 Alchemist [offline]", alchemist.status())
  end)

  it("should return setup required when flagged", function()
    state.update_sync({ connected = true, setup_required = true })
    assert.equals("🤖 Alchemist [setup required]", alchemist.status())
  end)

  it("should return idle when connected with no active job/error", function()
    state.update_sync({ connected = true, setup_required = false })
    assert.equals("🤖 Alchemist [idle]", alchemist.status())
  end)

  it("should return active model and key info", function()
    state.update_sync({
      connected = true,
      setup_required = false,
      last_status = { model = "deepseek-v3", key_index = 2 },
    })
    assert.equals("🤖 Alchemist [deepseek-v3 | Key #2]", alchemist.status())
  end)

  it("should return rate limited on exhausted keys", function()
    state.update_sync({
      connected = true,
      setup_required = false,
      last_error = { code = "ALL_KEYS_EXHAUSTED" },
    })
    assert.equals("🤖 Alchemist [rate limited]", alchemist.status())
  end)
end)
