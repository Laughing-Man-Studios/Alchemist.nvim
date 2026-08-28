local paths = require("alchemist.paths")

describe("paths", function()
  it("should return valid socket path", function()
    local socket = paths.socket_path()
    assert.truthy(socket:match("alchemist%.sock$"))
  end)

  it("should return valid lock path", function()
    local lock = paths.lock_path()
    assert.truthy(lock:match("alchemist%.lock$"))
  end)

  it("should normalize paths removing trailing slashes", function()
    local norm = paths.normalize("/some/test/path/")
    assert.equals("/some/test/path", norm)
  end)

  it("should return valid daemon script path", function()
    local script = paths.daemon_script()
    assert.truthy(script:match("main%.py$"))
  end)
end)
