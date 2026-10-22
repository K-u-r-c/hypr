#!/usr/bin/env bash

export PATH="$HOME/.local/bin:$PATH"

WALL_DIR="$HOME/Pictures/wallpapers"
THUMB_DIR="$HOME/.cache/wallpaper-thumbs"
WOFI_STYLE="$HOME/.config/wofi/style.css"
MONITORS=("DP-1" "HDMI-A-1")

mkdir -p "$WALL_DIR" "$THUMB_DIR"

state_file() {
    printf '%s/.config/hypr/.wallpaper_%s' "$HOME" "$1"
}

get_current_wp() {
    local mon="$1"
    local sf
    sf=$(state_file "$mon")
    if [[ -f "$sf" ]]; then
        cat "$sf"
    elif [[ -f "$HOME/.config/hypr/.current_wallpaper" ]]; then
        cat "$HOME/.config/hypr/.current_wallpaper"
    fi
}

list_wallpapers() {
    find "$WALL_DIR" -maxdepth 1 -type f \( \
        -iname "*.mp4" -o \
        -iname "*.webm" -o \
        -iname "*.mkv" -o \
        -iname "*.gif" -o \
        -iname "*.jpg" -o \
        -iname "*.jpeg" -o \
        -iname "*.png" -o \
        -iname "*.webp" \
    \) | sort
}

ensure_thumb() {
    local wp="$1"
    local base
    base=$(basename "$wp")
    local thumb="$THUMB_DIR/${base}.png"
    if [[ ! -f "$thumb" || "$wp" -nt "$thumb" ]]; then
        ffmpeg -y -v error -i "$wp" \
            -vf "scale=160:90:force_original_aspect_ratio=increase,crop=160:90" \
            -frames:v 1 "$thumb" </dev/null >/dev/null 2>&1
    fi
    printf '%s' "$thumb"
}

apply_monitor_wp() {
    local mon="$1"
    local wp="$2"
    if [[ ! -f "$wp" ]]; then
        return 1
    fi

    printf '%s\n' "$wp" > "$(state_file "$mon")"

    pkill -x hyprpaper 2>/dev/null
    pkill -f "mpvpaper .* \\* " 2>/dev/null
    pkill -f "mpvpaper .* ${mon} " 2>/dev/null
    sleep 0.1

    mpvpaper -f -p -o "no-audio --loop-file=inf --image-display-duration=inf --hwdec=auto --panscan=1.0" "$mon" "$wp" >/dev/null 2>&1
}

apply_target() {
    local target="$1"
    local wp="$2"
    if [[ "$target" == "ALL" ]]; then
        for m in "${MONITORS[@]}"; do
            apply_monitor_wp "$m" "$wp"
        done
    else
        apply_monitor_wp "$target" "$wp"
        for m in "${MONITORS[@]}"; do
            if [[ "$m" != "$target" ]] && ! pgrep -f "mpvpaper .* ${m} " >/dev/null; then
                other_wp=$(get_current_wp "$m")
                [[ -f "$other_wp" ]] && apply_monitor_wp "$m" "$other_wp"
            fi
        done
    fi
}

cmd="${1:-menu}"

case "$cmd" in
    set)
        if [[ $# -ge 3 ]]; then
            apply_target "$2" "$3"
        else
            apply_target "ALL" "$2"
        fi
        ;;
    restore)
        first=$(list_wallpapers | head -n 1)
        for m in "${MONITORS[@]}"; do
            saved=$(get_current_wp "$m")
            if [[ -f "$saved" ]]; then
                apply_monitor_wp "$m" "$saved"
            elif [[ -n "$first" ]]; then
                apply_monitor_wp "$m" "$first"
            fi
        done
        ;;
    next)
        mapfile -t files < <(list_wallpapers)
        [[ ${#files[@]} -eq 0 ]] && exit 0
        focused_mon=$(hyprctl monitors -j | jq -r '.[] | select(.focused == true) | .name' | head -n 1)
        [[ -z "$focused_mon" ]] && focused_mon="DP-1"
        current=$(get_current_wp "$focused_mon")
        next_idx=0
        for i in "${!files[@]}"; do
            if [[ "${files[$i]}" == "$current" ]]; then
                next_idx=$(( (i + 1) % ${#files[@]} ))
                break
            fi
        done
        apply_target "$focused_mon" "${files[$next_idx]}"
        ;;
    menu)
        if pgrep -x wofi >/dev/null; then
            pkill -x wofi
            exit 0
        fi

        mapfile -t all_files < <(list_wallpapers)
        [[ ${#all_files[@]} -eq 0 ]] && exit 0

        cur_dp=$(basename "$(get_current_wp DP-1)" 2>/dev/null)
        cur_hdmi=$(basename "$(get_current_wp HDMI-A-1)" 2>/dev/null)
        [[ -z "$cur_dp" ]] && cur_dp="none"
        [[ -z "$cur_hdmi" ]] && cur_hdmi="none"

        mon_choice=$(printf "DP-1   (3440x1440) [current: %s]\nHDMI-A-1 (1920x1080) [current: %s]\nBoth monitors (DP-1 + HDMI-A-1)\n" "${cur_dp%.*}" "${cur_hdmi%.*}" | wofi --dmenu \
            --style "$WOFI_STYLE" \
            --prompt "[*] Select Monitor:" \
            --pre-display-cmd "echo '> %s'" \
            --define use_search_box=false \
            --define dynamic_lines=true \
            --hide-scroll \
            --width 560 \
            --lines 3 \
            --cache-file /dev/null \
            --insensitive)

        [[ -z "$mon_choice" ]] && exit 0

        case "$mon_choice" in
            Both*) target_mon="ALL"; ref_mon="DP-1" ;;
            DP-1*) target_mon="DP-1"; ref_mon="DP-1" ;;
            HDMI-A-1*) target_mon="HDMI-A-1"; ref_mon="HDMI-A-1" ;;
            *) exit 0 ;;
        esac

        # Sort wallpapers so the ones matching the selected monitor's aspect ratio appear first
        uw_files=()
        fhd_files=()
        for f in "${all_files[@]}"; do
            b=$(basename "$f")
            if [[ "$b" == uw-* ]]; then
                uw_files+=("$f")
            else
                fhd_files+=("$f")
            fi
        done

        if [[ "$ref_mon" == "DP-1" ]]; then
            files=("${uw_files[@]}" "${fhd_files[@]}")
        else
            files=("${fhd_files[@]}" "${uw_files[@]}")
        fi

        current=$(get_current_wp "$ref_mon")

        menu_items=()
        for f in "${files[@]}"; do
            base=$(basename "$f")
            name="${base%.*}"
            name="${name#uw-}"
            thumb=$(ensure_thumb "$f")
            case "${f,,}" in
                *.mp4|*.webm|*.mkv|*.gif) type_tag="anim" ;;
                *) type_tag="img " ;;
            esac
            if [[ "$base" == uw-* ]]; then
                res_tag="21:9"
            else
                res_tag="16:9"
            fi
            if [[ "$f" == "$current" ]]; then
                menu_items+=("img-noscale:${thumb}:text:* [$res_tag|$type_tag] $name ($base)")
            else
                menu_items+=("img-noscale:${thumb}:text:  [$res_tag|$type_tag] $name ($base)")
            fi
        done

        lines=${#menu_items[@]}
        (( lines > 5 )) && lines=5

        choice=$(printf '%s\n' "${menu_items[@]}" | wofi --dmenu \
            --allow-images \
            --define dmenu-parse_action=true \
            --style "$WOFI_STYLE" \
            --prompt "[*] Wallpaper ($target_mon):" \
            --define use_search_box=false \
            --define dynamic_lines=true \
            --hide-scroll \
            --width 660 \
            --lines "$lines" \
            --cache-file /dev/null \
            --insensitive)

        if [[ -n "$choice" ]]; then
            selected_base=$(printf '%s' "$choice" | sed -E 's/^.*\(([^)]+)\)$/\1/')
            if [[ -f "$WALL_DIR/$selected_base" ]]; then
                apply_target "$target_mon" "$WALL_DIR/$selected_base"
            fi
        fi
        ;;
esac
