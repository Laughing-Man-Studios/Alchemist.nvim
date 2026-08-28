local methods = require("alchemist.methods")
local state = require("alchemist.state")
local rpc = require("alchemist.rpc")

describe("methods", function()
  before_each(function()
    state.reset()
  end)

  it("should format initialize request correctly", function()
    local conn = rpc.connection()
    local sent = {}
    conn.request = function(_, method, params, callback)
      table.insert(sent, { method = method, params = params })
      callback({
        daemon_version = "0.1.0",
        protocol_version = "1.0.0",
        aider_version = "0.72.0",
        status = "ready",
      })
    end

    methods.initialize(function(err, res)
      assert.is_nil(err)
      assert.truthy(res)
      assert.equals("0.1.0", res.daemon_version)
    end)

    assert.equals(1, #sent)
    assert.equals("client/initialize", sent[1].method)
    assert.equals("1.0.0", sent[1].params.protocol_version)
    assert.truthy(sent[1].params.client_id)
  end)

  it("should format submit_prompt request with correct mode and parameters", function()
    local conn = rpc.connection()
    local sent = {}
    conn.request = function(_, method, params, callback)
      table.insert(sent, { method = method, params = params })
      callback({ status = "accepted", job_id = "job-123" })
    end

    methods.submit_prompt({
      mode = "code",
      prompt = "Refactor this function",
      active_files = { "main.py" },
      buffers = {},
    }, function(err, res)
      assert.is_nil(err)
      assert.equals("accepted", res.status)
    end)

    assert.equals(1, #sent)
    assert.equals("agent/submit_prompt", sent[1].method)
    assert.equals("code", sent[1].params.mode)
    assert.equals("Refactor this function", sent[1].params.prompt)
    assert.equals("main.py", sent[1].params.active_files[1])
  end)
end)
