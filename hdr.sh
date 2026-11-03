#!/usr/bin/env bash
# HDR na monitorze: dopisuje/usuwa "bitdepth, 10, cm, hdr" w jego linii w monitors.conf i przeładowuje Hyprlanda.
#   hdr.sh <MONITOR> status   -> on / off (stan z Hyprlanda)
#   hdr.sh <MONITOR> on|off|toggle
#   hdr.sh status             -> dla aktywnego monitora (tak samo z on/off/toggle)
# Używa go command center (kafelek jasności, [T]).

conf="$HOME/.config/hypr/monitors.conf"

if [[ $# -eq 1 ]]; then
    mon=$(hyprctl monitors -j | jq -r '.[] | select(.focused) | .name')
    action=$1
else
    mon=$1
    action=${2:-status}
fi

state() {
    hyprctl monitors -j | jq -r --arg m "$mon" \
        '.[] | select(.name == $m) | if (.colorManagementPreset | test("^hdr")) then "on" else "off" end'
}

cur=$(state)
[[ -z "$cur" ]] && { echo "Nie ma monitora $mon (hyprctl monitors)" >&2; exit 2; }

case "$action" in
status) echo "$cur"; exit 0 ;;
toggle) [[ "$cur" == on ]] && want=off || want=on ;;
on | off) want=$action ;;
*) echo "użycie: $0 [MONITOR] status|on|off|toggle" >&2; exit 1 ;;
esac

[[ "$cur" == "$want" ]] && { echo "$cur"; exit 0; }

n=$(grep -nE "^\s*monitor\s*=\s*$mon\s*," "$conf" | head -1 | cut -d: -f1)
[[ -z "$n" ]] && { echo "Brak linii 'monitor = $mon, …' w $conf" >&2; exit 3; }

sed -i -E "${n}s/,\s*bitdepth\s*,\s*[0-9]+//; ${n}s/,\s*cm\s*,\s*[a-z0-9]+//" "$conf"
[[ "$want" == on ]] && sed -i -E "${n}s/\s*$/, bitdepth, 10, cm, hdr/" "$conf"

hyprctl reload >/dev/null
# monitor przestawia się chwilę (ekran mignie) – czekamy, aż Hyprland zgłosi nowy stan
for _ in $(seq 1 25); do
    [[ "$(state)" == "$want" ]] && { echo "$want"; exit 0; }
    sleep 0.2
done
echo "Hyprland nie przełączył HDR (stan: $(state))" >&2
exit 4
