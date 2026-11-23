-- Konfiguracja Hyprlanda w Lua (od 0.56; format .conf znika w 0.57).
-- API: /usr/share/hypr/stubs/hl.meta.lua, przykład: /usr/share/hypr/hyprland.lua, wiki: https://wiki.hypr.land/Configuring/Start/
-- Sprawdzenie bez uruchamiania: Hyprland --verify-config -c ~/.config/hypr/hyprland.lua

-- monitory + przypisanie workspace'ów są per-komputer
require("monitors")

local mainMod     = "SUPER"
local terminal    = "ghostty"
local fileManager = "dolphin"
local menu        = "hyprlauncher"
local browser     = "zen-browser"

-------------------
---- AUTOSTART ----
-------------------

hl.on("hyprland.start", function()
    hl.exec_cmd("~/.config/waybar/launch.sh")
    hl.exec_cmd("~/.config/hypr/wallpaper.sh restore")
    hl.exec_cmd("~/.config/waybar/autohide.sh")
    -- wygaszacz po 5 min, wyłączenie ekranu po 20 min (hypridle.conf, screensaver.sh)
    hl.exec_cmd("hypridle")
    -- RGB (OpenRGB): po starcie urządzenia wracają do swoich domyślnych – nakładamy ostatni wybór (rgb-mode z dotfiles)
    hl.exec_cmd("[ -x ~/.local/bin/rgb-mode ] && ~/.local/bin/rgb-mode restore")
    -- numer pulpitu na chwilę na środku ekranu po przełączeniu (workspace-osd.py)
    hl.exec_cmd("~/.config/hypr/workspace-osd.py")
    -- command center: https://github.com/K-u-r-c/command-center (~/.local/bin/command-center -> command_center.py)
    hl.exec_cmd("~/.local/bin/command-center --daemon")
end)

-----------------------
---- LOOK AND FEEL ----
-----------------------

hl.config({
    input = {
        kb_layout    = "pl",
        follow_mouse = 1,

        touchpad = {
            natural_scroll = false,
        },
    },

    general = {
        gaps_in     = 0,
        gaps_out    = 0,
        border_size = 0,
        layout      = "dwindle",

        col = {
            active_border   = "rgba(555555ff)",
            inactive_border = "rgba(222222ff)",
        },
    },

    decoration = {
        blur = {
            enabled           = true,
            size              = 8,
            passes            = 3,
            new_optimizations = true,
        },
    },

    animations = {
        enabled = true,
    },
})

hl.animation({ leaf = "layersIn",  enabled = true, speed = 4,   bezier = "default", style = "fade" })
hl.animation({ leaf = "layersOut", enabled = true, speed = 1.3, bezier = "default", style = "fade" })
-- czas zanikania warstw (np. workspace-osd); bez tego dziedziczy globalne 800 ms
hl.animation({ leaf = "fadeLayersOut", enabled = true, speed = 4, bezier = "default" })

hl.layer_rule({ name = "blur-command-center", match = { namespace = "^(command-center)$" }, blur = true })
hl.layer_rule({ name = "blur-workspace-osd",  match = { namespace = "^(workspace-osd)$" },  blur = true })
hl.layer_rule({ name = "anim-workspace-osd",  match = { namespace = "^(workspace-osd)$" },  animation = "popin 85%" })

---------------------
---- KEYBINDINGS ----
---------------------

local function bind(keys, dispatcher, opts)
    hl.bind(mainMod .. " + " .. keys, dispatcher, opts)
end

bind("RETURN", hl.dsp.exec_cmd(terminal))
bind("W",      hl.dsp.exec_cmd("~/.config/hypr/killactive.sh"))
bind("M",      hl.dsp.exit())
bind("E",      hl.dsp.exec_cmd(fileManager))
bind("G",      hl.dsp.exec_cmd(menu))
bind("V",      hl.dsp.window.float({ action = "toggle" }))
bind("Z",      hl.dsp.exec_cmd(browser))
bind("TAB",    hl.dsp.exec_cmd("~/.local/bin/command-center"))
-- Emergency: kill a stuck command center and start a fresh daemon
bind("SHIFT + TAB", hl.dsp.exec_cmd("~/.local/bin/command-center-restart"))

for _, dir in ipairs({ "left", "right", "up", "down" }) do
    bind(dir,              hl.dsp.focus({ direction = dir }))
    bind("SHIFT + " .. dir, hl.dsp.window.move({ direction = dir }))
end

bind("mouse:272", hl.dsp.window.drag(),   { mouse = true })
bind("mouse:273", hl.dsp.window.resize(), { mouse = true })

-- pulpity 1–10 (klawisz 0 = pulpit 10)
for i = 1, 10 do
    local key = i % 10
    bind(key,              hl.dsp.focus({ workspace = i }))
    bind("SHIFT + " .. key, hl.dsp.window.move({ workspace = i }))
end

bind("CTRL + left",  hl.dsp.window.resize({ x = -50, y = 0,   relative = true }), { repeating = true })
bind("CTRL + right", hl.dsp.window.resize({ x = 50,  y = 0,   relative = true }), { repeating = true })
bind("CTRL + up",    hl.dsp.window.resize({ x = 0,   y = -50, relative = true }), { repeating = true })
bind("CTRL + down",  hl.dsp.window.resize({ x = 0,   y = 50,  relative = true }), { repeating = true })

hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"))
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"))
hl.bind("XF86AudioMute",        hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"))

hl.bind("Print",         hl.dsp.exec_cmd('grim - | tee ~/Pictures/$(date +%Y-%m-%d_%H-%M-%S).png | wl-copy'))
hl.bind("SHIFT + Print", hl.dsp.exec_cmd('grim -g "$(slurp)" - | tee ~/Pictures/$(date +%Y-%m-%d_%H-%M-%S).png | wl-copy'))
hl.bind("CTRL + Print",  hl.dsp.exec_cmd('grim -g "$(slurp)" - | wl-copy'))

----------------------
---- WINDOW RULES ----
----------------------

-- Wygaszacz (screensaver.sh): pływający na cały monitor, bez animacji wejścia
hl.window_rule({
    name    = "screensaver",
    match   = { class = "^(screensaver)$" },
    float   = true,
    size    = "monitor_w monitor_h",
    move    = "0 0",
    pin     = true,
    no_anim = true,
})

-- Gry (Steam, Heroic przez Protona: klasa steam_app_…) jako "game": VRR w trybie fullscreen_game (monitors.lua)
-- włącza się tylko dla nich, a nie dla filmów na pełnym ekranie w przeglądarce
hl.window_rule({ name = "games", match = { class = "^(steam_app_.*)$" }, content = "game" })
-- Genshin Impact (Heroic): BEZ VRR – przełączanie VRR <-> stałe 240 Hz przy zmianie pulpitu dawało mignięcie obrazu
hl.window_rule({ name = "genshin-no-vrr", match = { class = "^(steam_app_7d690c122fde4c60bed85405f343ad10)$" }, content = "none" })

-- Dolphin: match Alacritty opacity
hl.window_rule({ name = "dolphin-opacity", match = { class = "^(org.kde.dolphin)$" }, opacity = "0.95 0.95" })
