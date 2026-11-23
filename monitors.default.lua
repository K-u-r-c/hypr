-- Domyślne monitory (komputer bez własnego profilu w dotfiles/machines/<hostname>/):
-- Hyprland sam wykrywa monitory – natywna rozdzielczość, ustawione obok siebie, skala dobrana automatycznie.
--
-- Własne ustawienia – edytuj ~/.config/hypr/monitors.lua (ten plik to tylko szablon), np.:
--   ~/.config/hypr/monitors-detect.sh     -> zapisze wykryte monitory jako punkt wyjścia
--   hl.monitor({ output = "NAZWA", mode = "2560x1440@144", position = "0x0", scale = 1 })
--   hl.env("PRIMARY_MONITOR", "NAZWA")    -> monitor z waybarem (domyślnie największy)
--   hl.workspace_rule({ workspace = "1", monitor = "NAZWA", default = true })
-- Nazwy i tryby: hyprctl monitors

hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })
