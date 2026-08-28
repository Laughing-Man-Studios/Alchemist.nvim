local setup = require("alchemist.ui.setup")

describe("setup UI", function()
  it("should have valid provider list", function()
    assert.truthy(setup.PROVIDERS)
    assert.equals(5, #setup.PROVIDERS)
    assert.equals("gemini", setup.PROVIDERS[1])
  end)
end)
