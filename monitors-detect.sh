#!/usr/bin/env bash
# Zapisuje AKTUALNIE wykryte monitory do monitors.lua jako punkt wyjścia do ręcznej edycji
# i przeładowuje Hyprlanda. Poprzedni plik ląduje w monitors.lua.bak-<data>.
#   monitors-detect.sh          -> zapisz + hyprctl reload
#   monitors-detect.sh --print  -> tylko wypisz, nic nie zmieniaj

conf="$HOME/.config/hypr/monitors.lua"
mons=$(hyprctl monitors -j) || { echo "Nie mogę odpytać Hyprlanda (hyprctl monitors)"; exit 1; }
primary=$("$HOME/.config/hypr/primary-monitor.sh")

generate() {
    echo "-- Wygenerowane przez monitors-detect.sh $(date '+%F %T') – edytuj śmiało."
    echo "-- Każdy hl.monitor({ ... }) w jednej linii (hdr.sh ją edytuje). Pola: output, mode, position, scale[, transform]"
    echo
    jq -r '.[] |
        "-- \(.description)\n-- dostępne tryby: \(.availableModes | join(" "))\n" +
        "hl.monitor({ output = \"\(.name)\", mode = \"\(.width)x\(.height)@\(.refreshRate * 100 | round / 100)\", position = \"\(.x)x\(.y)\", scale = \(.scale)" +
        (if .transform != 0 then ", transform = \(.transform)" else "" end) + " })\n"' <<<"$mons"
    echo "-- monitor z waybarem / domyślny dla tapet \"na wszystkich\""
    echo "hl.env(\"PRIMARY_MONITOR\", \"$primary\")"
    echo
    # workspace 1 na głównym, 2, 3… po jednym na pozostałych
    local i=1 m
    for m in "$primary" $(jq -r --arg p "$primary" '.[].name | select(. != $p)' <<<"$mons"); do
        echo "hl.workspace_rule({ workspace = \"$i\", monitor = \"$m\"$( ((i == 1)) && echo ', default = true') })"
        i=$((i + 1))
    done
}

if [[ "${1:-}" == "--print" ]]; then
    generate
    exit 0
fi

[[ -f "$conf" ]] && cp "$conf" "$conf.bak-$(date +%Y%m%d-%H%M%S)"
generate > "$conf"
hyprctl reload >/dev/null
echo "Zapisano $conf (waybar przeniesie się na nowy główny monitor po ponownym zalogowaniu)"
