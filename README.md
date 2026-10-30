# hypr

Moja konfiguracja **Hyprlanda**: bez odstępów i ramek, rozmycie warstw, polski układ klawiatury. Do tego skrypty od tapet (obrazy i wideo) i monitorów, z których korzystają też [waybar](https://github.com/K-u-r-c/waybar), [command-center](https://github.com/K-u-r-c/command-center) i [wall-downloader](https://github.com/K-u-r-c/wall-downloader).

> Część zestawu **[linux-tools](https://github.com/K-u-r-c/linux-tools)**: tam jest mapa, co z czym współpracuje, i instalator.

## Pliki

| Plik | Co |
|---|---|
| `hyprland.conf` | config: bindy, wygląd, autostart (waybar, tapety, command center) |
| `monitors.default.conf` | szablon `monitors.conf` (autodetekcja), patrz niżej |
| `monitors-detect.sh` | zapisuje aktualnie podłączone monitory do `monitors.conf` jako punkt wyjścia do edycji (`--print` tylko wypisuje) |
| `primary-monitor.sh` | nazwa głównego monitora: `$PRIMARY_MONITOR` albo największy (`--json` zwraca cały obiekt z `hyprctl`) |
| `wallpaper.sh` | tapety per monitor: obrazy przez **hyprpaper**, wideo i GIF-y przez **mpvpaper**. `restore`, `next`, `menu` (wofi), `set <monitor\|ALL> <plik>` |
| `killactive.sh` | SUPER+W: zamyka okno, przy Alacritty najpierw pyta |
| `hyprpaper.conf` | zapasowy config hyprpapera (normalnie generuje go `wallpaper.sh`) |

Menu tapet i pytanie przy zamykaniu Alacritty używają wofi ze stylem `~/.config/wofi/style.css`. Bez tego pliku wofi wygląda domyślnie.

Tapety leżą w `~/Pictures/wallpapers`. Pliki z prefiksem `uw-` to tapety 21:9 i trafiają najpierw na monitory ultrawide. Miniatury są w `~/.cache/wallpaper-thumbs`.

## Instalacja

```bash
sudo pacman -S --needed hyprland hyprpaper jq wofi grim slurp wl-clipboard alacritty dolphin
paru -S --needed mpvpaper            # tapety wideo (AUR)

[ -d ~/.config/hypr ] && mv ~/.config/hypr ~/.config/hypr.bak
git clone https://github.com/K-u-r-c/hypr ~/.config/hypr
cp ~/.config/hypr/monitors.default.conf ~/.config/hypr/monitors.conf   # potem ewentualnie: ~/.config/hypr/monitors-detect.sh
```

`hyprland.conf` odpala też [waybar](https://github.com/K-u-r-c/waybar) i [command-center](https://github.com/K-u-r-c/command-center). Bez nich Hyprland działa, tylko te linie nic nie robią. Najprościej wszystko naraz: [linux-tools](https://github.com/K-u-r-c/linux-tools).

Aktualizacja: `git -C ~/.config/hypr pull` (Hyprland sam przeładuje config).

## Monitory

Wszystko, co zależy od konkretnego komputera, siedzi w `~/.config/hypr/monitors.conf`. Ten plik nie jest w repo (`.gitignore`), a `hyprland.conf` go wczytuje:

```ini
monitor = DP-1, 3440x1440@144, 0x0, 1
env = PRIMARY_MONITOR,DP-1               # monitor z waybarem; bez tego: największy
workspace = 1, monitor:DP-1, default:true
```

## Bindy

| Skrót | Akcja |
|---|---|
| SUPER+Enter | Alacritty |
| SUPER+TAB / SUPER+SHIFT+TAB | [command center](https://github.com/K-u-r-c/command-center) / jego restart |
| SUPER+W | zamknij okno |
| SUPER+E / Z / G | Dolphin / Zen / hyprlauncher |
| SUPER+V | okno pływające |
| SUPER+strzałki, +SHIFT, +CTRL | fokus / przesuwanie / rozmiar okna |
| SUPER+1…5, +SHIFT | workspace / przeniesienie okna |
| Print, SHIFT+Print, CTRL+Print | zrzut ekranu / obszaru do `~/Pictures` i schowka / obszaru tylko do schowka |
| SUPER+M | wyjście z Hyprlanda |
