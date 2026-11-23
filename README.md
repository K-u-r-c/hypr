# hypr

Moja konfiguracja **Hyprlanda**: bez odstępów i ramek, rozmycie warstw, polski układ klawiatury. Do tego skrypty od tapet (obrazy i wideo) i monitorów, z których korzystają też [waybar](https://github.com/K-u-r-c/waybar), [command-center](https://github.com/K-u-r-c/command-center) i [wall-downloader](https://github.com/K-u-r-c/wall-downloader).

> Część zestawu **[linux-tools](https://github.com/K-u-r-c/linux-tools)**: tam jest mapa, co z czym współpracuje, i instalator.

## Pliki

| Plik | Co |
|---|---|
| `hyprland.lua` | config (Lua, Hyprland 0.56+): bindy, wygląd, autostart (waybar, tapety, command center). Sprawdzenie: `Hyprland --verify-config -c ~/.config/hypr/hyprland.lua` |
| `hyprland.conf` | stary config w formacie `.conf` – zapas na okres przejściowy, Hyprland używa go tylko, gdy nie ma `hyprland.lua` (znika w 0.57) |
| `monitors.default.lua` | szablon `monitors.lua` (autodetekcja), patrz niżej |
| `monitors-detect.sh` | zapisuje aktualnie podłączone monitory do `monitors.lua` jako punkt wyjścia do edycji (`--print` tylko wypisuje) |
| `primary-monitor.sh` | nazwa głównego monitora: `$PRIMARY_MONITOR` albo największy (`--json` zwraca cały obiekt z `hyprctl`) |
| `wallpaper.sh` | tapety per monitor: obrazy przez **hyprpaper**, wideo i GIF-y przez **mpvpaper**. `restore`, `next`, `menu` (wofi), `set <monitor\|ALL> <plik>` |
| `screensaver.sh`, `hypridle.conf` | wygaszacz Matrix (cmatrix) po 5 min bezczynności, wyłączenie ekranu po 20 min (**hypridle**) |
| `workspace-osd.py` | po przełączeniu pulpitu na chwilę pokazuje jego numer i miniatury zajętych pulpitów (ostatni znany wygląd: mały zrzut `grim` ~1,2 s po wejściu na pulpit i po zmianach okien, z `nice 19`); poza tym działa na zdarzeniach Hyprlanda, bez odpytywania |
| `hdr.sh` | HDR on/off/toggle/status dla monitora: dopisuje lub usuwa `bitdepth = 10, cm = "hdr"` w jego linii w `monitors.lua` (i w `monitors.conf`, dopóki istnieje) (używa go command center, `[T]`) |
| `killactive.sh` | SUPER+W: zamyka okno, przy terminalu (Ghostty, Alacritty) najpierw pyta |
| `dispatch.sh` | `hyprctl dispatch` dla obu formatów configu: najpierw składnia Lua, a gdy Hyprland działa jeszcze na `.conf` – stara (używają go `killactive.sh` i waybar) |
| `hyprpaper.conf` | zapasowy config hyprpapera (normalnie generuje go `wallpaper.sh`) |

Menu tapet i pytanie przy zamykaniu terminala używają wofi ze stylem `~/.config/wofi/style.css`. Bez tego pliku wofi wygląda domyślnie.

Tapety leżą w `~/Pictures/wallpapers`. Pliki z prefiksem `uw-` to tapety 21:9 i trafiają najpierw na monitory ultrawide. Miniatury są w `~/.cache/wallpaper-thumbs`.

## Instalacja

```bash
sudo pacman -S --needed hyprland hyprpaper jq wofi grim slurp wl-clipboard ghostty alacritty dolphin hypridle cmatrix python-gobject gtk3 gtk-layer-shell python-cairo
paru -S --needed mpvpaper            # tapety wideo (AUR)

[ -d ~/.config/hypr ] && mv ~/.config/hypr ~/.config/hypr.bak
git clone https://github.com/K-u-r-c/hypr ~/.config/hypr
cp ~/.config/hypr/monitors.default.lua ~/.config/hypr/monitors.lua   # potem ewentualnie: ~/.config/hypr/monitors-detect.sh
```

`hyprland.lua` odpala też [waybar](https://github.com/K-u-r-c/waybar) i [command-center](https://github.com/K-u-r-c/command-center). Bez nich Hyprland działa, tylko te linie nic nie robią. Najprościej wszystko naraz: [linux-tools](https://github.com/K-u-r-c/linux-tools).

Aktualizacja: `git -C ~/.config/hypr pull` (Hyprland sam przeładuje config).

## Monitory

Wszystko, co zależy od konkretnego komputera, siedzi w `~/.config/hypr/monitors.lua`. Ten plik nie jest w repo (`.gitignore`), a `hyprland.lua` go wczytuje (`require("monitors")`):

```lua
hl.monitor({ output = "DP-1", mode = "3440x1440@144", position = "0x0", scale = 1 })
hl.env("PRIMARY_MONITOR", "DP-1")      -- monitor z waybarem; bez tego: największy
hl.workspace_rule({ workspace = "1", monitor = "DP-1", default = true })
```

## Bindy

| Skrót | Akcja |
|---|---|
| SUPER+Enter | [Ghostty](https://github.com/K-u-r-c/ghostty) |
| SUPER+TAB / SUPER+SHIFT+TAB | [command center](https://github.com/K-u-r-c/command-center) / jego restart |
| SUPER+W | zamknij okno |
| SUPER+E / Z / G | Dolphin / Zen / hyprlauncher |
| SUPER+V | okno pływające |
| SUPER+strzałki, +SHIFT, +CTRL | fokus / przesuwanie / rozmiar okna |
| SUPER+1…9, 0 (=10), +SHIFT | workspace / przeniesienie okna |
| Print, SHIFT+Print, CTRL+Print | zrzut ekranu / obszaru do `~/Pictures` i schowka / obszaru tylko do schowka |
| SUPER+M | wyjście z Hyprlanda |
