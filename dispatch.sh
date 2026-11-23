#!/usr/bin/env bash
# hyprctl dispatch działający z obiema konfiguracjami Hyprlanda:
#   dispatch.sh '<dispatcher Lua>' <stary dispatcher> [argumenty…]
#   np. dispatch.sh 'hl.dsp.focus({ workspace = "e+1" })' workspace e+1
# Najpierw składnia Lua (hyprland.lua); gdy Hyprland jeszcze działa na hyprland.conf, odpowiada
# "Invalid dispatcher" i wtedy idzie stara składnia. Po usunięciu hyprland.conf (Hyprland 0.57+)
# można wołać po prostu: hyprctl dispatch '<dispatcher Lua>'.

# Starą składnię wołamy TYLKO przy "Invalid dispatcher" – inaczej przy innej odpowiedzi niż "ok"
# akcja mogłaby pójść dwa razy (np. zamknięcie dwóch okien).

lua=$1
shift
out=$(hyprctl dispatch "$lua")
if [[ "$out" == "Invalid dispatcher"* && $# -gt 0 ]]; then
    out=$(hyprctl dispatch "$@")
fi
[[ -z "$out" || "$out" == ok ]] && exit 0
echo "$out" >&2
exit 1
