local M = {}

--- Handle a server/request_confirmation request
---@param params table
---@return table result
function M.handle_confirmation(params)
  local prompt_type = params.prompt_type
  local message = params.message or ""
  local default_value = params.default_value

  if prompt_type == "boolean" then
    return M._handle_boolean(message, default_value)
  elseif prompt_type == "text" then
    return M._handle_text(message, default_value)
  elseif prompt_type == "selection" then
    return M._handle_selection(message, default_value)
  else
    return { confirmed = false, value = nil }
  end
end

---@param message string
---@param default boolean|nil
---@return table
function M._handle_boolean(message, default)
  local choice = vim.fn.confirm(
    "[Alchemist] " .. message,
    "&Yes\n&No",
    default and 1 or 2
  )
  local confirmed = (choice == 1)
  return { confirmed = confirmed, value = confirmed and "y" or "n" }
end

---@param message string
---@param default string|nil
---@return table
function M._handle_text(message, default)
  local value = vim.fn.input({
    prompt = "[Alchemist] " .. message .. ": ",
    default = default or "",
  })
  if value and value ~= "" then
    return { confirmed = true, value = value }
  else
    return { confirmed = false, value = nil }
  end
end

---@param message string
---@param default any
---@return table
function M._handle_selection(message, default)
  local options = {}
  if type(default) == "table" then
    options = default
  elseif type(default) == "string" then
    for line in default:gmatch("[^\n]+") do
      table.insert(options, line)
    end
  end

  if #options == 0 then
    return { confirmed = false, value = nil }
  end

  local prompt_str = "[Alchemist] " .. message .. "\n"
  for i, opt in ipairs(options) do
    prompt_str = prompt_str .. "&" .. i .. ". " .. opt .. "\n"
  end

  local choice = vim.fn.confirm(prompt_str, table.concat(
    vim.tbl_map(function(_, i) return "&" .. i end,
      vim.fn.range(1, #options)), "\n"))

  if choice > 0 and choice <= #options then
    return { confirmed = true, value = options[choice] }
  else
    return { confirmed = false, value = nil }
  end
end

return M
