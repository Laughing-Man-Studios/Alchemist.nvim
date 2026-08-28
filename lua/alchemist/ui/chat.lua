local M = {}

local methods = require("alchemist.methods")
local hash = require("alchemist.utils.hash")

local chat_buf = nil
local chat_win = nil

function M.open()
  if chat_win and vim.api.nvim_win_is_valid(chat_win) then
    vim.api.nvim_set_current_win(chat_win)
    return
  end

  if not chat_buf or not vim.api.nvim_buf_is_valid(chat_buf) then
    chat_buf = vim.api.nvim_create_buf(false, true)
    vim.api.nvim_buf_set_name(chat_buf, "alchemist-chat")
    vim.api.nvim_set_option_value("buftype", "nofile", { buf = chat_buf })
    vim.api.nvim_set_option_value("bufhidden", "hide", { buf = chat_buf })
    vim.api.nvim_set_option_value("swapfile", false, { buf = chat_buf })
    vim.api.nvim_set_option_value("filetype", "markdown", { buf = chat_buf })

    vim.api.nvim_buf_set_keymap(chat_buf, "n", "q", "",
      { noremap = true, silent = true, callback = function() M.close() end })
  end

  vim.cmd("botright vsplit")
  chat_win = vim.api.nvim_get_current_win()
  vim.api.nvim_win_set_buf(chat_win, chat_buf)
  vim.api.nvim_win_set_width(chat_win, math.floor(vim.o.columns * 0.35))
end

function M.close()
  if chat_win and vim.api.nvim_win_is_valid(chat_win) then
    vim.api.nvim_win_close(chat_win, true)
    chat_win = nil
  end
end

--- Append text to the chat buffer
---@param text string
function M.append(text)
  if not chat_buf or not vim.api.nvim_buf_is_valid(chat_buf) then
    return
  end

  vim.api.nvim_set_option_value("modifiable", true, { buf = chat_buf })
  local lines = vim.split(text, "\n", { plain = true })
  local last_line = vim.api.nvim_buf_line_count(chat_buf)
  local last_content = vim.api.nvim_buf_get_lines(chat_buf, last_line - 1, last_line, false)[1] or ""

  if #lines > 0 then
    vim.api.nvim_buf_set_lines(chat_buf, last_line - 1, last_line, false,
      { last_content .. lines[1] })
    if #lines > 1 then
      local rest = {}
      for i = 2, #lines do
        table.insert(rest, lines[i])
      end
      vim.api.nvim_buf_set_lines(chat_buf, last_line, last_line, false, rest)
    end
  end

  vim.api.nvim_set_option_value("modifiable", false, { buf = chat_buf })

  if chat_win and vim.api.nvim_win_is_valid(chat_win) then
    local new_last = vim.api.nvim_buf_line_count(chat_buf)
    vim.api.nvim_win_set_cursor(chat_win, { new_last, 0 })
  end
end

--- Handle agent/stream_delta notification
---@param params table {delta?: string}
function M.on_stream_delta(params)
  if params and params.delta then
    M.append(params.delta)
  end
end

--- Handle ui/status_update notification
---@param params table
function M.on_status_update(params)
  if params and params.phase then
    M.append("\n-- " .. params.phase .. " --\n")
  end
end

--- Prompt the user for input and submit to the agent
---@param mode string "ask"|"code"|"architect"
---@param initial_text string|nil Pre-filled prompt text
function M.prompt(mode, initial_text)
  M.open()

  if initial_text and initial_text ~= "" then
    M._submit(mode, initial_text)
    return
  end

  vim.ui.input({
    prompt = "[Alchemist " .. mode .. "] > ",
  }, function(input)
    if input and input ~= "" then
      M._submit(mode, input)
    end
  end)
end

--- Submit a prompt to the agent
---@param mode string
---@param prompt_text string
function M._submit(mode, prompt_text)
  M.append("\n--- You (" .. mode .. ") ---\n" .. prompt_text .. "\n")
  M.append("\n--- Alchemist ---\n")

  local buffers = M._collect_buffers()

  methods.submit_prompt({
    mode = mode,
    prompt = prompt_text,
    active_files = M._active_files(),
    buffers = buffers,
  }, function(err)
    if err then
      local diag = require("alchemist.ui.diagnostics")
      diag.handle_error(err)
    end
  end)
end

--- Collect buffer snapshots for pre-flight sync
---@return table[]
function M._collect_buffers()
  local buffers = {}
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_valid(buf)
      and vim.api.nvim_buf_is_loaded(buf)
      and vim.api.nvim_get_option_value("buflisted", { buf = buf })
      and vim.api.nvim_get_option_value("buftype", { buf = buf }) == "" then
      local path = vim.api.nvim_buf_get_name(buf)
      if path ~= "" then
        local lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
        local content = table.concat(lines, "\n") .. "\n"
        table.insert(buffers, {
          path = path,
          content = content,
          sha256 = hash.sha256(content),
          modified = vim.api.nvim_get_option_value("modified", { buf = buf }),
        })
      end
    end
  end
  return buffers
end

--- Get list of active file paths
---@return string[]
function M._active_files()
  local files = {}
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_valid(buf)
      and vim.api.nvim_buf_is_loaded(buf)
      and vim.api.nvim_get_option_value("buflisted", { buf = buf })
      and vim.api.nvim_get_option_value("buftype", { buf = buf }) == "" then
      local path = vim.api.nvim_buf_get_name(buf)
      if path ~= "" then
        table.insert(files, path)
      end
    end
  end
  return files
end

return M
