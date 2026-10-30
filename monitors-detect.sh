#!/usr/bin/env bash
# Zapisuje AKTUALNIE wykryte monitory do monitors.conf jako punkt wyjścia do ręcznej edycji
# i przeładowuje Hyprlanda. Poprzedni plik ląduje w monitors.conf.bak-<data>.
#   monitors-detect.sh          -> zapisz + hyprctl reload
#   monitors-detect.sh --print  -> tylko wypisz, nic nie zmieniaj

conf="$HOME/.config/hypr/monitors.conf"
mons=$(hyprctl monitors -j) || { echo "Nie mogę odpytać Hyprlanda (hyprctl monitors)"; exit 1; }
primary=$("$HOME/.config/hypr/primary-monitor.sh")

generate() {
    echo "# Wygenerowane przez monitors-detect.sh $(date '+%F %T') – edytuj śmiało."
    echo "# Składnia: monitor = NAZWA, ROZDZIELCZOŚĆ@HZ, POZYCJA, SKALA[, transform, 0-3]"
    echo
    jq -r '.[] |
        "# \(.description)\n# dostępne tryby: \(.availableModes | join(" "))\n" +
        "monitor = \(.name), \(.width)x\(.height)@\(.refreshRate * 100 | round / 100), \(.x)x\(.y), \(.scale)" +
        (if .transform != 0 then ", transform, \(.transform)" else "" end) + "\n"' <<<"$mons"
    echo "# monitor z waybarem / domyślny dla tapet \"na wszystkich\""
    echo "env = PRIMARY_MONITOR,$primary"
    echo
    # workspace 1 na głównym, 2, 3… po jednym na pozostałych
    local i=1 m
    for m in "$primary" $(jq -r --arg p "$primary" '.[].name | select(. != $p)' <<<"$mons"); do
        echo "workspace = $i, monitor:$m$( ((i == 1)) && echo ', default:true')"
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
