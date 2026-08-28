local rpc = require("alchemist.rpc")

describe("rpc", function()
  describe("NDJSON parsing", function()
    it("should parse a single valid frame", function()
      local conn = rpc.RpcConnection.new()
      local received = {}
      conn._handle_frame = function(_, frame)
        table.insert(received, vim.json.decode(frame))
      end

      conn:_on_data('{"jsonrpc":"2.0","method":"test"}\n')
      assert.equals(1, #received)
      assert.equals("test", received[1].method)
    end)

    it("should handle fragmented frames", function()
      local conn = rpc.RpcConnection.new()
      local received = {}
      conn._handle_frame = function(_, frame)
        table.insert(received, frame)
      end

      conn:_on_data('{"jsonrpc":')
      assert.equals(0, #received)
      conn:_on_data('"2.0","method":"test"}\n')
      assert.equals(1, #received)
    end)

    it("should skip empty lines", function()
      local conn = rpc.RpcConnection.new()
      local received = {}
      conn._handle_frame = function(_, frame)
        table.insert(received, frame)
      end

      conn:_on_data('\n\n{"jsonrpc":"2.0"}\n\n')
      assert.equals(1, #received)
    end)
  end)
end)
