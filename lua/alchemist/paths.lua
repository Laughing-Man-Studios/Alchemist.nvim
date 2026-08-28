local M = {}

local uv = vim.uv or vim.loop

--- Resolve XDG_RUNTIME_DIR with fallback to /tmp/alchemist_$USER
---@return string
function M.runtime_dir()
  local xdg = os.getenv("XDG_RUNTIME_DIR")
  if xdg and xdg ~= "" then
    return xdg
  end
  local user = os.getenv("USER") or os.getenv("LOGNAME") or "unknown"
  return "/tmp/alchemist_" .. user
end

--- Socket path matching daemon/paths.py exactly
---@return string
function M.socket_path()
  return M.runtime_dir() .. "/alchemist.sock"
end

--- Lock path matching daemon/paths.py exactly
---@return string
function M.lock_path()
  return M.runtime_dir() .. "/alchemist.lock"
end

--- Config directory (~/.config/alchemist/)
---@return string
function M.config_dir()
  local xdg_config = os.getenv("XDG_CONFIG_HOME")
  if xdg_config and xdg_config ~= "" then
    return xdg_config .. "/alchemist"
  end
  return vim.fn.expand("~/.config/alchemist")
end

--- Daemon script path (ships with the plugin)
---@return string
function M.daemon_script()
  local plugin_root = vim.fn.fnamemodify(
    debug.getinfo(1, "S").source:sub(2), ":h:h:h"
  )
  return plugin_root .. "/alchemist/daemon/main.py"
end

--- Normalize a project path (resolve symlinks, trailing slashes)
---@param path string
---@return string
function M.normalize(path)
  local resolved = vim.fn.resolve(vim.fn.fnamemodify(path, ":p"))
  if #resolved > 1 and resolved:sub(-1) == "/" then
    resolved = resolved:sub(1, -2)
  end
  return resolved
end

--- Get current working directory
---@return string
function M.cwd()
  return M.normalize(uv.cwd())
end

--- Ensure a directory exists with the given permissions
---@param dir string
---@param mode integer|nil
function M.ensure_dir(dir, mode)
  local stat = uv.fs_stat(dir)
  if not stat then
    vim.fn.mkdir(dir, "p")
  end
  if mode then
    uv.fs_chmod(dir, mode)
  end
end

return M
