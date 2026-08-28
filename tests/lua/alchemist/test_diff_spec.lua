local diff_ui = require("alchemist.ui.diff")
local state = require("alchemist.state")

describe("diff UI", function()
  before_each(function()
    state.reset()
  end)

  it("should store pending diff in state", function()
    local payload = {
      client_id = state.client_id(),
      diff = "diff --git a/test.py b/test.py\n--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-a\n+b\n",
      files_changed = { "test.py" },
      base_hashes = { ["test.py"] = "hash123" },
    }

    diff_ui.show(payload)
    local s = state.get()
    assert.truthy(s.pending_diff)
    assert.equals("test.py", s.pending_diff.files_changed[1])

    diff_ui._cleanup()
    s = state.get()
    assert.is_nil(s.pending_diff)
  end)
end)
