#!/usr/bin/env bash

export PATH="$HOME/.local/bin:$PATH"

WALL_DIR="$HOME/Pictures/wallpapers"
THUMB_DIR="$HOME/.cache/wallpaper-thumbs"
WOFI_STYLE="$HOME/.config/wofi/style.css"
# monitory wykrywane na żywo – nic nie jest wpisane na sztywno (główny: hypr/primary-monitor.sh)
MONS_JSON=$(hyprctl monitors -j 2>/dev/null)
mapfile -t MONITORS < <(jq -r '.[].name' <<<"$MONS_JSON" 2>/dev/null)
PRIMARY=$("$HOME/.config/hypr/primary-monitor.sh" 2>/dev/null)
[[ -z "$PRIMARY" ]] && PRIMARY="${MONITORS[0]}"
mapfile -t MONITORS < <(printf '%s\n' "$PRIMARY" "${MONITORS[@]}" | awk 'NF && !seen[$0]++')   # główny pierwszy

mon_res() {
    jq -r --arg m "$1" '.[] | select(.name == $m) | "\(.width)x\(.height)"' <<<"$MONS_JSON"
}

# szeroki (21:9, 32:9) -> najpierw tapety uw-*
is_wide() {
    jq -e --arg m "$1" '.[] | select(.name == $m) | (.width / .height) >= 2' <<<"$MONS_JSON" >/dev/null
}

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

# jedno wywołanie naraz – równoległe uruchomienia (np. dwuklik) zostawiały po kilka mpvpaperów na monitor
lock() {
    exec 9>"${XDG_RUNTIME_DIR:-/tmp}/wallpaper.sh.lock"
    flock -w 15 9
}

is_image() {
    case "${1,,}" in
        *.png|*.jpg|*.jpeg|*.webp) return 0 ;;
    esac
    return 1
}

# zabija mpvpapera danego monitora ("\\*" = mpvpaper na wszystkich) i czeka, aż zniknie;
# po PID-ach, bo proces z martwym wątkiem głównym (wątek CUDA dalej wisi) traci cmdline i pgrep -f go nie widzi
stop_mpvpaper() {
    local pids p alive
    pids=$(pgrep -f "mpvpaper .* $1 ") || return 0
    kill $pids 2>/dev/null
    for _ in {1..40}; do
        alive=0
        for p in $pids; do
            is_alive "$p" && alive=1
        done
        (( alive )) || return 0
        sleep 0.05
    done
    kill -9 $pids 2>/dev/null
}

# istnieje i nie jest czystym zombie (zombie z żywymi wątkami dalej trzyma tapetę)
is_alive() {
    [[ -d /proc/$1 ]] || return 1
    [[ $(ls "/proc/$1/task" 2>/dev/null | wc -l) -gt 1 || "$(awk '{print $3}' "/proc/$1/stat" 2>/dev/null)" != Z ]]
}

# obrazy: jeden hyprpaper na wszystkie monitory (kilkanaście MB zamiast całego mpv na monitor);
# config generowany ze stanu monitorów, hyprpaper restartowany tylko gdy coś się zmieniło
sync_hyprpaper() {
    local conf="${XDG_RUNTIME_DIR:-/tmp}/hyprpaper-wallpaper.conf"
    local new="$conf.new" m wp
    : > "$new"
    for m in "${MONITORS[@]}"; do
        wp=$(get_current_wp "$m")
        if is_image "$wp" && [[ -f "$wp" ]]; then
            printf 'wallpaper {\n    monitor = %s\n    path = %s\n    fit_mode = cover\n}\n' "$m" "$wp" >> "$new"
        fi
    done

    if [[ ! -s "$new" ]]; then
        rm -f "$new" "$conf"
        pkill -x hyprpaper 2>/dev/null
        return 0
    fi
    if pgrep -x hyprpaper >/dev/null && cmp -s "$new" "$conf"; then
        rm -f "$new"
        return 0
    fi
    mv -f "$new" "$conf"
    pkill -x hyprpaper 2>/dev/null
    for _ in {1..40}; do
        pgrep -x hyprpaper >/dev/null || break
        sleep 0.05
    done
    setsid -f hyprpaper -c "$conf" >/dev/null 2>&1 9>&- </dev/null
}

apply_monitor_wp() {
    local mon="$1"
    local wp="$2"
    if [[ ! -f "$wp" ]]; then
        return 1
    fi

    printf '%s\n' "$wp" > "$(state_file "$mon")"

    stop_mpvpaper "\\*"
    stop_mpvpaper "$mon"
    sync_hyprpaper

    if ! is_image "$wp"; then
        # 9>&- – mpvpaper nie może trzymać blokady po wyjściu skryptu
        mpvpaper -f -p -o "no-audio --loop-file=inf --hwdec=auto --panscan=1.0" "$mon" "$wp" >/dev/null 2>&1 9>&-
    fi
}

apply_target() {
    local target="$1"
    local wp="$2"
    lock
    if [[ "$target" == "ALL" ]]; then
        for m in "${MONITORS[@]}"; do
            apply_monitor_wp "$m" "$wp"
        done
    else
        apply_monitor_wp "$target" "$wp"
        for m in "${MONITORS[@]}"; do
            # obrazy na pozostałych monitorach ogarnia już sync_hyprpaper; tu tylko brakujące wideo
            other_wp=$(get_current_wp "$m")
            if [[ "$m" != "$target" && -f "$other_wp" ]] && ! is_image "$other_wp" \
                && ! pgrep -f "mpvpaper .* ${m} " >/dev/null; then
                apply_monitor_wp "$m" "$other_wp"
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
        lock
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
        [[ -z "$focused_mon" ]] && focused_mon="$PRIMARY"
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

        if ((${#MONITORS[@]} == 1)); then
            target_mon="${MONITORS[0]}"; ref_mon="$target_mon"
        else
            mon_lines=()
            for m in "${MONITORS[@]}"; do
                cur=$(basename "$(get_current_wp "$m")" 2>/dev/null); cur="${cur%.*}"
                mon_lines+=("$m ($(mon_res "$m")) [current: ${cur:-none}]")
            done
            mon_lines+=("All monitors (${MONITORS[*]})")

            mon_choice=$(printf '%s\n' "${mon_lines[@]}" | wofi --dmenu \
                --style "$WOFI_STYLE" \
                --prompt "[*] Select Monitor:" \
                --pre-display-cmd "echo '> %s'" \
                --define use_search_box=false \
                --define dynamic_lines=true \
                --hide-scroll \
                --width 560 \
                --lines "${#mon_lines[@]}" \
                --cache-file /dev/null \
                --insensitive)

            [[ -z "$mon_choice" ]] && exit 0

            case "$mon_choice" in
                All*) target_mon="ALL"; ref_mon="$PRIMARY" ;;
                *) target_mon="${mon_choice%% *}"; ref_mon="$target_mon" ;;
            esac
        fi

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

        if is_wide "$ref_mon"; then
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
