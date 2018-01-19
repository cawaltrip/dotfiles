local awful = require('awful')
local gears = require('gears')
local l = awful.layout.suit

-- [[
-- Layouts that I'm using
-- 1.  max
-- 2.  tile
-- 3.  floating
-- ]]

local names = {
    "main",
    "www",
    "video?",
    "vm"
}

local layouts = {
    l.floating,
    l.tile,
    l.max,
    l.tile
}

awful.tag(names, s, layouts)

-- A lot of inspiration can come from: https://github.com/timroes/awesome-config
-- vim: filetype=lua:expandtab:shiftwidth=4:tabstop=8:softtabstop=4:textwidth=80
