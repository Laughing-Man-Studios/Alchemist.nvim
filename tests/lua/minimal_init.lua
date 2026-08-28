local plenary_dir = os.getenv("PLENARY_DIR") or "/tmp/plenary.nvim"
local nui_dir = os.getenv("NUI_DIR") or "/tmp/nui.nvim"

if vim.fn.isdirectory(plenary_dir) == 0 then
  vim.fn.system({
    "git", "clone", "--depth=1",
    "https://github.com/nvim-lua/plenary.nvim",
    plenary_dir,
  })
end

if vim.fn.isdirectory(nui_dir) == 0 then
  vim.fn.system({
    "git", "clone", "--depth=1",
    "https://github.com/MunifTanjim/nui.nvim",
    nui_dir,
  })
end

vim.opt.rtp:prepend(".")
vim.opt.rtp:prepend(plenary_dir)
vim.opt.rtp:prepend(nui_dir)

vim.cmd("runtime plugin/plenary.vim")
