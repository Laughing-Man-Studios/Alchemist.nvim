local M = {}

--- Compute SHA-256 hash of a string (matching Python's hashlib.sha256)
---@param content string UTF-8 string content
---@return string hex lowercase hex digest
function M.sha256(content)
  return vim.fn.sha256(content)
end

--- Compute SHA-256 hash of a buffer's contents
---@param bufnr integer Buffer number
---@return string hex lowercase hex digest
function M.sha256_buffer(bufnr)
  local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
  local content = table.concat(lines, "\n") .. "\n"
  return M.sha256(content)
end

--- Compute hashes for multiple buffers by file path
---@param buffers table[] Array of {path: string, bufnr: integer}
---@return table<string, string> Map of path -> sha256 hash
function M.hash_buffers(buffers)
  local hashes = {}
  for _, buf in ipairs(buffers) do
    hashes[buf.path] = M.sha256_buffer(buf.bufnr)
  end
  return hashes
end

return M
