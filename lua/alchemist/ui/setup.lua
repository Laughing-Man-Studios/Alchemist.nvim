local M = {}

local methods = require("alchemist.methods")
local state = require("alchemist.state")

local PROVIDERS = { "gemini", "deepseek", "qwen", "openai", "anthropic" }

local function has_nui()
  local ok = pcall(require, "nui.input")
  return ok
end

local function nui_secret_input(title, on_submit)
  local Input = require("nui.input")

  local SecretInput = Input:extend("SecretInput")

  function SecretInput:init(popup_options, options)
    popup_options.win_options = vim.tbl_deep_extend("force",
      popup_options.win_options or {}, {
        conceallevel = 2,
        concealcursor = "nvi",
      })
    SecretInput.super.init(self, popup_options, options)
  end

  function SecretInput:mount()
    SecretInput.super.mount(self)
    local prompt_length = vim.api.nvim_strwidth(
      vim.fn.prompt_getprompt(self.bufnr))
    vim.api.nvim_buf_call(self.bufnr, function()
      vim.cmd(string.format([[
        syn region SecretValue start=/^/ms=s+%s end=/$/ contains=SecretChar
        syn match SecretChar /./ contained conceal cchar=*
      ]], prompt_length))
    end)
  end

  local input = SecretInput({
    position = "50%",
    size = { width = 60 },
    border = {
      style = "rounded",
      text = { top = title, top_align = "center" },
    },
    win_options = {
      winhighlight = "Normal:Normal,FloatBorder:FloatBorder",
    },
  }, {
    prompt = "Key: ",
    on_submit = function(value)
      if value and value ~= "" then
        on_submit(value)
      end
    end,
  })

  input:mount()

  input:map("n", "<Esc>", function()
    input:unmount()
  end)

  local event = require("nui.utils.autocmd").event
  input:on(event.BufLeave, function()
    input:unmount()
  end)
end

local function native_secret_input(title, on_submit)
  local key = vim.fn.inputsecret(title .. " API Key: ")
  if key and key ~= "" then
    on_submit(key)
  end
end

local function prompt_key(provider, on_submit)
  local title = "[Alchemist Setup] " .. provider
  if has_nui() then
    nui_secret_input(title, on_submit)
  else
    native_secret_input(title, on_submit)
  end
end

function M.open()
  vim.ui.select(PROVIDERS, {
    prompt = "[Alchemist] Select a provider to configure:",
  }, function(provider)
    if not provider then return end

    prompt_key(provider, function(key)
      methods.set_key(provider, key, function(err)
        if err then
          vim.notify("[Alchemist] Failed to save key: "
            .. (err.message or "unknown error"), vim.log.levels.ERROR)
          return
        end

        state.update({ setup_required = false })
        vim.notify("[Alchemist] " .. provider .. " key saved successfully.",
          vim.log.levels.INFO)

        vim.ui.select(
          { "Add another provider key", "Done" },
          { prompt = "[Alchemist] Setup complete for " .. provider },
          function(choice)
            if choice == "Add another provider key" then
              M.open()
            end
          end
        )
      end)
    end)
  end)
end

M.PROVIDERS = PROVIDERS
M.has_nui = has_nui

return M
