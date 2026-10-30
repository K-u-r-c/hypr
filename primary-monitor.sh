#!/usr/bin/env bash
# Główny monitor (waybar, domyślny cel tapet): $PRIMARY_MONITOR z monitors.conf,
# a gdy nie jest ustawiony albo nie jest podłączony – największy.
#   primary-monitor.sh         -> nazwa, np. DP-1
#   primary-monitor.sh --json  -> obiekt z hyprctl monitors -j

mons=$(hyprctl monitors -j) || exit 1
pick='max_by(.width * .height)'
if [[ -n "${PRIMARY_MONITOR:-}" ]] && jq -e --arg m "$PRIMARY_MONITOR" 'any(.[]; .name == $m)' <<<"$mons" >/dev/null; then
    pick="map(select(.name == \"$PRIMARY_MONITOR\"))[0]"
fi

if [[ "${1:-}" == "--json" ]]; then
    jq -c "$pick" <<<"$mons"
else
    jq -r "$pick.name" <<<"$mons"
fi
