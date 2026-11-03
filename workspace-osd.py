#!/usr/bin/env python3
# Wskaźnik pulpitu: po przełączeniu na chwilę pokazuje na środku ekranu numer pulpitu i miniatury
# zajętych pulpitów (aktywny podświetlony). Autostart w hyprland.conf, animację robi Hyprland (layerrule).
#
# Miniatury: Hyprland nie daje zrzutu niewidocznego pulpitu, więc każdy pulpit jest fotografowany
# (grim, mała skala) ~1,2 s po wejściu na niego i ~1,5 s po zmianie okien – pokazywany jest ostatni
# znany wygląd. Zrzut kosztuje ~0,4 s CPU (odczyt 4K z karty), robiony z nice 19, najwyżej raz na zdarzenie.
# Poza tym działa tylko na zdarzeniach z socketu Hyprlanda – w spoczynku ~0% CPU.

import fcntl
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, GtkLayerShell

SHOW_MS = 900
THUMB_W, THUMB_H = 176, 99            # logiczne px miniatury (16:9)
SHOT_AFTER_SWITCH_MS = 1200           # po zniknięciu wskaźnika, żeby nie trafił na zdjęcie
SHOT_AFTER_CHANGE_MS = 1500           # po otwarciu/zamknięciu/przeniesieniu okna
WINDOW_EVENTS = {"openwindow", "closewindow", "movewindowv2", "fullscreen", "changefloatingmode"}
# warstwy, przy których nie robimy zdjęcia (zasłaniają pulpit)
BLOCKING_LAYERS = {"command-center", "workspace-osd"}

RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
THUMB_DIR = RUNTIME / "workspace-osd"

CSS = b"""
* { font-family: "JetBrainsMono Nerd Font", monospace; border-radius: 0; box-shadow: none; }
window#ws-osd { background-color: transparent; }
#box { background-color: rgba(0, 0, 0, 0.88); border: 1px solid #444444; padding: 12px 18px 16px 18px; }
#num { color: #ffffff; font-size: 48px; font-weight: bold; }
.thumb { border: 1px solid #333333; background-color: #0b0b0b; }
.thumb.active { border: 2px solid #ffffff; }
.thumb-num { color: #777777; font-size: 12px; }
.thumb-num.active { color: #ffffff; font-weight: bold; }
.empty { color: #444444; font-size: 20px; }
"""


def hypr_json(*args):
    try:
        out = subprocess.run(["hyprctl", *args, "-j"], capture_output=True, text=True, timeout=1).stdout
        return json.loads(out)
    except Exception:
        return {} if args and args[0].startswith("active") else []


def buffer_scale():
    # GTK3 rysuje w całkowitej skali (przy 1.5 -> 2); miniatury ładujemy w tylu pikselach, żeby były ostre
    disp = Gdk.Display.get_default()
    return max((disp.get_monitor(i).get_scale_factor() for i in range(disp.get_n_monitors())), default=1)


class Osd:
    def __init__(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        self.win = None
        self.hide_id = None
        self.shot_id = None
        self.shot_running = False
        self.shot_pending = False

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box.set_name("box")
        self.num = Gtk.Label(label="1")
        self.num.set_name("num")
        self.box.pack_start(self.num, False, False, 0)
        self.row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.row.set_halign(Gtk.Align.CENTER)
        self.box.pack_start(self.row, False, False, 0)

        self.schedule_shot(2000)

    # ---------- okno ----------
    def _make_window(self):
        # Nowe okno przy każdym pokazaniu: layer surface trafia wtedy na aktualnie aktywny monitor
        win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_name("ws-osd")
        visual = win.get_screen().get_rgba_visual()
        if visual:
            win.set_visual(visual)
        win.set_app_paintable(True)
        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_namespace(win, "workspace-osd")
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
        # bez kotwic = wyśrodkowane; okno ma tylko rozmiar ramki, więc rysowanie jest tanie
        win.add(self.box)
        # kliknięcia przechodzą przez wskaźnik do okien pod spodem
        win.connect("realize", lambda w: w.get_window().input_shape_combine_region(cairo.Region(), 0, 0))
        return win

    def _thumb_widget(self, ws_id, active, scale):
        cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        frame = Gtk.Box()
        frame.get_style_context().add_class("thumb")
        frame.set_size_request(THUMB_W, THUMB_H)
        path = THUMB_DIR / f"{ws_id}.png"
        img = None
        if path.exists():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), THUMB_W * scale, THUMB_H * scale, False)
                img = Gtk.Image.new_from_surface(Gdk.cairo_surface_create_from_pixbuf(pb, scale, None))
            except Exception:
                img = None
        if img is None:
            img = Gtk.Label(label="·")
            img.get_style_context().add_class("empty")
            img.set_hexpand(True)
        frame.pack_start(img, True, True, 0)
        lbl = Gtk.Label(label=str(ws_id))
        lbl.get_style_context().add_class("thumb-num")
        if active:
            frame.get_style_context().add_class("active")
            lbl.get_style_context().add_class("active")
        cell.pack_start(frame, False, False, 0)
        cell.pack_start(lbl, False, False, 0)
        return cell

    def show(self, ws_id):
        used = {w.get("id") for w in hypr_json("workspaces") if w.get("windows", 0) > 0 and w.get("id", 0) > 0}
        self.num.set_text(str(ws_id))
        for child in self.row.get_children():
            self.row.remove(child)
        scale = buffer_scale()
        for wid in sorted(used | {ws_id}):
            self.row.pack_start(self._thumb_widget(wid, wid == ws_id, scale), False, False, 0)

        if self.win is None:
            self.win = self._make_window()
        self.win.show_all()
        if self.hide_id:
            GLib.source_remove(self.hide_id)
        self.hide_id = GLib.timeout_add(SHOW_MS, self.hide)

    def hide(self):
        self.hide_id = None
        if self.win is not None:
            self.win.remove(self.box)
            self.win.destroy()
            self.win = None
        return False

    # ---------- miniatury ----------
    def schedule_shot(self, delay_ms, replace=True):
        if self.shot_id:
            if not replace:
                return  # już zaplanowane – nie przesuwamy w nieskończoność przy serii zdarzeń
            GLib.source_remove(self.shot_id)
        self.shot_id = GLib.timeout_add(delay_ms, self._take_shot)

    def _take_shot(self):
        self.shot_id = None
        if self.shot_running:
            # pod obciążeniem (gra) zrzut z nice 19 trwa dłużej – kolejny idzie zaraz po nim
            self.shot_pending = True
            return False
        if self.win is not None:
            self.schedule_shot(800)
            return False
        ws = hypr_json("activeworkspace")
        ws_id, mon_name = ws.get("id", 0), ws.get("monitor")
        if ws_id <= 0 or not mon_name:
            return False
        if hypr_json("activewindow").get("class") == "screensaver":
            return False
        layers = hypr_json("layers")
        layers = layers.values() if isinstance(layers, dict) else []
        top = {l.get("namespace") for m in layers for lvl in m.get("levels", {}).values() for l in lvl}
        if top & BLOCKING_LAYERS:
            self.schedule_shot(1000)
            return False
        mon = next((m for m in hypr_json("monitors") if m.get("name") == mon_name), None)
        if not mon or mon.get("dpmsStatus") is False:
            return False
        # grim skaluje od pikseli fizycznych; miniatura ma THUMB_W * skala bufora px szerokości
        factor = min(1.0, THUMB_W * buffer_scale() / max(1, mon.get("width", 3840)))
        tmp = THUMB_DIR / f".{ws_id}.tmp.png"
        try:
            proc = Gio.Subprocess.new(
                ["nice", "-n", "19", "grim", "-o", mon_name, "-s", f"{factor:.4f}", "-l", "1", str(tmp)],
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error:
            return False
        self.shot_running = True
        proc.wait_check_async(None, self._shot_done, (ws_id, tmp))
        return False

    def _shot_done(self, proc, res, data):
        ws_id, tmp = data
        self.shot_running = False
        try:
            proc.wait_check_finish(res)
            # zrzut trwał – jeśli w międzyczasie zmienił się pulpit, obraz nie pasuje do ws_id
            if hypr_json("activeworkspace").get("id") == ws_id:
                tmp.replace(THUMB_DIR / f"{ws_id}.png")
            else:
                tmp.unlink(missing_ok=True)
        except Exception:
            tmp.unlink(missing_ok=True)
        if self.shot_pending:
            self.shot_pending = False
            self.schedule_shot(200)

    def forget(self, ws_id):
        (THUMB_DIR / f"{ws_id}.png").unlink(missing_ok=True)


def main():
    lock = open(RUNTIME / "workspace-osd.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(0)

    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        sys.exit("brak HYPRLAND_INSTANCE_SIGNATURE – uruchom z Hyprlanda")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(RUNTIME / "hypr" / sig / ".socket2.sock"))
    sock.setblocking(False)

    osd = Osd()
    buf = [b""]

    def on_data(_src, cond):
        if cond & (GLib.IO_HUP | GLib.IO_ERR):
            Gtk.main_quit()
            return False
        try:
            data = sock.recv(65536)
        except BlockingIOError:
            return True
        if not data:
            Gtk.main_quit()
            return False
        buf[0] += data
        *lines, buf[0] = buf[0].split(b"\n")
        target = None
        changed = False
        for line in lines:
            ev, _, arg = line.decode(errors="replace").partition(">>")
            if ev == "workspacev2":
                ws_id, _, name = arg.partition(",")
                if ws_id.lstrip("-").isdigit() and int(ws_id) > 0 and not name.startswith("special"):
                    target = int(ws_id)
            elif ev == "destroyworkspacev2":
                ws_id = arg.partition(",")[0]
                if ws_id.isdigit():
                    osd.forget(int(ws_id))
            elif ev in WINDOW_EVENTS:
                changed = True
        if target is not None:
            osd.show(target)
            osd.schedule_shot(SHOT_AFTER_SWITCH_MS)
        elif changed:
            osd.schedule_shot(SHOT_AFTER_CHANGE_MS, replace=False)
        return True

    GLib.io_add_watch(sock.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, on_data)
    Gtk.main()


if __name__ == "__main__":
    main()
