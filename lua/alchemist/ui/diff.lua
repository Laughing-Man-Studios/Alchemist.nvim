local M = {}

local state = require("alchemist.state")
local methods = require("alchemist.methods")
local patch_util = require("alchemist.utils.patch")
local diag = require("alchemist.ui.diagnostics")

local diff_bufs = {}
local diff_wins = {}

--- Show a diff from ui/diff_ready payload
---@param params table {base_hashes: table, diff: string, files_changed: string[], client_id?: string, session_id?: string, project_id?: string}
function M.show(params)
  M._cleanup()

  local s = state.get()
  if params.client_id and params.client_id ~= s.client_id then
    return
  end

  state.update_sync({ pending_diff = params })

  local diff_text = params.diff or ""
  local files_changed = params.files_changed or {}

  if diff_text == "" then
    vim.notify("[Alchemist] No changes in diff.", vim.log.levels.INFO)
    return
  end

  for _, file_path in ipairs(files_changed) do
    M._show_file_diff(file_path, diff_text, params.base_hashes)
  end

  M._setup_keymaps()

  vim.notify("[Alchemist] Diff ready for " .. #files_changed .. " file(s). "
    .. "<Leader>ca to apply, <Leader>cr to reject.", vim.log.levels.INFO)
end

--- Show native NeoVim diff for a single file
function M._show_file_diff(file_path, unified_diff, base_hashes)
  local live_buf = vim.fn.bufnr(file_path)
  if live_buf == -1 then
    vim.cmd("edit " .. vim.fn.fnameescape(file_path))
    live_buf = vim.api.nvim_get_current_buf()
  end

  local file_diff = patch_util._extract_file_diff(unified_diff, file_path)
  if not file_diff then return end

  local current_lines = vim.api.nvim_buf_get_lines(live_buf, 0, -1, false)
  local after_lines = patch_util.apply_unified_diff(current_lines, file_diff)

  if not after_lines then
    M._show_raw_diff(file_path, unified_diff)
    return
  end

  vim.cmd("tabnew")
  vim.api.nvim_win_set_buf(0, live_buf)

  local scratch_buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_name(scratch_buf, "alchemist://diff/" ..
    vim.fn.fnamemodify(file_path, ":t"))
  vim.api.nvim_buf_set_lines(scratch_buf, 0, -1, false, after_lines)
  vim.api.nvim_set_option_value("buftype", "nofile", { buf = scratch_buf })
  vim.api.nvim_set_option_value("modifiable", false, { buf = scratch_buf })
  vim.api.nvim_set_option_value("filetype",
    vim.api.nvim_get_option_value("filetype", { buf = live_buf }),
    { buf = scratch_buf })

  vim.cmd("diffthis")
  vim.cmd("vsplit")
  vim.api.nvim_win_set_buf(0, scratch_buf)
  vim.cmd("diffthis")

  table.insert(diff_bufs, scratch_buf)
  table.insert(diff_wins, vim.api.nvim_get_current_win())
end

--- Show raw diff text in a scratch buffer (fallback)
function M._show_raw_diff(file_path, diff_text)
  vim.cmd("botright new")
  local buf = vim.api.nvim_get_current_buf()
  vim.api.nvim_buf_set_name(buf, "alchemist://diff-raw/" ..
    vim.fn.fnamemodify(file_path, ":t"))
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(diff_text, "\n"))
  vim.api.nvim_set_option_value("buftype", "nofile", { buf = buf })
  vim.api.nvim_set_option_value("modifiable", false, { buf = buf })
  vim.api.nvim_set_option_value("filetype", "diff", { buf = buf })
  table.insert(diff_bufs, buf)
end

--- Apply the pending diff
function M.apply()
  local diff_data = state.get().pending_diff
  if not diff_data then
    vim.notify("[Alchemist] No pending diff to apply.", vim.log.levels.WARN)
    return
  end

  local hash_mod = require("alchemist.utils.hash")
  local conflicts = {}

  for path, expected_hash in pairs(diff_data.base_hashes or {}) do
    local buf = vim.fn.bufnr(path)
    if buf ~= -1 and vim.api.nvim_buf_is_valid(buf) then
      local current_hash = hash_mod.sha256_buffer(buf)
      if current_hash ~= expected_hash then
        table.insert(conflicts, path)
      end
    end
  end

  if #conflicts > 0 then
    vim.notify("[Alchemist] Optimistic lock conflict on: "
      .. table.concat(conflicts, ", ")
      .. ". Buffers were modified since the diff was generated.",
      vim.log.levels.ERROR)
    return
  end

  local ok, err = patch_util.apply_transactional(diff_data)
  if not ok then
    diag.handle_error({
      message = "PATCH_APPLY_FAILED",
      data = { hint = err or "Patch application failed. Buffers were restored." },
    })
    return
  end

  methods.accept_diff(function(rpc_err)
    if rpc_err then
      diag.handle_error(rpc_err)
      return
    end
    vim.notify("[Alchemist] Diff applied successfully.", vim.log.levels.INFO)
  end)

  M._cleanup()
end

--- Reject the pending diff
function M.reject()
  local diff_data = state.get().pending_diff
  if not diff_data then
    vim.notify("[Alchemist] No pending diff to reject.", vim.log.levels.WARN)
    return
  end

  methods.reject_diff(function(err)
    if err then
      diag.handle_error(err)
      return
    end
    vim.notify("[Alchemist] Diff rejected.", vim.log.levels.INFO)
  end)

  M._cleanup()
end

--- Setup apply/reject keymaps
function M._setup_keymaps()
  vim.keymap.set("n", "<Leader>ca", function() M.apply() end,
    { desc = "Alchemist: Apply diff", silent = true })
  vim.keymap.set("n", "<Leader>cr", function() M.reject() end,
    { desc = "Alchemist: Reject diff", silent = true })
end

--- Remove diff keymaps
function M._remove_keymaps()
  pcall(vim.keymap.del, "n", "<Leader>ca")
  pcall(vim.keymap.del, "n", "<Leader>cr")
end

--- Clean up diff UI state
function M._cleanup()
  for _, buf in ipairs(diff_bufs) do
    if vim.api.nvim_buf_is_valid(buf) then
      vim.api.nvim_buf_delete(buf, { force = true })
    end
  end
  diff_bufs = {}

  for _, win in ipairs(vim.api.nvim_list_wins()) do
    if vim.api.nvim_win_is_valid(win) then
      pcall(function()
        vim.api.nvim_win_call(win, function()
          vim.cmd("diffoff")
        end)
      end)
    end
  end
  diff_wins = {}

  M._remove_keymaps()
  state.set("pending_diff", nil)
end

return M
