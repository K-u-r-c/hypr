#!/usr/bin/env python3
# Wskaźnik pulpitu: po przełączeniu na środku ekranu na chwilę pokazuje numer i pasek 1-10
# (zajęte pulpity jaśniejsze). Autostart w hyprland.conf, animację wejścia/wyjścia robi Hyprland (layerrule).
# Działa tylko na zdarzeniach z socketu Hyprlanda – bez odpytywania, w spoczynku ~0% CPU.

import fcntl
import json
import os
import socket
import subprocess
import sys

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import GLib, Gtk, GtkLayerShell

SHOW_MS = 800
SLOTS = 10

CSS = b"""
* { font-family: "JetBrainsMono Nerd Font", monospace; border-radius: 0; box-shadow: none; }
window#ws-osd { background-color: transparent; }
#box { background-color: rgba(0, 0, 0, 0.88); border: 1px solid #444444; padding: 14px 22px 18px 22px; }
#num { color: #ffffff; font-size: 64px; font-weight: bold; }
.slot { min-width: 10px; min-height: 4px; background-color: #2a2a2a; }
.slot.used { background-color: #777777; }
.slot.active { background-color: #ffffff; }
"""


def hypr_json(*args):
    try:
        return json.loads(subprocess.run(["hyprctl", *args, "-j"], capture_output=True, text=True, timeout=1).stdout)
    except Exception:
        return []


class Osd:
    def __init__(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self._screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.hide_id = None
        self.win = None

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box.set_name("box")
        self.num = Gtk.Label(label="1")
        self.num.set_name("num")
        self.box.pack_start(self.num, False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        row.set_halign(Gtk.Align.CENTER)
        self.slots = []
        for _ in range(SLOTS):
            s = Gtk.Box()
            s.get_style_context().add_class("slot")
            row.pack_start(s, False, False, 0)
            self.slots.append(s)
        self.box.pack_start(row, False, False, 0)

    @staticmethod
    def _screen():
        from gi.repository import Gdk

        return Gdk.Screen.get_default()

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

    def show(self, ws_id):
        used = {w.get("id") for w in hypr_json("workspaces") if w.get("windows", 0) > 0}
        self.num.set_text(str(ws_id))
        for i, s in enumerate(self.slots, start=1):
            ctx = s.get_style_context()
            for c in ("used", "active"):
                ctx.remove_class(c)
            if i == ws_id:
                ctx.add_class("active")
            elif i in used:
                ctx.add_class("used")

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


def main():
    lock = open(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "workspace-osd.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(0)

    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        sys.exit("brak HYPRLAND_INSTANCE_SIGNATURE – uruchom z Hyprlanda")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "hypr", sig, ".socket2.sock"))
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
        for line in lines:
            ev, _, arg = line.decode(errors="replace").partition(">>")
            if ev == "workspacev2":
                ws_id, _, name = arg.partition(",")
                if ws_id.lstrip("-").isdigit() and int(ws_id) > 0 and not name.startswith("special"):
                    target = int(ws_id)
        if target is not None:
            osd.show(target)
        return True

    GLib.io_add_watch(sock.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, on_data)
    Gtk.main()


if __name__ == "__main__":
    main()
