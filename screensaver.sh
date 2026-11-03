#!/usr/bin/env bash
# Wygaszacz Matrix (cmatrix w Alacritty na cały monitor). Odpalany przez hypridle (hypridle.conf).
#   screensaver.sh start  -> pokaż (pomija, gdy aktywne okno jest na pełnym ekranie: gra, film)
#   screensaver.sh stop   -> zamknij
# Okno jest pływające na cały ekran, a nie "fullscreen", żeby nie włączało VRR (na OLED-zie migałoby przy niskim fps).

class=screensaver

case "${1:-}" in
start)
    pgrep -f "alacritty --class $class" >/dev/null && exit 0
    [[ "$(hyprctl activewindow -j | jq -r '.fullscreen // 0')" != "0" ]] && exit 0
    exec alacritty --class "$class" \
        -o 'window.opacity=1.0' -o 'window.padding={x=0,y=0}' \
        -o 'colors.primary.background="#000000"' \
        -e cmatrix -b -u 6 -C green
    ;;
stop)
    pkill -f "alacritty --class $class"
    ;;
*)
    echo "użycie: $0 start|stop" >&2; exit 1
    ;;
esac
