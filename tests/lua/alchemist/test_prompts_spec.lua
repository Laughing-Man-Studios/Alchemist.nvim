local prompts = require("alchemist.ui.prompts")

describe("prompts UI", function()
  it("should handle boolean prompt with confirmation", function()
    local orig_confirm = vim.fn.confirm
    vim.fn.confirm = function() return 1 end

    local res = prompts.handle_confirmation({
      prompt_type = "boolean",
      message = "Do you want to add file to git?",
      default_value = false,
    })

    vim.fn.confirm = orig_confirm

    assert.is_true(res.confirmed)
    assert.equals("y", res.value)
  end)

  it("should handle text prompt input", function()
    local orig_input = vim.fn.input
    vim.fn.input = function() return "my answer" end

    local res = prompts.handle_confirmation({
      prompt_type = "text",
      message = "Enter your instruction",
      default_value = "",
    })

    vim.fn.input = orig_input

    assert.is_true(res.confirmed)
    assert.equals("my answer", res.value)
  end)
end)
