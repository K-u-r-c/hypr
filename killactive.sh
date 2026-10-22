#!/usr/bin/env bash

if pgrep -x wofi >/dev/null; then
    pkill -x wofi
    exit 0
fi

active_json=$(hyprctl activewindow -j)
win_class=$(printf '%s' "$active_json" | jq -r '.class // empty')
win_addr=$(printf '%s' "$active_json" | jq -r '.address // empty')

if [[ -z "$win_addr" ]]; then
    exit 0
fi

if [[ "${win_class,,}" == "alacritty" ]]; then
    choice=$(printf "No\nYes\n" | wofi --dmenu \
        --style "$HOME/.config/wofi/style.css" \
        --prompt "[?] Close Alacritty?" \
        --pre-display-cmd "echo '> %s'" \
        --define use_search_box=false \
        --define dynamic_lines=true \
        --hide-scroll \
        --width 340 \
        --lines 2 \
        --cache-file /dev/null \
        --insensitive)

    if [[ "$choice" == "Yes" ]]; then
        hyprctl dispatch closewindow "address:$win_addr"
    fi
else
    hyprctl dispatch killactive
fi
