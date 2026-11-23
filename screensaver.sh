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
    # cmatrix rysuje kolorami palety (normal.black = tło, normal/bright.white = znaki), nie primary.background,
    # więc nadpisujemy je na czystą czerń i biel. sleep: cmatrix musi wystartować dopiero po tym, jak
    # Hyprland rozciągnie okno na cały monitor, bo inaczej zostaje w rozmiarze startowym (róg ekranu).
    exec alacritty --class "$class" \
        -o 'window.opacity=1.0' -o 'window.padding={x=0,y=0}' \
        -o 'colors.primary.background="#000000"' \
        -o 'colors.normal.black="#000000"' -o 'colors.bright.black="#000000"' \
        -o 'colors.normal.white="#ffffff"' -o 'colors.bright.white="#ffffff"' \
        -e sh -c 'sleep 0.3; exec cmatrix -b -u 6 -C white'
    ;;
stop)
    pkill -f "alacritty --class $class"
    ;;
*)
    echo "użycie: $0 start|stop" >&2; exit 1
    ;;
esac
