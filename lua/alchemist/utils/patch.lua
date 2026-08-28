local M = {}

--- Apply a unified diff to an array of lines
--- Returns the modified lines, or nil on failure
---@param lines string[] Original lines
---@param diff_text string Unified diff for this file
---@return string[]|nil
function M.apply_unified_diff(lines, diff_text)
  local hunks = M._parse_hunks(diff_text)
  if not hunks or #hunks == 0 then return nil end

  local result = vim.deepcopy(lines)
  for i = #hunks, 1, -1 do
    local hunk = hunks[i]
    local ok, updated = M._apply_hunk(result, hunk)
    if not ok then return nil end
    result = updated
  end

  return result
end

--- Parse unified diff hunks
---@param diff_text string
---@return table[]|nil
function M._parse_hunks(diff_text)
  local hunks = {}
  local current_hunk = nil

  for line in diff_text:gmatch("[^\n]*") do
    local old_start, old_count, new_start, new_count =
      line:match("^@@ %-(%d+),?(%d*) %+(%d+),?(%d*) @@")

    if old_start then
      if current_hunk then
        table.insert(hunks, current_hunk)
      end
      current_hunk = {
        old_start = tonumber(old_start),
        old_count = tonumber(old_count) or (old_count == "" and 1 or 0),
        new_start = tonumber(new_start),
        new_count = tonumber(new_count) or (new_count == "" and 1 or 0),
        lines = {},
      }
    elseif current_hunk then
      if line:sub(1, 1) == "-" or line:sub(1, 1) == "+"
        or line:sub(1, 1) == " " then
        table.insert(current_hunk.lines, line)
      end
    end
  end

  if current_hunk then
    table.insert(hunks, current_hunk)
  end

  return hunks
end

--- Apply a single hunk to lines
---@param lines string[]
---@param hunk table
---@return boolean, string[]
function M._apply_hunk(lines, hunk)
  local old_lines = {}
  local new_lines = {}

  for _, line in ipairs(hunk.lines) do
    local prefix = line:sub(1, 1)
    local content = line:sub(2)
    if prefix == "-" then
      table.insert(old_lines, content)
    elseif prefix == "+" then
      table.insert(new_lines, content)
    elseif prefix == " " then
      table.insert(old_lines, content)
      table.insert(new_lines, content)
    end
  end

  local start = hunk.old_start
  for i, expected in ipairs(old_lines) do
    local actual = lines[start + i - 1]
    if actual ~= expected then
      return false, lines
    end
  end

  local result = {}
  for i = 1, start - 1 do
    table.insert(result, lines[i])
  end
  for _, line in ipairs(new_lines) do
    table.insert(result, line)
  end
  for i = start + #old_lines, #lines do
    table.insert(result, lines[i])
  end

  return true, result
end

--- Transactional patch application
--- Snapshots all affected buffers, applies changes, rolls back on failure
---@param diff_data table {base_hashes: table, diff: string, files_changed: string[]}
---@return boolean success, string|nil error_message
function M.apply_transactional(diff_data)
  local files = diff_data.files_changed or {}
  local unified_diff = diff_data.diff or ""

  local snapshots = {}
  local cursor_states = {}

  for _, file_path in ipairs(files) do
    local buf = vim.fn.bufnr(file_path)
    if buf ~= -1 and vim.api.nvim_buf_is_valid(buf) then
      snapshots[file_path] = {
        bufnr = buf,
        lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false),
        modified = vim.api.nvim_get_option_value("modified", { buf = buf }),
      }

      for _, win in ipairs(vim.api.nvim_list_wins()) do
        if vim.api.nvim_win_is_valid(win) and vim.api.nvim_win_get_buf(win) == buf then
          cursor_states[win] = vim.api.nvim_win_get_cursor(win)
        end
      end
    end
  end

  local git_ok = M._try_git_apply(unified_diff)
  if git_ok then
    for _, file_path in ipairs(files) do
      local buf = vim.fn.bufnr(file_path)
      if buf ~= -1 and vim.api.nvim_buf_is_valid(buf) then
        vim.api.nvim_buf_call(buf, function()
          vim.cmd("edit!")
        end)
      end
    end
    M._restore_cursors(cursor_states)
    return true, nil
  end

  local applied = {}

  for _, file_path in ipairs(files) do
    local buf = vim.fn.bufnr(file_path)
    local file_diff = M._extract_file_diff(unified_diff, file_path)

    if buf ~= -1 and vim.api.nvim_buf_is_valid(buf) and file_diff then
      local current_lines = vim.api.nvim_buf_get_lines(buf, 0, -1, false)
      local new_lines = M.apply_unified_diff(current_lines, file_diff)

      if not new_lines then
        M._rollback(applied, snapshots)
        return false, "Failed to apply patch to: " .. file_path
      end

      vim.api.nvim_buf_set_lines(buf, 0, -1, false, new_lines)
      table.insert(applied, file_path)
    elseif file_diff then
      vim.cmd("edit " .. vim.fn.fnameescape(file_path))
      local new_buf = vim.api.nvim_get_current_buf()
      local new_lines = M._extract_new_file_content(file_diff)
      if new_lines then
        vim.api.nvim_buf_set_lines(new_buf, 0, -1, false, new_lines)
        table.insert(applied, file_path)
      end
    end
  end

  for _, file_path in ipairs(applied) do
    local buf = vim.fn.bufnr(file_path)
    if buf ~= -1 and vim.api.nvim_buf_is_valid(buf) then
      local write_ok, write_err = pcall(function()
        vim.api.nvim_buf_call(buf, function()
          vim.cmd("write")
        end)
      end)
      if not write_ok then
        M._rollback(applied, snapshots)
        return false, "Failed to write: " .. file_path .. " - " .. tostring(write_err)
      end
    end
  end

  M._restore_cursors(cursor_states)

  return true, nil
end

--- Try applying via git apply
---@param diff_text string
---@return boolean
function M._try_git_apply(diff_text)
  local tmp = vim.fn.tempname()
  local f = io.open(tmp, "w")
  if not f then return false end
  f:write(diff_text)
  f:close()

  local check_result = vim.fn.system({ "git", "apply", "--check", tmp })
  local check_ok = (vim.v.shell_error == 0)

  if check_ok then
    vim.fn.system({ "git", "apply", tmp })
    check_ok = (vim.v.shell_error == 0)
  end

  os.remove(tmp)
  return check_ok
end

--- Rollback applied changes using snapshots
function M._rollback(applied, snapshots)
  for _, file_path in ipairs(applied) do
    local snap = snapshots[file_path]
    if snap and vim.api.nvim_buf_is_valid(snap.bufnr) then
      vim.api.nvim_buf_set_lines(snap.bufnr, 0, -1, false, snap.lines)
    end
  end
  vim.notify("[Alchemist] PATCH_APPLY_FAILED: All buffers restored from snapshots.",
    vim.log.levels.ERROR)
end

--- Restore cursor positions
function M._restore_cursors(cursor_states)
  for win, cursor in pairs(cursor_states) do
    if vim.api.nvim_win_is_valid(win) then
      pcall(vim.api.nvim_win_set_cursor, win, cursor)
    end
  end
end

--- Extract new file content from a diff (for file creation)
function M._extract_new_file_content(diff_text)
  local lines = {}
  local in_hunks = false
  for line in diff_text:gmatch("[^\n]*") do
    if line:match("^@@") then
      in_hunks = true
    elseif in_hunks then
      if line:sub(1, 1) == "+" then
        table.insert(lines, line:sub(2))
      end
    end
  end
  return #lines > 0 and lines or nil
end

--- Extract file diff
function M._extract_file_diff(unified_diff, file_path)
  local basename = vim.fn.fnamemodify(file_path, ":t")
  local in_file = false
  local lines = {}
  for line in unified_diff:gmatch("[^\n]*") do
    if line:match("^diff %-%-git") then
      if in_file then break end
      if line:match(basename) then in_file = true end
    end
    if in_file then table.insert(lines, line) end
  end
  return #lines > 0 and table.concat(lines, "\n") or nil
end

return M
