if vim.g.loaded_alchemist then
  return
end
vim.g.loaded_alchemist = true

if vim.fn.has("nvim-0.9.0") ~= 1 then
  vim.notify("[Alchemist] Requires NeoVim >= 0.9.0", vim.log.levels.ERROR)
  return
end
