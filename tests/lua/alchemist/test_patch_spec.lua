local patch = require("alchemist.utils.patch")

describe("patch utility", function()
  it("should parse unified diff hunks correctly", function()
    local diff = [[
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
 line 1
-line 2
+line 2 modified
 line 3
]]
    local hunks = patch._parse_hunks(diff)
    assert.truthy(hunks)
    assert.equals(1, #hunks)
    assert.equals(1, hunks[1].old_start)
    assert.equals(3, hunks[1].old_count)
  end)

  it("should apply unified diff to lines", function()
    local orig = { "line 1", "line 2", "line 3" }
    local diff = [[
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
 line 1
-line 2
+line 2 modified
 line 3
]]
    local res = patch.apply_unified_diff(orig, diff)
    assert.truthy(res)
    assert.equals("line 1", res[1])
    assert.equals("line 2 modified", res[2])
    assert.equals("line 3", res[3])
  end)
end)
