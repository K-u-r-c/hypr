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

case "${win_class,,}" in
    alacritty)             term_name="Alacritty" ;;
    com.mitchellh.ghostty) term_name="Ghostty" ;;
    *)                     term_name="" ;;
esac

if [[ -n "$term_name" ]]; then
    choice=$(printf "No\nYes\n" | wofi --dmenu \
        --style "$HOME/.config/wofi/style.css" \
        --prompt "[?] Close $term_name?" \
        --pre-display-cmd "echo '> %s'" \
        --define use_search_box=false \
        --define dynamic_lines=true \
        --hide-scroll \
        --width 340 \
        --lines 2 \
        --cache-file /dev/null \
        --insensitive)

    if [[ "$choice" == "Yes" ]]; then
        "$HOME/.config/hypr/dispatch.sh" "hl.dsp.window.close({ window = \"address:$win_addr\" })" closewindow "address:$win_addr"
    fi
else
    "$HOME/.config/hypr/dispatch.sh" "hl.dsp.window.close()" killactive
fi
