#!/usr/bin/env python3
import json
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

PID_FILE = Path("/tmp/hypr_command_center.pid")


def find_running_pid():
    # Only trust the PID file if it really points at a live command center
    try:
        pid = int(PID_FILE.read_text().strip())
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except Exception:
        return None
    if pid == os.getpid() or b"command_center" not in cmdline:
        return None
    return pid


if __name__ == "__main__" and "--daemon" not in sys.argv:
    _pid = find_running_pid()
    if _pid:
        try:
            os.kill(_pid, signal.SIGUSR1)
            sys.exit(0)
        except ProcessLookupError:
            pass

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, GtkLayerShell, Pango

HOME = Path.home()
LAYOUT_FILE = HOME / ".config/hypr/command_center_layout.json"
# Bump when tile order/defaults change so stale saved positions are dropped
LAYOUT_VERSION = 4
# Preferred (width, max height) per tile; rows are flowed to fit whichever screen opens it
TILE_PREFS = {
    "audio": (430, 650),
    "brightness": (420, 330),
    "bluetooth": (510, 650),
    "screenshots": (470, 650),
    "wallpaper": (480, 650),
    "system": (420, 400),
}
WALL_SCRIPT = HOME / ".config/hypr/wallpaper.sh"
WALL_DIR = HOME / "Pictures/wallpapers"
THUMB_DIR = HOME / ".cache/wallpaper-thumbs"
SHOT_THUMB_DIR = HOME / ".cache/screenshot-thumbs"
PICTURES_DIR = HOME / "Pictures"
UPDATES_CACHE = HOME / ".cache/command-center-updates.json"
UPDATES_CACHE_TTL = 1800
APP_USAGE_FILE = HOME / ".cache/command-center-apps.json"
DDC_CACHE = HOME / ".cache/command-center-ddc.json"
LAUNCHER_MAX_RESULTS = 30
SEARCH_W = 760
TERMINAL = "alacritty"

THUMB_DIR.mkdir(parents=True, exist_ok=True)
SHOT_THUMB_DIR.mkdir(parents=True, exist_ok=True)

CSS = b"""
* {
    font-family: "JetBrainsMono Nerd Font", monospace;
    border-radius: 0;
    box-shadow: none;
    outline: none;
    text-shadow: none;
    -gtk-icon-shadow: none;
}

button {
    background-image: none;
}

selection,
entry selection,
label selection {
    background-color: #3a3a3a;
    color: #ffffff;
}

window#overlay-win,
#backdrop {
    background-color: rgba(0, 0, 0, 0.65);
}

.hud-box {
    background-color: rgba(0, 0, 0, 0.96);
    border: 1px solid #444444;
    padding: 6px 14px;
}

.hud-title {
    color: #ffffff;
    font-weight: bold;
    font-size: 14px;
}

.hud-status {
    color: #ffffff;
    background-color: #161616;
    border: 1px solid #444444;
    padding: 3px 10px;
    font-size: 12px;
}

.info-popup {
    background-color: rgba(0, 0, 0, 0.98);
    border: 1px solid #ffffff;
    padding: 12px 16px;
}

.info-title {
    color: #ffffff;
    font-weight: bold;
    font-size: 13px;
}

.info-text {
    color: #bbbbbb;
    font-size: 12px;
}

.tile-card {
    background-color: rgba(0, 0, 0, 0.95);
    border: 1px solid #333333;
}

.tile-card-focused {
    background-color: rgba(0, 0, 0, 0.98);
    border: 1px solid #ffffff;
}

.tile-header {
    background-color: #0d0d0d;
    border-bottom: 1px solid #333333;
    padding: 9px 12px;
}

.tile-header-focused {
    background-color: #1a1a1a;
    border-bottom: 1px solid #ffffff;
    padding: 9px 12px;
}

.tile-title {
    color: #d8d8d8;
    font-weight: bold;
    font-size: 14px;
}

.tile-title-focused {
    color: #ffffff;
    font-weight: bold;
    font-size: 14px;
}

.tile-sub {
    color: #666666;
    font-size: 11px;
}

.tile-footer {
    background-color: transparent;
    border-top: none;
    padding: 0px 6px 3px 6px;
}

.tile-btn {
    background-image: none;
    background-color: transparent;
    color: #888888;
    border: 1px solid #333333;
    padding: 0px 6px;
    font-size: 11px;
    min-height: 0;
    min-width: 0;
}

.tile-btn label {
    color: #888888;
}

.tile-btn:hover {
    background-image: none;
    background-color: #222222;
    color: #ffffff;
    border: 1px solid #888888;
}

.tile-btn:hover label {
    color: #ffffff;
}

.resize-grip {
    color: #777777;
    font-size: 12px;
}

.resize-grip:hover {
    color: #ffffff;
}

.item-row {
    background-color: transparent;
    border-left: 2px solid transparent;
    padding: 6px 10px;
    margin: 2px 0;
}

.item-row-selected {
    background-color: rgba(255, 255, 255, 0.12);
    border-left: 2px solid #ffffff;
    padding: 6px 10px;
    margin: 2px 0;
}

.item-row-selected .row-title {
    color: #ffffff;
}

.row-title {
    color: #e0e0e0;
    font-size: 13px;
    font-weight: bold;
}

.row-sub {
    color: #777777;
    font-size: 11px;
}

.mono-btn {
    background-image: none;
    background-color: #0f0f0f;
    color: #cccccc;
    border: 1px solid #3a3a3a;
    padding: 4px 10px;
    font-size: 12px;
}

.mono-btn label {
    color: #cccccc;
}

.mono-btn:hover {
    background-image: none;
    background-color: #222222;
    color: #ffffff;
    border: 1px solid #888888;
}

.mono-btn:hover label {
    color: #ffffff;
}

.mono-btn-active {
    background-image: none;
    background-color: #242424;
    color: #ffffff;
    border: 1px solid #ffffff;
    font-weight: bold;
    padding: 4px 10px;
    font-size: 12px;
}

.mono-btn-active label {
    color: #ffffff;
    font-weight: bold;
}

entry {
    background-color: #0f0f0f;
    color: #ffffff;
    caret-color: #ffffff;
    border: 1px solid #3a3a3a;
    padding: 6px 10px;
    font-size: 13px;
}

entry:focus {
    border: 1px solid #ffffff;
}

entry image {
    color: #777777;
}

.spotlight-box {
    background-color: rgba(0, 0, 0, 0.97);
    border: 1px solid #444444;
    padding: 8px 14px;
}

.spotlight-box-active {
    background-color: rgba(0, 0, 0, 0.97);
    border: 1px solid #ffffff;
    padding: 8px 14px;
}

entry.spotlight-entry,
entry.spotlight-entry:focus {
    background-color: transparent;
    border: none;
    font-size: 18px;
    padding: 6px 4px;
}

.spotlight-results {
    background-color: rgba(0, 0, 0, 0.97);
    border: 1px solid #444444;
    padding: 6px;
}

.preview-box {
    border: 1px solid #333333;
    background-color: #050505;
}

scale trough {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    min-height: 8px;
}

scale highlight {
    background-color: #d8d8d8;
    min-height: 8px;
}

scale slider {
    background-color: #ffffff;
    border: 1px solid #000000;
    min-width: 12px;
    min-height: 12px;
    margin: -3px 0;
}

progressbar trough {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    min-height: 6px;
}

progressbar progress {
    background-color: #d8d8d8;
    border: none;
    min-height: 6px;
}

scrollbar,
scrolledwindow {
    background-color: transparent;
    border: none;
}

scrollbar slider {
    background-color: #333333;
    min-width: 6px;
}
"""


def run_cmd(args, timeout=2.5):
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip()
    except Exception:
        return ""


def detect_monitors():
    # [(name, w, h)], główny monitor (primary-monitor.sh) pierwszy – nic na sztywno
    try:
        mons = json.loads(run_cmd(["hyprctl", "monitors", "-j"]))
    except Exception:
        return []
    primary = run_cmd([str(HOME / ".config/hypr/primary-monitor.sh")])
    mons.sort(key=lambda m: m.get("name") != primary)
    return [(m["name"], int(m.get("width", 0)), int(m.get("height", 0))) for m in mons]


def aspect_label(w, h):
    return "21:9" if h and w / h >= 2 else "16:9"


def count_pending_updates(args, timeout=60):
    # Counts "pkg old -> new" lines; None when the check itself failed
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    if args[0] == "checkupdates" and res.returncode == 1:
        return None
    return sum(1 for ln in res.stdout.splitlines() if re.match(r"^\S+ \S+ -> \S+", ln))


def find_cpu_temp_path():
    for name_file in Path("/sys/class/hwmon").glob("hwmon*/name"):
        try:
            if name_file.read_text().strip() != "coretemp":
                continue
        except Exception:
            continue
        hw = name_file.parent
        for label in sorted(hw.glob("temp*_label")):
            try:
                if label.read_text().strip().startswith("Package"):
                    return hw / label.name.replace("_label", "_input")
            except Exception:
                pass
        if (hw / "temp1_input").exists():
            return hw / "temp1_input"
    return None


def read_cpu_times():
    with open("/proc/stat") as f:
        vals = [int(v) for v in f.readline().split()[1:9]]
    return vals[3] + vals[4], sum(vals)


def scroll_row_into_view(scrolled: Gtk.ScrolledWindow, list_box: Gtk.Box, idx: int):
    def _do():
        children = list_box.get_children()
        if 0 <= idx < len(children):
            row = children[idx]
            alloc = row.get_allocation()
            vadj = scrolled.get_vadjustment()
            if vadj and alloc.height > 0:
                top = alloc.y
                bot = alloc.y + alloc.height
                cur = vadj.get_value()
                page = vadj.get_page_size()
                if top < cur:
                    vadj.set_value(max(0, top - 8))
                elif bot > cur + page:
                    vadj.set_value(min(vadj.get_upper() - page, bot - page + 8))
        return False

    GLib.idle_add(_do)


class DraggableTile(Gtk.EventBox):
    MIN_W = 320
    MIN_H = 260

    def __init__(self, app, tile_id, title, width, height, default_x, default_y):
        super().__init__()
        self.app = app
        self.tile_id = tile_id
        self.tile_width = width
        self.tile_height = height
        self.default_w = width
        self.default_h = height
        self.x = default_x
        self.y = default_y
        self.minimized = False

        self.set_size_request(width, height)
        self.set_visible_window(True)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.get_style_context().add_class("tile-card")

        self.outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.outer.get_style_context().add_class("tile-card")
        self.add(self.outer)

        # Top Draggable Header Bar
        self.header_ev = Gtk.EventBox()
        self.header_ev.set_visible_window(True)
        self.header_ev.set_above_child(False)
        self.header_ev.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.header_ev.connect("button-press-event", self.on_drag_start)
        self.header_ev.connect("button-release-event", self.on_drag_end)
        self.header_ev.connect("motion-notify-event", self.on_drag_motion)
        self.header_ev.connect("enter-notify-event", self.on_header_enter)
        self.header_ev.connect("leave-notify-event", self.on_header_leave)

        self.header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.header_box.get_style_context().add_class("tile-header")
        self.header_ev.add(self.header_box)

        self.title_lbl = Gtk.Label(label=f"[::] {title}")
        self.title_lbl.get_style_context().add_class("tile-title")
        self.title_lbl.set_xalign(0)
        self.header_box.pack_start(self.title_lbl, True, True, 0)

        self.hint_lbl = Gtk.Label(label="⠿")
        self.hint_lbl.get_style_context().add_class("tile-sub")
        self.header_box.pack_end(self.hint_lbl, False, False, 0)

        self.min_btn = Gtk.Button(label="[_]")
        self.min_btn.get_style_context().add_class("tile-btn")
        self.min_btn.set_tooltip_text("Minimize / restore (Ctrl+M)")
        self.min_btn.connect("clicked", lambda *_: self.toggle_minimized())
        self.header_box.pack_end(self.min_btn, False, False, 0)

        self.outer.pack_start(self.header_ev, False, False, 0)

        # Main Body
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.body.set_margin_top(10)
        self.body.set_margin_bottom(2)
        self.body.set_margin_start(12)
        self.body.set_margin_end(12)
        self.outer.pack_start(self.body, True, True, 0)

        # Bottom-right Resize Grip
        self.footer_ev = Gtk.EventBox()
        self.footer_ev.set_visible_window(True)
        self.footer_ev.set_above_child(True)
        self.footer_ev.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.footer_ev.connect("button-press-event", self.on_resize_start)
        self.footer_ev.connect("button-release-event", self.on_resize_end)
        self.footer_ev.connect("motion-notify-event", self.on_resize_motion)
        self.footer_ev.connect("enter-notify-event", self.on_resize_enter)
        self.footer_ev.connect("leave-notify-event", self.on_resize_leave)

        footer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        footer_box.get_style_context().add_class("tile-footer")
        self.footer_ev.add(footer_box)

        grip_lbl = Gtk.Label(label="◢")
        grip_lbl.get_style_context().add_class("resize-grip")
        footer_box.pack_end(grip_lbl, False, False, 0)

        self.outer.pack_end(self.footer_ev, False, False, 0)

        # Also allow dragging or edge-resizing from the tile frame itself
        self.connect("button-press-event", self.on_frame_press)
        self.connect("button-release-event", self.on_drag_end)
        self.connect("motion-notify-event", self.on_frame_motion)

    def set_cursor_on(self, widget, name: str):
        win = widget.get_window()
        if win:
            disp = win.get_display()
            cur = Gdk.Cursor.new_from_name(disp, name)
            win.set_cursor(cur)

    def update_size_request(self, new_w: int, new_h: int):
        self.tile_width = max(self.MIN_W, min(self.app.screen_w - self.x - 10, int(new_w)))
        self.tile_height = max(self.MIN_H, min(self.app.screen_h - self.y - 10, int(new_h)))
        if not self.minimized:
            self.set_size_request(self.tile_width, self.tile_height)

    def apply_minimized(self):
        # Minimized = header only, at its natural size; tile_width/height keep the restore size
        if self.minimized:
            self.body.hide()
            self.footer_ev.hide()
            self.min_btn.set_label("[+]")
            self.set_size_request(-1, -1)
            return
        self.body.show()
        self.footer_ev.show()
        self.min_btn.set_label("[_]")
        # Pull back on screen if it was dragged near an edge while minimized
        nx = max(10, min(self.app.screen_w - self.tile_width - 10, self.x))
        ny = max(64, min(self.app.screen_h - self.tile_height - 10, self.y))
        if (nx, ny) != (self.x, self.y):
            self.x, self.y = nx, ny
            self.app.fixed.move(self, nx, ny)
        self.update_size_request(self.tile_width, self.tile_height)

    def toggle_minimized(self):
        self.app.focus_tile(self.tile_id)
        self.minimized = not self.minimized
        self.apply_minimized()
        self.app.save_layout()

    def on_header_enter(self, *_):
        if self.app.dragging_tile is None and self.app.resizing_tile is None:
            self.set_cursor_on(self.header_ev, "grab")
        return False

    def on_header_leave(self, *_):
        if self.app.dragging_tile is None:
            self.set_cursor_on(self.header_ev, "default")
        return False

    def on_resize_enter(self, *_):
        if self.app.resizing_tile is None:
            self.set_cursor_on(self.footer_ev, "nwse-resize")
        return False

    def on_resize_leave(self, *_):
        if self.app.resizing_tile is None:
            self.set_cursor_on(self.footer_ev, "default")
        return False

    def set_focused_style(self, focused: bool):
        for w in (self, self.outer):
            ctx = w.get_style_context()
            if focused:
                ctx.remove_class("tile-card")
                ctx.add_class("tile-card-focused")
            else:
                ctx.remove_class("tile-card-focused")
                ctx.add_class("tile-card")
        hctx = self.header_box.get_style_context()
        tctx = self.title_lbl.get_style_context()
        if focused:
            hctx.remove_class("tile-header")
            hctx.add_class("tile-header-focused")
            tctx.remove_class("tile-title")
            tctx.add_class("tile-title-focused")
        else:
            hctx.remove_class("tile-header-focused")
            hctx.add_class("tile-header")
            tctx.remove_class("tile-title-focused")
            tctx.add_class("tile-title")

    def on_drag_start(self, widget, event):
        self.app.focus_tile(self.tile_id)
        if event.button == 1:
            coords = widget.translate_coordinates(self, int(event.x), int(event.y))
            if coords:
                self.app.start_tile_drag(self, coords[0], coords[1])
                self.set_cursor_on(self.header_ev, "grabbing")
        return True

    def on_drag_motion(self, widget, event):
        if self.app.dragging_tile is self:
            coords = widget.translate_coordinates(self.app.fixed, int(event.x), int(event.y))
            if coords:
                self.app.move_tile_drag(coords[0], coords[1])
        return True

    def on_drag_end(self, _widget, event):
        if event.button == 1:
            if self.app.dragging_tile is self:
                self.app.end_tile_drag()
                self.set_cursor_on(self.header_ev, "grab")
            if self.app.resizing_tile is self:
                self.app.end_tile_resize()
                self.set_cursor_on(self.footer_ev, "nwse-resize")
        return True

    def on_resize_start(self, widget, event):
        self.app.focus_tile(self.tile_id)
        if event.button == 1:
            coords = widget.translate_coordinates(self.app.fixed, int(event.x), int(event.y))
            if coords:
                self.app.start_tile_resize(self, coords[0], coords[1])
                self.set_cursor_on(self.footer_ev, "nwse-resize")
        return True

    def on_resize_motion(self, widget, event):
        if self.app.resizing_tile is self:
            coords = widget.translate_coordinates(self.app.fixed, int(event.x), int(event.y))
            if coords:
                self.app.move_tile_resize(coords[0], coords[1])
        return True

    def on_resize_end(self, _widget, event):
        if event.button == 1 and self.app.resizing_tile is self:
            self.app.end_tile_resize()
        return True

    def on_frame_press(self, widget, event):
        self.app.focus_tile(self.tile_id)
        if event.button == 1:
            local = widget.translate_coordinates(self, int(event.x), int(event.y))
            canvas = widget.translate_coordinates(self.app.fixed, int(event.x), int(event.y))
            if local and canvas:
                lx, ly = local
                # If near right or bottom border (16px), start resize; otherwise start drag
                if not self.minimized and (lx >= self.tile_width - 18 or ly >= self.tile_height - 24):
                    self.app.start_tile_resize(self, canvas[0], canvas[1])
                else:
                    self.app.start_tile_drag(self, lx, ly)
        return True

    def on_frame_motion(self, widget, event):
        if self.app.dragging_tile is self or self.app.resizing_tile is self:
            coords = widget.translate_coordinates(self.app.fixed, int(event.x), int(event.y))
            if coords:
                if self.app.dragging_tile is self:
                    self.app.move_tile_drag(coords[0], coords[1])
                else:
                    self.app.move_tile_resize(coords[0], coords[1])
        return True


class CommandCenterApp:
    def __init__(self, start_hidden=False, daemon=False):
        self.daemon = daemon
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.win = None
        self.screen_w, self.screen_h = self.detect_focused_monitor_size()

        self.dragging_tile = None
        self.drag_offset = (0, 0)
        self.resizing_tile = None
        self.resize_start_mouse = (0, 0)
        self.resize_start_size = (0, 0)
        self.is_visible = False

        self.bg_ev = Gtk.EventBox()
        self.bg_ev.set_name("backdrop")
        self.bg_ev.set_visible_window(True)
        self.bg_ev.set_above_child(False)
        self.bg_ev.set_size_request(self.screen_w, self.screen_h)
        self.bg_ev.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.bg_ev.connect("button-press-event", self.on_backdrop_click)
        self.bg_ev.connect("motion-notify-event", self.on_global_motion)
        self.bg_ev.connect("button-release-event", self.on_global_release)

        self.fixed = Gtk.Fixed()
        self.fixed.connect("draw", self.on_fixed_draw)
        self.bg_ev.add(self.fixed)

        self.focused_tile_idx = 0
        self.tile_order = ["audio", "brightness", "bluetooth", "screenshots", "wallpaper", "system"]
        self.z_order = list(self.tile_order)
        self.tiles = {}
        self.left_ev = None
        self.right_ev = None
        self.info_popup = None

        self.audio_items = []
        self.audio_sel = 0
        self.audio_sinks = []
        self.audio_default_sink = ""

        self.screenshots = []
        self.shot_sel = 0
        self.shots_sig = None

        self.monitors = detect_monitors()
        self.wall_monitors = [m[0] for m in self.monitors] + (["ALL"] if len(self.monitors) > 1 else []) or ["ALL"]
        self.wall_mon_idx = 0
        self.wallpapers = []
        self.wall_sel = 0
        self.wall_sig = None
        self.wall_pixbufs = {}
        self.thumb_queue = queue.Queue()
        self.thumb_pending = set()
        self.thumb_failed = set()
        threading.Thread(target=self.thumb_worker, daemon=True).start()

        self.bt_powered = True
        self.bt_scanning = False
        self.bt_devices = []
        self.bt_sel = 0

        self.launch_apps = []
        self.launch_results = []
        self.launch_rows = []
        self.launch_sel = 0
        self.icon_cache = {}
        self.search_active = True
        try:
            self.app_usage = json.loads(APP_USAGE_FILE.read_text())
        except Exception:
            self.app_usage = {}

        self.bright_state = "detecting"
        self.bright_displays = []
        self.bright_items = []
        self.bright_widgets = []
        self.bright_sel = 0
        self.bright_targets = {}
        self.bright_inflight = set()
        self.bright_flush_id = None
        self.bright_reading = False

        self.sys_busy = False
        self.sys_rows = {}
        self.cpu_temp_path = find_cpu_temp_path()
        try:
            self.sys_cpu_prev = read_cpu_times()
        except Exception:
            self.sys_cpu_prev = (0, 0)
        self.upd_checking = False
        self.upd_counts = None

        self.build_tiles()
        self.build_hud()
        self.build_search()
        self.load_layout()
        self.update_focus_visuals()

        # DEFAULT priority, not HIGH: a HIGH source makes GLib skip the GDK Wayland
        # source's check(), leaving a pending wl_display read that deadlocks gdk_flush on quit
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.toggle_visibility)
        GLib.idle_add(self.refresh_all_data)
        GLib.timeout_add(2000, self.periodic_tick)

    def create_layer_window(self):
        win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_name("overlay-win")
        win.set_title("Command Center")

        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            win.set_visual(visual)

        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_namespace(win, "command-center")
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_exclusive_zone(win, -1)
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        for edge in (
            GtkLayerShell.Edge.TOP,
            GtkLayerShell.Edge.BOTTOM,
            GtkLayerShell.Edge.LEFT,
            GtkLayerShell.Edge.RIGHT,
        ):
            GtkLayerShell.set_anchor(win, edge, True)

        win.connect("key-press-event", self.on_key_press)
        win.connect("delete-event", lambda *_: self.hide_overlay() or True)
        return win

    def refresh_steps(self):
        return [
            self.refresh_launcher,
            self.refresh_audio,
            self.refresh_brightness,
            self.refresh_bluetooth,
            self.refresh_screenshots,
            self.refresh_wallpapers,
            self.refresh_system,
            self.check_updates,
        ]

    def refresh_all_data(self):
        # One refresh per idle iteration, so key presses and redraws interleave with the work
        steps = self.refresh_steps()

        def _run_next():
            steps.pop(0)()
            return bool(steps)

        GLib.idle_add(_run_next)
        return False

    def refresh_all_now(self):
        # Cold start straight into a visible window: fill every tile before the first frame
        for step in self.refresh_steps():
            step()

    def sync_monitor_size(self):
        w, h = self.detect_focused_monitor_size()
        if (w, h) == (self.screen_w, self.screen_h):
            return
        self.screen_w, self.screen_h = w, h
        self.bg_ev.set_size_request(w, h)
        self.fixed.move(self.right_ev, w - 230, 16)
        self.fixed.move(self.info_popup, w - 460, 66)
        self.place_search()
        self.load_layout()

    def show_overlay(self):
        self.is_visible = True
        self.sync_monitor_size()
        # Everything the first frame shows is settled before the window maps – changes made
        # after show() land in later frames and flicker during the fade-in
        self.set_status("")
        self.search_active = True
        self.launch_entry.set_text("")
        self.refresh_launcher_results()
        if self.win is None:
            self.win = self.create_layer_window()
            self.win.add(self.bg_ev)
            self.bg_ev.show_all()
            for tile in self.tiles.values():
                tile.apply_minimized()
        else:
            # File-based tiles are cheap and rebuild only when something changed
            self.refresh_screenshots()
            self.refresh_wallpapers()
        self.info_popup.hide()
        self.results_ev.hide()
        self.update_focus_visuals()
        if self.win.get_visible():
            return
        # Re-show in daemon mode: show() keeps hidden widgets (minimized bodies) hidden
        self.win.show()
        self.launch_entry.grab_focus_without_selecting()
        # Subprocess-based tiles (audio, bluetooth, …) catch up after the window is up
        GLib.idle_add(self.refresh_all_data)

    def hide_overlay(self):
        self.is_visible = False
        self.dragging_tile = None
        self.resizing_tile = None
        if self.daemon:
            if self.win is not None:
                self.win.hide()
            return
        PID_FILE.unlink(missing_ok=True)
        Gtk.main_quit()

    def toggle_visibility(self):
        # Act from an idle callback so the Wayland event source finishes its iteration first
        GLib.idle_add(self._toggle_now)
        # Keep the signal source: removing it would restore SIGUSR1's default action (terminate)
        return GLib.SOURCE_CONTINUE

    def _toggle_now(self):
        if self.is_visible:
            self.hide_overlay()
        else:
            self.show_overlay()
        return False

    def start_tile_drag(self, tile: DraggableTile, off_x: int, off_y: int):
        self.resizing_tile = None
        self.dragging_tile = tile
        self.drag_offset = (off_x, off_y)

    def move_tile_drag(self, canvas_x: int, canvas_y: int):
        tile = self.dragging_tile
        if not tile:
            return
        if tile.minimized:
            tw, th = tile.get_allocated_width(), tile.get_allocated_height()
        else:
            tw, th = tile.tile_width, tile.tile_height
        nx = max(10, min(self.screen_w - tw - 10, canvas_x - self.drag_offset[0]))
        ny = max(64, min(self.screen_h - th - 10, canvas_y - self.drag_offset[1]))
        tile.x = nx
        tile.y = ny
        self.fixed.move(tile, tile.x, tile.y)

    def end_tile_drag(self):
        if self.dragging_tile:
            self.dragging_tile = None
            self.save_layout()

    def start_tile_resize(self, tile: DraggableTile, canvas_x: int, canvas_y: int):
        self.dragging_tile = None
        self.resizing_tile = tile
        self.resize_start_mouse = (canvas_x, canvas_y)
        self.resize_start_size = (tile.tile_width, tile.tile_height)

    def move_tile_resize(self, canvas_x: int, canvas_y: int):
        tile = self.resizing_tile
        if not tile:
            return
        dx = canvas_x - self.resize_start_mouse[0]
        dy = canvas_y - self.resize_start_mouse[1]
        new_w = self.resize_start_size[0] + dx
        new_h = self.resize_start_size[1] + dy
        tile.update_size_request(new_w, new_h)

    def end_tile_resize(self):
        if self.resizing_tile:
            tid = self.resizing_tile.tile_id
            self.resizing_tile = None
            self.save_layout()
            if tid == "screenshots":
                self.rebuild_screenshot_ui()

    def on_global_motion(self, widget, event):
        if self.dragging_tile or self.resizing_tile:
            coords = widget.translate_coordinates(self.fixed, int(event.x), int(event.y))
            if coords:
                if self.dragging_tile:
                    self.move_tile_drag(coords[0], coords[1])
                elif self.resizing_tile:
                    self.move_tile_resize(coords[0], coords[1])
            return True
        return False

    def on_global_release(self, _widget, event):
        if event.button == 1:
            if self.dragging_tile:
                self.end_tile_drag()
                return True
            if self.resizing_tile:
                self.end_tile_resize()
                return True
        return False

    def detect_focused_monitor_size(self):
        out = run_cmd(["hyprctl", "monitors", "-j"])
        try:
            mons = json.loads(out)
            for m in mons:
                if m.get("focused"):
                    return int(m.get("width", 1920)), int(m.get("height", 1080))
        except Exception:
            pass
        return 1920, 1080

    def compute_layout(self):
        # Flow tiles into centered rows that fit the current screen.
        # Returns (search bar y, {tile_id: (x, y, w, h)}).
        gap = 24
        bar_block = 62 + gap
        rows, row, row_w = [], [], 0
        for tid in self.tile_order:
            w = TILE_PREFS[tid][0]
            if row and row_w + gap + w > self.screen_w - 48:
                rows.append(row)
                row, row_w = [], 0
            row_w += (gap if row else 0) + w
            row.append(tid)
        if row:
            rows.append(row)

        avail = self.screen_h - 72 - bar_block - 20 - gap * (len(rows) - 1)
        row_h = max(DraggableTile.MIN_H, min(650, avail // len(rows)))
        block_h = bar_block + len(rows) * row_h + gap * (len(rows) - 1)
        top = max(72, (self.screen_h - block_h) // 2)

        pos = {}
        y = top + bar_block
        for r in rows:
            total = sum(TILE_PREFS[t][0] for t in r) + gap * (len(r) - 1)
            x = max(24, (self.screen_w - total) // 2)
            for t in r:
                w, max_h = TILE_PREFS[t]
                pos[t] = (x, y, w, min(max_h, row_h))
                x += w + gap
            y += row_h + gap
        return top, pos

    def default_positions(self):
        return self.compute_layout()[1]

    def search_bar_pos(self):
        w = min(SEARCH_W, self.screen_w - 48)
        return (self.screen_w - w) // 2, self.compute_layout()[0], w

    def layout_key(self):
        return f"{self.screen_w}x{self.screen_h}"

    def read_layout_file(self):
        try:
            data = json.loads(LAYOUT_FILE.read_text())
        except Exception:
            return {}
        return data if data.get("_version") == LAYOUT_VERSION else {}

    def write_layout_file(self, data):
        data["_version"] = LAYOUT_VERSION
        try:
            LAYOUT_FILE.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def load_layout(self):
        defaults = self.default_positions()
        # Each screen size keeps its own layout, so a layout made on one monitor never spills off another
        saved = self.read_layout_file().get(self.layout_key(), {})
        for tid, tile in self.tiles.items():
            d_x, d_y, d_w, d_h = defaults[tid]
            entry = saved.get(tid, [d_x, d_y, d_w, d_h])
            x = int(entry[0]) if len(entry) >= 1 else d_x
            y = int(entry[1]) if len(entry) >= 2 else d_y
            w = int(entry[2]) if len(entry) >= 3 else d_w
            h = int(entry[3]) if len(entry) >= 4 else d_h
            tile.x = max(10, min(self.screen_w - DraggableTile.MIN_W - 10, x))
            tile.y = max(64, min(self.screen_h - DraggableTile.MIN_H - 10, y))
            self.fixed.move(tile, tile.x, tile.y)
            tile.update_size_request(w, h)
            tile.minimized = bool(entry[4]) if len(entry) >= 5 else False
            tile.apply_minimized()

    def save_layout(self):
        data = self.read_layout_file()
        data[self.layout_key()] = {
            tid: [tile.x, tile.y, tile.tile_width, tile.tile_height, int(tile.minimized)]
            for tid, tile in self.tiles.items()
        }
        self.write_layout_file(data)

    def reset_layout(self):
        data = self.read_layout_file()
        data.pop(self.layout_key(), None)
        self.write_layout_file(data)
        self.load_layout()
        self.rebuild_screenshot_ui()
        self.set_status("LAYOUT & SIZES RESET")

    def build_hud(self):
        left_ev = Gtk.EventBox()
        self.left_ev = left_ev
        left_ev.set_visible_window(True)
        left_ev.connect("button-press-event", lambda *_: True)
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        left_box.get_style_context().add_class("hud-box")
        left_ev.add(left_box)

        title = Gtk.Label(label="[ COMMAND CENTER ]")
        title.get_style_context().add_class("hud-title")
        left_box.pack_start(title, False, False, 0)

        self.status_lbl = Gtk.Label(label="")
        self.status_lbl.get_style_context().add_class("hud-status")
        self.status_lbl.set_no_show_all(True)
        left_box.pack_start(self.status_lbl, False, False, 0)

        self.fixed.put(left_ev, 24, 16)

        right_ev = Gtk.EventBox()
        self.right_ev = right_ev
        right_ev.set_visible_window(True)
        right_ev.connect("button-press-event", lambda *_: True)
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        right_box.get_style_context().add_class("hud-box")
        right_ev.add(right_box)

        info_ev = Gtk.EventBox()
        info_ev.set_visible_window(True)
        info_ev.set_above_child(True)
        info_ev.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        info_lbl = Gtk.Label(label="[ i ]")
        info_lbl.get_style_context().add_class("mono-btn")
        info_ev.add(info_lbl)
        info_ev.connect("enter-notify-event", self.on_info_hover_enter)
        info_ev.connect("leave-notify-event", self.on_info_hover_leave)
        right_box.pack_start(info_ev, False, False, 0)

        reset_btn = Gtk.Button(label="[RESET]")
        reset_btn.get_style_context().add_class("mono-btn")
        reset_btn.connect("clicked", lambda *_: self.reset_layout())
        right_box.pack_start(reset_btn, False, False, 0)

        close_btn = Gtk.Button(label="[X]")
        close_btn.get_style_context().add_class("mono-btn")
        close_btn.connect("clicked", lambda *_: self.hide_overlay())
        right_box.pack_start(close_btn, False, False, 0)

        self.fixed.put(right_ev, self.screen_w - 230, 16)

        self.info_popup = Gtk.EventBox()
        self.info_popup.set_visible_window(True)
        pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pbox.get_style_context().add_class("info-popup")
        self.info_popup.add(pbox)

        ptitle = Gtk.Label(label="[ KEYBOARD & MOUSE SHORTCUTS ]")
        ptitle.get_style_context().add_class("info-title")
        ptitle.set_xalign(0)
        pbox.pack_start(ptitle, False, False, 0)

        lines = [
            "• Drag Top Header    : Move tile freely",
            "• Drag Bottom [RESIZE]: Resize tile width & height",
            "• Ctrl + Arrows/HJKL : Resize active tile via keyboard",
            "• Type / '/'         : Search apps, ENTER launches",
            "• TAB / Shift+TAB    : Search bar <-> tiles",
            "• 1-6 / Alt+1-6      : Jump to tile",
            "• ↑/↓ or J/K         : Select item in tile",
            "• ←/→ or H/L         : Volume / Brightness -/+5%, Monitor",
            "• ENTER              : Apply / Copy / Connect",
            "• M (Audio)          : Toggle audio mute",
            "• O / Shift+O (Audio): Next / previous output device",
            "• D (Brightness)     : Re-detect displays",
            "• P / S (Bluetooth)  : BT Power ON/OFF / Scan",
            "• O / DEL (Screenshot): Open / Delete screenshot",
            "• ENTER / U (System) : Open btop / Run system update",
            "• [_] / Ctrl + M     : Minimize / restore tile",
            "• R                  : Reset tile positions & sizes",
            "• ESC / Click empty  : Clear search / Close",
        ]
        for ln in lines:
            l = Gtk.Label(label=ln)
            l.get_style_context().add_class("info-text")
            l.set_xalign(0)
            pbox.pack_start(l, False, False, 0)

        self.fixed.put(self.info_popup, self.screen_w - 460, 66)

    def build_search(self):
        x, y, w = self.search_bar_pos()

        self.search_ev = Gtk.EventBox()
        self.search_ev.set_visible_window(True)
        self.search_ev.connect("button-press-event", lambda *_: self.activate_search() or True)
        self.search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.search_box.get_style_context().add_class("spotlight-box-active")
        self.search_box.set_size_request(w, -1)
        self.search_ev.add(self.search_box)

        self.launch_entry = Gtk.SearchEntry()
        self.launch_entry.get_style_context().add_class("spotlight-entry")
        self.launch_entry.set_placeholder_text("Search applications...")
        self.launch_entry.connect("changed", lambda *_: self.refresh_launcher_results())
        self.launch_entry.connect("focus-in-event", lambda *_: self.activate_search() or False)
        self.search_box.pack_start(self.launch_entry, True, True, 0)

        hint = Gtk.Label(label="[TAB] TILES")
        hint.get_style_context().add_class("row-sub")
        self.search_box.pack_end(hint, False, False, 0)
        self.fixed.put(self.search_ev, x, y)

        self.results_ev = Gtk.EventBox()
        self.results_ev.set_visible_window(True)
        self.results_ev.connect("button-press-event", lambda *_: True)
        results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        results_box.get_style_context().add_class("spotlight-results")
        results_box.set_size_request(w, -1)
        self.results_ev.add(results_box)

        self.launch_scroll = Gtk.ScrolledWindow()
        self.launch_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.launch_scroll.set_propagate_natural_height(True)
        self.launch_scroll.set_max_content_height(8 * 50)
        self.launch_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.launch_scroll.add(self.launch_list_box)
        results_box.pack_start(self.launch_scroll, True, True, 0)
        self.fixed.put(self.results_ev, x, y + 62)

    def place_search(self):
        x, y, w = self.search_bar_pos()
        self.search_box.set_size_request(w, -1)
        self.results_ev.get_child().set_size_request(w, -1)
        self.fixed.move(self.search_ev, x, y)
        self.fixed.move(self.results_ev, x, y + 62)

    def activate_search(self):
        self.search_active = True
        self.update_focus_visuals()

    def hud_widgets(self):
        return (self.left_ev, self.right_ev, self.search_ev, self.results_ev, self.info_popup)

    def on_info_hover_enter(self, *_):
        self.info_popup.show_all()
        return False

    def on_info_hover_leave(self, *_):
        self.info_popup.hide()
        return False

    def set_status(self, text: str):
        # Only action feedback is shown; with nothing to say the label (and its frame) disappears
        self.status_lbl.set_text(text)
        self.status_lbl.set_visible(bool(text))

    def tile_title(self, tile_id: str, name: str) -> str:
        return f"{self.tile_order.index(tile_id) + 1:02d} // {name}"

    def build_tiles(self):
        pos = self.default_positions()


        # 1. AUDIO TILE
        ax, ay, aw, ah = pos["audio"]
        t_audio = DraggableTile(self, "audio", self.tile_title("audio", "AUDIO MIXER"), aw, ah, ax, ay)
        audio_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        audio_hint = Gtk.Label(label="Per-application & Master volume")
        audio_hint.get_style_context().add_class("row-sub")
        audio_hint.set_xalign(0)
        audio_top.pack_start(audio_hint, True, True, 0)
        ref_audio_btn = Gtk.Button(label="[REFRESH]")
        ref_audio_btn.get_style_context().add_class("mono-btn")
        ref_audio_btn.connect("clicked", lambda *_: (self.focus_tile("audio"), self.refresh_audio()))
        audio_top.pack_end(ref_audio_btn, False, False, 0)
        t_audio.body.pack_start(audio_top, False, False, 0)

        # Output device picker: one button per sink, the default one highlighted
        out_lbl = Gtk.Label(label="OUTPUT DEVICE [O]:")
        out_lbl.get_style_context().add_class("row-title")
        out_lbl.set_xalign(0)
        t_audio.body.pack_start(out_lbl, False, False, 0)
        self.audio_out_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        t_audio.body.pack_start(self.audio_out_box, False, False, 0)

        self.audio_scroll = Gtk.ScrolledWindow()
        self.audio_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.audio_scroll.connect("button-press-event", lambda *_: self.focus_tile("audio") or False)
        self.audio_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.audio_scroll.add(self.audio_list_box)
        t_audio.body.pack_start(self.audio_scroll, True, True, 0)

        self.tiles["audio"] = t_audio
        self.fixed.put(t_audio, t_audio.x, t_audio.y)

        # 2. SCREENSHOTS TILE
        sx, sy, sw, sh = pos["screenshots"]
        t_shot = DraggableTile(
            self, "screenshots", self.tile_title("screenshots", "RECENT SCREENSHOTS"), sw, sh, sx, sy
        )
        self.shot_preview_ev = Gtk.EventBox()
        self.shot_preview_ev.get_style_context().add_class("preview-box")
        self.shot_preview_ev.set_size_request(sw - 30, 220)
        self.shot_preview_ev.connect("button-press-event", lambda *_: self.focus_tile("screenshots") or False)
        self.shot_preview_img = Gtk.Image()
        self.shot_preview_ev.add(self.shot_preview_img)
        t_shot.body.pack_start(self.shot_preview_ev, False, False, 0)

        shot_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_copy = Gtk.Button(label="[ENTER] COPY")
        btn_copy.get_style_context().add_class("mono-btn")
        btn_copy.connect("clicked", lambda *_: (self.focus_tile("screenshots"), self.action_copy_screenshot()))
        shot_actions.pack_start(btn_copy, True, True, 0)

        btn_open = Gtk.Button(label="[O] OPEN")
        btn_open.get_style_context().add_class("mono-btn")
        btn_open.connect("clicked", lambda *_: (self.focus_tile("screenshots"), self.action_open_screenshot()))
        shot_actions.pack_start(btn_open, False, False, 0)

        btn_del = Gtk.Button(label="[DEL] DELETE")
        btn_del.get_style_context().add_class("mono-btn")
        btn_del.connect("clicked", lambda *_: (self.focus_tile("screenshots"), self.action_delete_screenshot()))
        shot_actions.pack_start(btn_del, False, False, 0)
        t_shot.body.pack_start(shot_actions, False, False, 0)

        self.shot_scroll = Gtk.ScrolledWindow()
        self.shot_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.shot_scroll.connect("button-press-event", lambda *_: self.focus_tile("screenshots") or False)
        self.shot_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.shot_scroll.add(self.shot_list_box)
        t_shot.body.pack_start(self.shot_scroll, True, True, 0)

        self.tiles["screenshots"] = t_shot
        self.fixed.put(t_shot, t_shot.x, t_shot.y)

        # 3. WALLPAPER TILE
        wx, wy, ww, wh = pos["wallpaper"]
        t_wall = DraggableTile(
            self, "wallpaper", self.tile_title("wallpaper", "QUICK WALLPAPER"), ww, wh, wx, wy
        )
        mon_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        mon_lbl = Gtk.Label(label="TARGET:")
        mon_lbl.get_style_context().add_class("row-title")
        mon_bar.pack_start(mon_lbl, False, False, 0)

        self.mon_btns = []
        mon_labels = [f"{n} ({aspect_label(w, h)})" for n, w, h in self.monitors]
        if len(self.monitors) > 1:
            mon_labels.append("ALL")
        for idx, mname in enumerate(mon_labels):
            b = Gtk.Button(label=f"[{mname}]")
            b.connect("clicked", lambda _w, i=idx: self.select_wall_monitor(i))
            mon_bar.pack_start(b, True, True, 0)
            self.mon_btns.append(b)
        t_wall.body.pack_start(mon_bar, False, False, 0)

        self.wall_scroll = Gtk.ScrolledWindow()
        self.wall_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.wall_scroll.connect("button-press-event", lambda *_: self.focus_tile("wallpaper") or False)
        self.wall_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.wall_scroll.add(self.wall_list_box)
        t_wall.body.pack_start(self.wall_scroll, True, True, 0)

        self.tiles["wallpaper"] = t_wall
        self.fixed.put(t_wall, t_wall.x, t_wall.y)

        # 4. BLUETOOTH TILE
        bx, by, bw, bh = pos["bluetooth"]
        t_bt = DraggableTile(
            self, "bluetooth", self.tile_title("bluetooth", "BLUETOOTH"), bw, bh, bx, by
        )
        bt_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.bt_power_btn = Gtk.Button(label="[P] POWER: ON")
        self.bt_power_btn.get_style_context().add_class("mono-btn-active")
        self.bt_power_btn.connect("clicked", lambda *_: self.toggle_bt_power())
        bt_bar.pack_start(self.bt_power_btn, True, True, 0)

        self.bt_scan_btn = Gtk.Button(label="[S] SCAN")
        self.bt_scan_btn.get_style_context().add_class("mono-btn")
        self.bt_scan_btn.connect("clicked", lambda *_: self.trigger_bt_scan())
        bt_bar.pack_start(self.bt_scan_btn, True, True, 0)

        bt_ref_btn = Gtk.Button(label="[REFRESH]")
        bt_ref_btn.get_style_context().add_class("mono-btn")
        bt_ref_btn.connect("clicked", lambda *_: (self.focus_tile("bluetooth"), self.refresh_bluetooth()))
        bt_bar.pack_start(bt_ref_btn, False, False, 0)
        t_bt.body.pack_start(bt_bar, False, False, 0)

        self.bt_scroll = Gtk.ScrolledWindow()
        self.bt_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.bt_scroll.connect("button-press-event", lambda *_: self.focus_tile("bluetooth") or False)
        self.bt_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.bt_scroll.add(self.bt_list_box)
        t_bt.body.pack_start(self.bt_scroll, True, True, 0)

        self.tiles["bluetooth"] = t_bt
        self.fixed.put(t_bt, t_bt.x, t_bt.y)

        # BRIGHTNESS TILE
        gx, gy, gw, gh = pos["brightness"]
        t_bright = DraggableTile(
            self, "brightness", self.tile_title("brightness", "DISPLAY BRIGHTNESS"), gw, gh, gx, gy
        )
        bright_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bright_hint = Gtk.Label(label="Hardware brightness (DDC/CI)")
        bright_hint.get_style_context().add_class("row-sub")
        bright_hint.set_xalign(0)
        bright_bar.pack_start(bright_hint, True, True, 0)
        redetect_btn = Gtk.Button(label="[D] REDETECT")
        redetect_btn.get_style_context().add_class("mono-btn")
        redetect_btn.connect("clicked", lambda *_: (self.focus_tile("brightness"), self.detect_displays(force=True)))
        bright_bar.pack_end(redetect_btn, False, False, 0)
        t_bright.body.pack_start(bright_bar, False, False, 0)

        self.bright_scroll = Gtk.ScrolledWindow()
        self.bright_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.bright_scroll.connect("button-press-event", lambda *_: self.focus_tile("brightness") or False)
        self.bright_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.bright_scroll.add(self.bright_list_box)
        t_bright.body.pack_start(self.bright_scroll, True, True, 0)

        self.tiles["brightness"] = t_bright
        self.fixed.put(t_bright, t_bright.x, t_bright.y)

        # 5. SYSTEM MONITOR TILE
        yx, yy, yw, yh = pos["system"]
        t_sys = DraggableTile(
            self, "system", self.tile_title("system", "SYSTEM MONITOR"), yw, yh, yx, yy
        )
        sys_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_btop = Gtk.Button(label="[ENTER] BTOP")
        btn_btop.get_style_context().add_class("mono-btn")
        btn_btop.connect("clicked", lambda *_: self.open_btop())
        sys_bar.pack_start(btn_btop, True, True, 0)

        self.sys_update_btn = Gtk.Button(label="[U] UPDATES: ...")
        self.sys_update_btn.get_style_context().add_class("mono-btn")
        self.sys_update_btn.connect("clicked", lambda *_: self.run_system_update())
        sys_bar.pack_start(self.sys_update_btn, True, True, 0)
        t_sys.body.pack_start(sys_bar, False, False, 0)

        self.sys_scroll = Gtk.ScrolledWindow()
        self.sys_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.sys_scroll.connect("button-press-event", lambda *_: self.focus_tile("system") or False)
        self.sys_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.sys_scroll.add(self.sys_list_box)
        t_sys.body.pack_start(self.sys_scroll, True, True, 0)

        for key, title in (
            ("cpu", "CPU"),
            ("ram", "RAM"),
            ("gpu", "GPU"),
            ("vram", "VRAM"),
            ("disk", "DISK /"),
        ):
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            row.get_style_context().add_class("item-row")
            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl = Gtk.Label(label=title)
            lbl.get_style_context().add_class("row-title")
            lbl.set_xalign(0)
            top.pack_start(lbl, True, True, 0)
            val_lbl = Gtk.Label(label="--")
            val_lbl.get_style_context().add_class("row-title")
            top.pack_end(val_lbl, False, False, 0)
            row.pack_start(top, False, False, 0)
            bar = Gtk.ProgressBar()
            row.pack_start(bar, False, False, 0)
            self.sys_list_box.pack_start(row, False, False, 0)
            self.sys_rows[key] = (val_lbl, bar)

        self.sys_info_lbl = Gtk.Label(label="")
        self.sys_info_lbl.get_style_context().add_class("row-sub")
        self.sys_info_lbl.set_xalign(0)
        self.sys_info_lbl.set_margin_start(12)
        self.sys_info_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.sys_list_box.pack_start(self.sys_info_lbl, False, False, 4)

        self.tiles["system"] = t_sys
        self.fixed.put(t_sys, t_sys.x, t_sys.y)

    # ---------------- APP LAUNCHER LOGIC ----------------
    def load_launcher_apps(self):
        apps = []
        for info in Gio.AppInfo.get_all():
            if not info.should_show():
                continue
            name = info.get_display_name() or info.get_name() or ""
            generic = getattr(info, "get_generic_name", lambda: None)() or ""
            keywords = getattr(info, "get_keywords", lambda: [])() or []
            apps.append(
                {
                    "id": info.get_id() or name,
                    "info": info,
                    "name": name,
                    "name_l": name.lower(),
                    "words": [w for w in re.split(r"[\s\-_.]+", name.lower()) if w],
                    "extra_l": " ".join(
                        [generic, " ".join(keywords), info.get_executable() or "", info.get_description() or ""]
                    ).lower(),
                    "sub": generic or info.get_description() or "",
                }
            )
        self.launch_apps = apps

    def launcher_match(self, app, query):
        # Lower is better; None = no match. Every query word has to match somewhere.
        score = 0
        for q in query.split():
            if app["name_l"].startswith(q):
                s = 0
            elif any(w.startswith(q) for w in app["words"]):
                s = 1
            elif q in app["name_l"]:
                s = 2
            elif q in app["extra_l"]:
                s = 3
            else:
                return None
            score = max(score, s)
        return score

    def refresh_launcher(self):
        first = not self.launch_apps
        self.load_launcher_apps()
        self.refresh_launcher_results()
        if first and self.daemon:
            self.prewarm_icons()

    def refresh_launcher_results(self):
        query = self.launch_entry.get_text().strip().lower()
        ranked = []
        for app in self.launch_apps:
            score = self.launcher_match(app, query) if query else 0
            if score is not None:
                ranked.append((score, -self.app_usage.get(app["id"], 0), app["name_l"], app))
        ranked.sort(key=lambda r: r[:3])
        self.launch_results = [r[3] for r in ranked[:LAUNCHER_MAX_RESULTS]] if query else []
        self.launch_sel = 0

        for child in self.launch_list_box.get_children():
            self.launch_list_box.remove(child)
        self.launch_rows = []

        # Spotlight-style: nothing below the bar until something is typed
        if not query:
            self.results_ev.hide()
            self.fixed.queue_draw()
            return

        for idx, app in enumerate(self.launch_results):
            ev = Gtk.EventBox()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.get_style_context().add_class("item-row-selected" if idx == 0 else "item-row")
            ev.add(row)

            pixbuf = self.app_icon(app)
            img = Gtk.Image.new_from_pixbuf(pixbuf) if pixbuf else Gtk.Image()
            img.set_size_request(32, 32)
            row.pack_start(img, False, False, 0)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_valign(Gtk.Align.CENTER)
            lbl = Gtk.Label(label=app["name"])
            lbl.get_style_context().add_class("row-title")
            lbl.set_xalign(0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            vbox.pack_start(lbl, False, False, 0)
            if app["sub"]:
                sub = Gtk.Label(label=app["sub"])
                sub.get_style_context().add_class("row-sub")
                sub.set_xalign(0)
                sub.set_ellipsize(Pango.EllipsizeMode.END)
                vbox.pack_start(sub, False, False, 0)
            row.pack_start(vbox, True, True, 0)

            ev.connect("button-press-event", self.on_launch_row_click, idx)
            self.launch_list_box.pack_start(ev, False, False, 0)
            self.launch_rows.append(row)

        if not self.launch_results:
            empty = Gtk.Label(label="NO MATCHING APPLICATIONS")
            empty.get_style_context().add_class("row-sub")
            empty.set_margin_top(12)
            self.launch_list_box.pack_start(empty, False, False, 0)

        self.launch_list_box.show_all()
        # Gtk.Fixed allocates children at their minimum size, so size the list to its content
        _min_h, nat_h = self.launch_list_box.get_preferred_height()
        self.launch_scroll.set_min_content_height(min(nat_h, 8 * 50))
        self.launch_scroll.get_vadjustment().set_value(0)
        self.results_ev.show_all()
        self.update_focus_visuals()

    def app_icon(self, app):
        # Icons are rendered once per app; rebuilding results per keystroke then stays cheap
        if app["id"] in self.icon_cache:
            return self.icon_cache[app["id"]]
        pixbuf = None
        icon = app["info"].get_icon()
        if icon:
            try:
                info = Gtk.IconTheme.get_default().lookup_by_gicon(icon, 32, Gtk.IconLookupFlags.FORCE_SIZE)
                pixbuf = info.load_icon() if info else None
            except Exception:
                pixbuf = None
        self.icon_cache[app["id"]] = pixbuf
        return pixbuf

    def prewarm_icons(self):
        apps = list(self.launch_apps)

        def _next():
            for _ in range(4):
                if not apps:
                    return False
                self.app_icon(apps.pop())
            return True

        GLib.idle_add(_next, priority=GLib.PRIORITY_LOW)

    def select_launch_row(self, idx):
        if not self.launch_rows:
            return
        idx %= len(self.launch_rows)
        for i in (self.launch_sel, idx):
            if 0 <= i < len(self.launch_rows):
                ctx = self.launch_rows[i].get_style_context()
                ctx.remove_class("item-row")
                ctx.remove_class("item-row-selected")
                ctx.add_class("item-row-selected" if i == idx else "item-row")
        self.launch_sel = idx
        scroll_row_into_view(self.launch_scroll, self.launch_list_box, idx)

    def on_launch_row_click(self, _widget, event, idx):
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.select_launch_row(idx)
            self.launch_app()
        return True

    def launch_app(self):
        if not self.launch_results:
            return
        app = self.launch_results[self.launch_sel]
        info = app["info"]
        try:
            if info.get_boolean("Terminal"):
                # GLib doesn't know alacritty, so terminal apps go through it explicitly
                cmd = [a for a in shlex.split(info.get_commandline() or "") if not re.fullmatch(r"%[a-zA-Z]", a)]
                subprocess.Popen([TERMINAL, "-e", *cmd])
            else:
                info.launch([], Gdk.Display.get_default().get_app_launch_context())
        except Exception as exc:
            self.set_status(f"LAUNCH FAILED: {app['name']}")
            print(f"launch failed for {app['id']}: {exc}", file=sys.stderr)
            return
        self.app_usage[app["id"]] = self.app_usage.get(app["id"], 0) + 1
        try:
            APP_USAGE_FILE.write_text(json.dumps(self.app_usage))
        except Exception:
            pass
        self.hide_overlay()

    def on_launcher_key(self, key):
        if key in ("Down", "Page_Down"):
            self.select_launch_row(self.launch_sel + (1 if key == "Down" else 5))
            return True
        if key in ("Up", "Page_Up"):
            self.select_launch_row(self.launch_sel - (1 if key == "Up" else 5))
            return True
        if key in ("Return", "KP_Enter"):
            self.launch_app()
            return True
        # Everything else is typing: hand it to the search entry
        if not self.launch_entry.has_focus():
            self.launch_entry.grab_focus_without_selecting()
        return False

    # ---------------- AUDIO MIXER LOGIC ----------------
    def query_audio_state(self):
        items = []
        sinks_raw = run_cmd(["pactl", "-f", "json", "list", "sinks"])
        default_sink = run_cmd(["pactl", "get-default-sink"])
        try:
            sinks = json.loads(sinks_raw) if sinks_raw else []
            chosen = sinks[0] if sinks else None
            for s in sinks:
                if s.get("name") == default_sink:
                    chosen = s
                    break
            self.audio_sinks = [
                (s.get("name", ""), s.get("description") or s.get("name", "")) for s in sinks
            ]
            self.audio_default_sink = chosen.get("name", "") if chosen else ""
            if chosen:
                vol_dict = chosen.get("volume", {})
                first_ch = next(iter(vol_dict.values()), {})
                pct_str = first_ch.get("value_percent", "100%").replace("%", "").strip()
                vol_pct = int(pct_str) if pct_str.isdigit() else 100
                desc = chosen.get("description") or chosen.get("name") or "Master Output"
                items.append(
                    {
                        "kind": "sink",
                        "id": chosen.get("name", "@DEFAULT_SINK@"),
                        "title": "MASTER OUTPUT",
                        "subtitle": desc,
                        "volume": vol_pct,
                        "mute": bool(chosen.get("mute", False)),
                    }
                )
        except Exception:
            pass

        inputs_raw = run_cmd(["pactl", "-f", "json", "list", "sink-inputs"])
        try:
            inputs = json.loads(inputs_raw) if inputs_raw else []
            for inp in inputs:
                idx = inp.get("index")
                props = inp.get("properties", {})
                app_name = (
                    props.get("application.name")
                    or props.get("node.name")
                    or props.get("application.process.binary")
                    or f"Stream #{idx}"
                )
                media_name = props.get("media.name") or ""
                vol_dict = inp.get("volume", {})
                first_ch = next(iter(vol_dict.values()), {})
                pct_str = first_ch.get("value_percent", "100%").replace("%", "").strip()
                vol_pct = int(pct_str) if pct_str.isdigit() else 100
                items.append(
                    {
                        "kind": "input",
                        "id": str(idx),
                        "title": app_name.upper(),
                        "subtitle": media_name[:44],
                        "volume": vol_pct,
                        "mute": bool(inp.get("mute", False)),
                    }
                )
        except Exception:
            pass
        return items

    def audio_signature(self):
        return (self.audio_default_sink, tuple(n for n, _ in self.audio_sinks), len(self.audio_items))

    def refresh_audio(self):
        self.audio_items = self.query_audio_state()
        if self.audio_sel >= len(self.audio_items):
            self.audio_sel = max(0, len(self.audio_items) - 1)

        for child in self.audio_out_box.get_children():
            self.audio_out_box.remove(child)
        for name, desc in self.audio_sinks:
            active = name == self.audio_default_sink
            b = Gtk.Button(label=f"[{'*' if active else ' '}] {desc}")
            b.get_style_context().add_class("mono-btn-active" if active else "mono-btn")
            b.get_child().set_xalign(0)
            b.get_child().set_ellipsize(Pango.EllipsizeMode.END)
            b.set_tooltip_text(name)
            b.connect("clicked", lambda _w, n=name: (self.focus_tile("audio"), self.set_audio_output(n)))
            self.audio_out_box.pack_start(b, False, False, 0)
        self.audio_out_box.show_all()

        for child in self.audio_list_box.get_children():
            self.audio_list_box.remove(child)

        for idx, item in enumerate(self.audio_items):
            ev = Gtk.EventBox()
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            row.get_style_context().add_class(
                "item-row-selected" if idx == self.audio_sel else "item-row"
            )
            ev.add(row)

            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            mute_tag = "[MUTED] " if item["mute"] else ""
            lbl = Gtk.Label(label=f"{mute_tag}{item['title']}")
            lbl.get_style_context().add_class("row-title")
            lbl.set_xalign(0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            top.pack_start(lbl, True, True, 0)

            val_lbl = Gtk.Label(label=f"{item['volume']}%")
            val_lbl.get_style_context().add_class("row-title")
            top.pack_start(val_lbl, False, False, 0)

            mute_btn = Gtk.Button(label="[MUTE]" if not item["mute"] else "[UNMUTE]")
            mute_btn.get_style_context().add_class(
                "mono-btn-active" if item["mute"] else "mono-btn"
            )
            mute_btn.connect("clicked", lambda _w, i=idx: self.toggle_audio_mute(i))
            top.pack_end(mute_btn, False, False, 0)
            row.pack_start(top, False, False, 0)

            if item["subtitle"]:
                sub = Gtk.Label(label=item["subtitle"])
                sub.get_style_context().add_class("row-sub")
                sub.set_xalign(0)
                sub.set_ellipsize(Pango.EllipsizeMode.END)
                row.pack_start(sub, False, False, 0)

            adj = Gtk.Adjustment(
                value=item["volume"], lower=0, upper=150, step_increment=5, page_increment=10
            )
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
            scale.set_draw_value(False)
            scale.connect(
                "value-changed",
                lambda s, i=idx, vl=val_lbl: self.on_audio_slider_change(i, int(s.get_value()), vl),
            )
            row.pack_start(scale, False, False, 0)

            ev.connect("button-press-event", lambda _w, _e, i=idx: self.select_audio_row(i))
            self.audio_list_box.pack_start(ev, False, False, 0)

        self.audio_list_box.show_all()
        scroll_row_into_view(self.audio_scroll, self.audio_list_box, self.audio_sel)

    def select_audio_row(self, idx):
        self.focus_tile("audio")
        self.audio_sel = idx
        self.refresh_audio()
        return True

    def on_audio_slider_change(self, idx, new_vol, val_lbl):
        if idx < 0 or idx >= len(self.audio_items):
            return
        item = self.audio_items[idx]
        item["volume"] = new_vol
        val_lbl.set_text(f"{new_vol}%")
        if item["kind"] == "sink":
            subprocess.Popen(["pactl", "set-sink-volume", item["id"], f"{new_vol}%"])
        else:
            subprocess.Popen(["pactl", "set-sink-input-volume", item["id"], f"{new_vol}%"])

    def adjust_selected_audio(self, delta):
        if not self.audio_items:
            return
        item = self.audio_items[self.audio_sel]
        new_vol = max(0, min(150, item["volume"] + delta))
        item["volume"] = new_vol
        if item["kind"] == "sink":
            run_cmd(["pactl", "set-sink-volume", item["id"], f"{new_vol}%"])
        else:
            run_cmd(["pactl", "set-sink-input-volume", item["id"], f"{new_vol}%"])
        self.set_status(f"{item['title']}: {new_vol}%")
        self.refresh_audio()

    def set_audio_output(self, sink_name):
        run_cmd(["pactl", "set-default-sink", sink_name])
        # Streams that were ever routed explicitly don't follow the default, so move them all
        try:
            inputs = json.loads(run_cmd(["pactl", "-f", "json", "list", "sink-inputs"]) or "[]")
        except Exception:
            inputs = []
        for inp in inputs:
            run_cmd(["pactl", "move-sink-input", str(inp.get("index")), sink_name])
        desc = dict(self.audio_sinks).get(sink_name, sink_name)
        self.set_status(f"OUTPUT: {desc}")
        self.refresh_audio()

    def cycle_audio_output(self, step=1):
        names = [n for n, _ in self.audio_sinks]
        if not names:
            return
        cur = names.index(self.audio_default_sink) if self.audio_default_sink in names else -1
        self.set_audio_output(names[(cur + step) % len(names)])

    def toggle_audio_mute(self, idx=None):
        if not self.audio_items:
            return
        if idx is None:
            idx = self.audio_sel
        self.audio_sel = idx
        item = self.audio_items[idx]
        if item["kind"] == "sink":
            run_cmd(["pactl", "set-sink-mute", item["id"], "toggle"])
        else:
            run_cmd(["pactl", "set-sink-input-mute", item["id"], "toggle"])
        self.refresh_audio()

    # ---------------- SCREENSHOTS LOGIC ----------------
    def refresh_screenshots(self):
        shots = []
        for p in PICTURES_DIR.glob("*.png"):
            try:
                st = p.stat()
                if st.st_size > 0:
                    shots.append((st.st_mtime, p))
            except Exception:
                pass
        shots.sort(key=lambda x: x[0], reverse=True)
        shots = shots[:15]
        # Same files as last time -> the tile already shows them; a rebuild would only flicker
        sig = tuple((p.name, m) for m, p in shots)
        if sig == self.shots_sig:
            return
        self.shots_sig = sig
        self.screenshots = [p for _, p in shots]
        if self.shot_sel >= len(self.screenshots):
            self.shot_sel = max(0, len(self.screenshots) - 1)

        self.rebuild_screenshot_ui()

    def get_scaled_pixbuf(self, path: Path, w: int, h: int, cache_dir: Path = None):
        try:
            if cache_dir:
                cfile = cache_dir / f"{path.name}_{w}x{h}.png"
                if cfile.exists() and cfile.stat().st_mtime >= path.stat().st_mtime:
                    return GdkPixbuf.Pixbuf.new_from_file(str(cfile))
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), w, h, True)
            if cache_dir and pb:
                pb.savev(str(cfile), "png", [], [])
            return pb
        except Exception:
            return None

    def rebuild_screenshot_ui(self):
        for child in self.shot_list_box.get_children():
            self.shot_list_box.remove(child)

        t_shot = self.tiles.get("screenshots")
        pw = max(260, (t_shot.tile_width if t_shot else 470) - 34)
        ph = max(140, min(320, int(pw * 0.52)))
        self.shot_preview_ev.set_size_request(pw, ph)

        if self.screenshots and 0 <= self.shot_sel < len(self.screenshots):
            sel_path = self.screenshots[self.shot_sel]
            pb = self.get_scaled_pixbuf(sel_path, pw - 6, ph - 6, SHOT_THUMB_DIR)
            if pb:
                self.shot_preview_img.set_from_pixbuf(pb)

        for idx, spath in enumerate(self.screenshots):
            ev = Gtk.EventBox()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.get_style_context().add_class(
                "item-row-selected" if idx == self.shot_sel else "item-row"
            )
            ev.add(row)

            thumb_pb = self.get_scaled_pixbuf(spath, 96, 54, SHOT_THUMB_DIR)
            if thumb_pb:
                img = Gtk.Image.new_from_pixbuf(thumb_pb)
                img.get_style_context().add_class("preview-box")
                row.pack_start(img, False, False, 0)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            prefix = "* " if idx == self.shot_sel else "  "
            lbl = Gtk.Label(label=f"{prefix}{spath.name}")
            lbl.get_style_context().add_class("row-title")
            lbl.set_xalign(0)
            vbox.pack_start(lbl, False, False, 0)

            kb = spath.stat().st_size // 1024
            sub = Gtk.Label(label=f"Size: {kb} KB  |  Double-click: copy")
            sub.get_style_context().add_class("row-sub")
            sub.set_xalign(0)
            vbox.pack_start(sub, False, False, 0)

            row.pack_start(vbox, True, True, 0)
            ev.connect("button-press-event", self.on_shot_row_click, idx)
            self.shot_list_box.pack_start(ev, False, False, 0)

        self.shot_list_box.show_all()
        scroll_row_into_view(self.shot_scroll, self.shot_list_box, self.shot_sel)

    def on_shot_row_click(self, _widget, event, idx):
        self.focus_tile("screenshots")
        self.shot_sel = idx
        self.rebuild_screenshot_ui()
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.action_copy_screenshot()
        return True

    def action_copy_screenshot(self):
        if not self.screenshots:
            return
        spath = self.screenshots[self.shot_sel]
        try:
            with open(spath, "rb") as f:
                subprocess.run(["wl-copy", "--type", "image/png"], stdin=f, timeout=2)
            self.set_status(f"COPIED: {spath.name}")
        except Exception:
            self.set_status("COPY FAILED")

    def action_open_screenshot(self):
        if not self.screenshots:
            return
        spath = self.screenshots[self.shot_sel]
        subprocess.Popen(["xdg-open", str(spath)])
        self.hide_overlay()

    def action_delete_screenshot(self):
        if not self.screenshots:
            return
        spath = self.screenshots[self.shot_sel]
        try:
            spath.unlink(missing_ok=True)
            self.set_status(f"DELETED: {spath.name}")
        except Exception:
            pass
        self.refresh_screenshots()

    # ---------------- WALLPAPER LOGIC ----------------
    def get_active_wall(self, mon: str):
        ref = self.wall_monitors[0] if mon == "ALL" else mon
        sf = HOME / f".config/hypr/.wallpaper_{ref}"
        if sf.exists():
            return sf.read_text().strip()
        return ""

    def select_wall_monitor(self, idx):
        self.focus_tile("wallpaper")
        self.wall_mon_idx = idx % len(self.wall_monitors)
        self.refresh_wallpapers()

    @staticmethod
    def file_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def wall_thumb_pixbuf(self, wpath: Path):
        tfile = THUMB_DIR / f"{wpath.name}.png"
        mtime = self.file_mtime(tfile)
        if not mtime:
            return None
        cached = self.wall_pixbufs.get(tfile.name)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(tfile), 120, 68, True)
        except Exception:
            return None
        self.wall_pixbufs[tfile.name] = (mtime, pb)
        return pb

    def queue_wall_thumbs(self, paths):
        # Wallpapers added by hand (or by anything else) get a thumbnail too – same file name
        # and ffmpeg filter as wallpaper.sh / wall-downloader, so all of them share one cache
        for wpath in paths:
            key = (str(wpath), self.file_mtime(wpath))
            if key in self.thumb_pending or key in self.thumb_failed:
                continue
            if self.file_mtime(THUMB_DIR / f"{wpath.name}.png") >= key[1]:
                continue
            self.thumb_pending.add(key)
            self.thumb_queue.put(key)

    def thumb_worker(self):
        # One background thread; ffmpeg never runs on the GTK main loop
        while True:
            key = self.thumb_queue.get()
            src = Path(key[0])
            dst = THUMB_DIR / f"{src.name}.png"
            tmp = THUMB_DIR / f".{src.name}.tmp.png"
            ok = False
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", str(src),
                     "-vf", "scale=160:90:force_original_aspect_ratio=increase,crop=160:90",
                     "-frames:v", "1", str(tmp)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=30,
                )
                if tmp.exists() and tmp.stat().st_size > 0:
                    tmp.replace(dst)
                    ok = True
            except Exception:
                pass
            finally:
                tmp.unlink(missing_ok=True)
            if not ok:
                self.thumb_failed.add(key)
            self.thumb_pending.discard(key)
            if self.thumb_queue.empty():
                GLib.idle_add(self._on_wall_thumbs_ready)

    def _on_wall_thumbs_ready(self):
        self.refresh_wallpapers()
        return False

    def refresh_wallpapers(self):
        for idx, b in enumerate(self.mon_btns):
            ctx = b.get_style_context()
            ctx.remove_class("mono-btn")
            ctx.remove_class("mono-btn-active")
            ctx.add_class("mono-btn-active" if idx == self.wall_mon_idx else "mono-btn")

        target_mon = self.wall_monitors[self.wall_mon_idx]
        active_wp = self.get_active_wall(target_mon)

        exts = {".mp4", ".webm", ".mkv", ".gif", ".jpg", ".jpeg", ".png", ".webp"}
        all_files = sorted(
            [p for p in WALL_DIR.iterdir() if p.is_file() and p.suffix.lower() in exts]
        )
        uw = [p for p in all_files if p.name.startswith("uw-")]
        fhd = [p for p in all_files if not p.name.startswith("uw-")]
        ref = self.wall_monitors[0] if target_mon == "ALL" else target_mon
        wide = any(n == ref and h and w / h >= 2 for n, w, h in self.monitors)
        self.wallpapers = (uw + fhd) if wide else (fhd + uw)

        if self.wall_sel >= len(self.wallpapers):
            self.wall_sel = max(0, len(self.wallpapers) - 1)

        self.queue_wall_thumbs(self.wallpapers)
        # Rebuild only when something visible changed (files, thumbnails, selection, [ACTIVE])
        sig = (
            tuple((p.name, self.file_mtime(p), self.file_mtime(THUMB_DIR / f"{p.name}.png"))
                  for p in self.wallpapers),
            self.wall_sel,
            self.wall_mon_idx,
            active_wp,
        )
        if sig == self.wall_sig:
            return
        self.wall_sig = sig

        for child in self.wall_list_box.get_children():
            self.wall_list_box.remove(child)

        for idx, wpath in enumerate(self.wallpapers):
            ev = Gtk.EventBox()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.get_style_context().add_class(
                "item-row-selected" if idx == self.wall_sel else "item-row"
            )
            ev.add(row)

            pb = self.wall_thumb_pixbuf(wpath)
            if pb:
                img = Gtk.Image.new_from_pixbuf(pb)
                img.get_style_context().add_class("preview-box")
                row.pack_start(img, False, False, 0)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            is_act = str(wpath) == active_wp
            act_str = "[ACTIVE] " if is_act else ""
            clean_name = wpath.stem.removeprefix("uw-")
            lbl = Gtk.Label(label=f"{act_str}{clean_name}")
            lbl.get_style_context().add_class("row-title")
            lbl.set_xalign(0)
            vbox.pack_start(lbl, False, False, 0)

            ratio = "21:9" if wpath.name.startswith("uw-") else "16:9"
            kind = "ANIMATED" if wpath.suffix.lower() in {".mp4", ".webm", ".gif", ".mkv"} else "STATIC"
            sub = Gtk.Label(label=f"[{ratio}] • {kind}")
            sub.get_style_context().add_class("row-sub")
            sub.set_xalign(0)
            vbox.pack_start(sub, False, False, 0)

            row.pack_start(vbox, True, True, 0)
            ev.connect("button-press-event", self.on_wall_row_click, idx)
            self.wall_list_box.pack_start(ev, False, False, 0)

        self.wall_list_box.show_all()
        scroll_row_into_view(self.wall_scroll, self.wall_list_box, self.wall_sel)

    def on_wall_row_click(self, _widget, event, idx):
        # dwuklik to 3 zdarzenia (PRESS, PRESS, _2BUTTON_PRESS) – reaguj tylko na zwykłe kliknięcie
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return True
        self.focus_tile("wallpaper")
        self.wall_sel = idx
        self.apply_selected_wallpaper()
        return True

    def apply_selected_wallpaper(self):
        if not self.wallpapers:
            return
        wpath = self.wallpapers[self.wall_sel]
        target_mon = self.wall_monitors[self.wall_mon_idx]
        subprocess.Popen([str(WALL_SCRIPT), "set", target_mon, str(wpath)])
        self.set_status(f"WALLPAPER ({target_mon}): {wpath.stem}")
        GLib.timeout_add(250, self.refresh_wallpapers)

    # ---------------- BLUETOOTH LOGIC ----------------
    def query_bluetooth_state(self):
        show_out = run_cmd(["bluetoothctl", "show"])
        powered = "Powered: yes" in show_out

        conn_out = run_cmd(["bluetoothctl", "devices", "Connected"])
        conn_macs = set()
        for ln in conn_out.splitlines():
            parts = ln.split(" ", 2)
            if len(parts) >= 2:
                conn_macs.add(parts[1].strip())

        devs_out = run_cmd(["bluetoothctl", "devices"])
        devices = []
        for ln in devs_out.splitlines():
            parts = ln.split(" ", 2)
            if len(parts) >= 3 and parts[0] == "Device":
                mac = parts[1].strip()
                name = parts[2].strip()
                is_conn = mac in conn_macs
                bat = ""
                icon = ""
                if is_conn:
                    info_out = run_cmd(["bluetoothctl", "info", mac])
                    m_bat = re.search(r"Battery Percentage:.*\((\d+)\)", info_out)
                    if m_bat:
                        bat = f"{m_bat.group(1)}%"
                    m_ico = re.search(r"Icon:\s*(\S+)", info_out)
                    if m_ico:
                        icon = m_ico.group(1)
                devices.append(
                    {
                        "mac": mac,
                        "name": name,
                        "connected": is_conn,
                        "battery": bat,
                        "icon": icon,
                    }
                )
        devices.sort(key=lambda d: (not d["connected"], d["name"].lower()))
        return powered, devices

    def refresh_bluetooth(self):
        self.bt_powered, self.bt_devices = self.query_bluetooth_state()
        if self.bt_sel >= len(self.bt_devices):
            self.bt_sel = max(0, len(self.bt_devices) - 1)

        pctx = self.bt_power_btn.get_style_context()
        pctx.remove_class("mono-btn")
        pctx.remove_class("mono-btn-active")
        if self.bt_powered:
            self.bt_power_btn.set_label("[P] POWER: ON")
            pctx.add_class("mono-btn-active")
        else:
            self.bt_power_btn.set_label("[P] POWER: OFF")
            pctx.add_class("mono-btn")

        for child in self.bt_list_box.get_children():
            self.bt_list_box.remove(child)

        for idx, dev in enumerate(self.bt_devices):
            ev = Gtk.EventBox()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.get_style_context().add_class(
                "item-row-selected" if idx == self.bt_sel else "item-row"
            )
            ev.add(row)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            status_tag = "[CONNECTED] " if dev["connected"] else ""
            lbl = Gtk.Label(label=f"{status_tag}{dev['name']}")
            lbl.get_style_context().add_class("row-title")
            lbl.set_xalign(0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            vbox.pack_start(lbl, False, False, 0)

            meta = [dev["mac"]]
            if dev["battery"]:
                meta.append(f"BAT: {dev['battery']}")
            if dev["icon"]:
                meta.append(dev["icon"])
            sub = Gtk.Label(label="  •  ".join(meta))
            sub.get_style_context().add_class("row-sub")
            sub.set_xalign(0)
            vbox.pack_start(sub, False, False, 0)

            row.pack_start(vbox, True, True, 0)

            act_btn = Gtk.Button(label="[DISCONNECT]" if dev["connected"] else "[CONNECT]")
            act_btn.get_style_context().add_class(
                "mono-btn-active" if dev["connected"] else "mono-btn"
            )
            act_btn.connect("clicked", lambda _w, i=idx: self.toggle_bt_device(i))
            row.pack_end(act_btn, False, False, 0)

            ev.connect("button-press-event", self.on_bt_row_click, idx)
            self.bt_list_box.pack_start(ev, False, False, 0)

        self.bt_list_box.show_all()
        scroll_row_into_view(self.bt_scroll, self.bt_list_box, self.bt_sel)

    def on_bt_row_click(self, _widget, event, idx):
        self.focus_tile("bluetooth")
        self.bt_sel = idx
        self.refresh_bluetooth()
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.toggle_bt_device(idx)
        return True

    def toggle_bt_power(self):
        self.focus_tile("bluetooth")
        new_state = "off" if self.bt_powered else "on"
        run_cmd(["bluetoothctl", "power", new_state])
        self.set_status(f"BLUETOOTH POWER: {new_state.upper()}")
        self.refresh_bluetooth()

    def trigger_bt_scan(self):
        self.focus_tile("bluetooth")
        if self.bt_scanning:
            return
        self.bt_scanning = True
        self.bt_scan_btn.set_label("[SCANNING...]")
        self.set_status("BT SCANNING (5s)...")

        def _scan_worker():
            run_cmd(["bluetoothctl", "--timeout", "5", "scan", "on"], timeout=7)
            GLib.idle_add(self._finish_bt_scan)

        threading.Thread(target=_scan_worker, daemon=True).start()

    def _finish_bt_scan(self):
        self.bt_scanning = False
        self.bt_scan_btn.set_label("[S] SCAN")
        self.set_status("BT SCAN COMPLETE")
        self.refresh_bluetooth()
        return False

    def toggle_bt_device(self, idx=None):
        self.focus_tile("bluetooth")
        if not self.bt_devices:
            return
        if idx is None:
            idx = self.bt_sel
        self.bt_sel = idx
        dev = self.bt_devices[idx]
        mac = dev["mac"]
        name = dev["name"]
        action = "disconnect" if dev["connected"] else "connect"
        self.set_status(f"BT {action.upper()}: {name}...")

        def _worker():
            run_cmd(["bluetoothctl", action, mac], timeout=8)
            GLib.idle_add(self._after_bt_toggle, name)

        threading.Thread(target=_worker, daemon=True).start()

    def _after_bt_toggle(self, name):
        self.refresh_bluetooth()
        self.set_status(f"BT UPDATED: {name}")
        return False

    # ---------------- BRIGHTNESS (DDC/CI) LOGIC ----------------
    def parse_ddc_detect(self, out):
        displays = []
        for block in re.split(r"\n(?=\S)", out):
            if not block.startswith("Display "):
                continue  # skips "Invalid display" blocks too
            m_bus = re.search(r"/dev/i2c-(\d+)", block)
            if not m_bus:
                continue
            m_conn = re.search(r"DRM[_ ]connector:\s+(?:card\d+-)?(\S+)", block)
            m_model = re.search(r"Model:\s+(.+)", block)
            conn = m_conn.group(1) if m_conn else ""
            model = m_model.group(1).strip() if m_model else ""
            displays.append(
                {
                    "bus": int(m_bus.group(1)),
                    "name": conn or model or f"i2c-{m_bus.group(1)}",
                    "model": model,
                    "value": None,
                    "max": 100,
                }
            )
        return displays

    def refresh_brightness(self):
        if self.bright_displays:
            self.read_brightness()
        elif self.bright_state != "detecting" or not getattr(self, "_bright_started", False):
            self._bright_started = True
            self.detect_displays()

    def detect_displays(self, force=False):
        if shutil.which("ddcutil") is None:
            self.bright_state = "missing"
            self.render_brightness()
            return
        if not any(Path("/dev").glob("i2c-*")):
            self.bright_state = "noi2c"
            self.render_brightness()
            return
        if not force:
            try:
                cached = json.loads(DDC_CACHE.read_text())
                self.bright_displays = [dict(d, value=None) for d in cached]
                self.bright_state = "ok" if self.bright_displays else "none"
                self.render_brightness()
                self.read_brightness()
                return
            except Exception:
                pass

        self.bright_state = "detecting"
        self.bright_displays = []
        self.render_brightness()

        def _worker():
            out = run_cmd(["ddcutil", "detect"], timeout=25)
            GLib.idle_add(self._finish_detect, self.parse_ddc_detect(out))

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_detect(self, displays):
        self.bright_displays = displays
        self.bright_state = "ok" if displays else "none"
        if displays:
            try:
                DDC_CACHE.write_text(json.dumps(displays))
            except Exception:
                pass
        self.render_brightness()
        self.read_brightness()
        return False

    def read_brightness(self):
        if self.bright_reading or not self.bright_displays:
            return
        self.bright_reading = True
        buses = [d["bus"] for d in self.bright_displays]

        def _worker():
            vals = {}
            for bus in buses:
                out = run_cmd(["ddcutil", "--bus", str(bus), "getvcp", "10", "--brief"], timeout=6)
                m = re.search(r"VCP 10 C (\d+) (\d+)", out)
                if m:
                    vals[bus] = (int(m.group(1)), int(m.group(2)))
            GLib.idle_add(self._finish_read_brightness, vals)

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_read_brightness(self, vals):
        self.bright_reading = False
        for d in self.bright_displays:
            # Don't overwrite a value the user is changing right now
            if d["bus"] in vals and d["bus"] not in self.bright_targets and d["bus"] not in self.bright_inflight:
                d["value"], d["max"] = vals[d["bus"]]
        self.render_brightness()
        return False

    def bright_item_value(self, idx):
        kind, d = self.bright_items[idx]
        if kind == "all":
            known = [x["value"] for x in self.bright_displays if x["value"] is not None]
            return round(sum(known) / len(known)) if known else None
        return d["value"]

    def render_brightness(self):
        for child in self.bright_list_box.get_children():
            self.bright_list_box.remove(child)
        self.bright_items = []
        self.bright_widgets = []

        messages = {
            "missing": ("DDCUTIL NOT INSTALLED", "sudo pacman -S ddcutil"),
            "noi2c": ("I2C-DEV MODULE NOT LOADED", "sudo modprobe i2c-dev"),
            "detecting": ("DETECTING DISPLAYS...", "ddcutil detect, takes a few seconds"),
            "none": ("NO DDC/CI DISPLAYS FOUND", "Enable DDC/CI in the monitor OSD, then [D]"),
        }
        if self.bright_state in messages:
            title, sub = messages[self.bright_state]
            for text, cls in ((title, "row-title"), (sub, "row-sub")):
                l = Gtk.Label(label=text)
                l.get_style_context().add_class(cls)
                l.set_xalign(0)
                l.set_margin_start(10)
                self.bright_list_box.pack_start(l, False, False, 0)
            self.bright_list_box.show_all()
            return

        if len(self.bright_displays) > 1:
            self.bright_items.append(("all", None))
        self.bright_items += [("display", d) for d in self.bright_displays]
        if self.bright_sel >= len(self.bright_items):
            self.bright_sel = 0

        for idx, (kind, d) in enumerate(self.bright_items):
            ev = Gtk.EventBox()
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            row.get_style_context().add_class("item-row-selected" if idx == self.bright_sel else "item-row")
            ev.add(row)

            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            title = "ALL DISPLAYS" if kind == "all" else d["name"]
            lbl = Gtk.Label(label=title)
            lbl.get_style_context().add_class("row-title")
            lbl.set_xalign(0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            top.pack_start(lbl, True, True, 0)
            value = self.bright_item_value(idx)
            val_lbl = Gtk.Label(label=f"{value}%" if value is not None else "--")
            val_lbl.get_style_context().add_class("row-title")
            top.pack_end(val_lbl, False, False, 0)
            row.pack_start(top, False, False, 0)

            if kind == "display" and d["model"] and d["model"] != d["name"]:
                sub = Gtk.Label(label=d["model"])
                sub.get_style_context().add_class("row-sub")
                sub.set_xalign(0)
                sub.set_ellipsize(Pango.EllipsizeMode.END)
                row.pack_start(sub, False, False, 0)

            upper = 100 if kind == "all" else d["max"]
            adj = Gtk.Adjustment(value=value or 0, lower=0, upper=upper, step_increment=5, page_increment=10)
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
            scale.set_draw_value(False)
            scale.set_sensitive(value is not None)
            hid = scale.connect("value-changed", lambda s, i=idx: self.set_brightness(i, int(s.get_value())))
            row.pack_start(scale, False, False, 0)

            ev.connect("button-press-event", lambda _w, _e, i=idx: self.select_bright_row(i))
            self.bright_list_box.pack_start(ev, False, False, 0)
            self.bright_widgets.append((scale, val_lbl, hid))

        self.bright_list_box.show_all()

    def select_bright_row(self, idx):
        self.focus_tile("brightness")
        self.bright_sel = idx
        self.render_brightness()
        return False

    def set_brightness(self, idx, value):
        if not (0 <= idx < len(self.bright_items)):
            return
        kind, d = self.bright_items[idx]
        targets = self.bright_displays if kind == "all" else [d]
        for t in targets:
            t["value"] = max(0, min(t["max"], value))
            self.bright_targets[t["bus"]] = t["value"]
        self.sync_bright_widgets()
        # Debounce: only the latest value per display is written, one write per bus at a time
        if self.bright_flush_id is None:
            self.bright_flush_id = GLib.timeout_add(150, self._flush_brightness)

    def sync_bright_widgets(self):
        for idx, (scale, val_lbl, hid) in enumerate(self.bright_widgets):
            value = self.bright_item_value(idx)
            if value is None:
                continue
            val_lbl.set_text(f"{value}%")
            if int(scale.get_value()) != value:
                scale.handler_block(hid)
                scale.set_value(value)
                scale.handler_unblock(hid)

    def _flush_brightness(self):
        self.bright_flush_id = None
        for bus in list(self.bright_targets):
            if bus in self.bright_inflight:
                continue
            value = self.bright_targets.pop(bus)
            self.bright_inflight.add(bus)
            threading.Thread(target=self._bright_worker, args=(bus, value), daemon=True).start()
        return False

    def _bright_worker(self, bus, value):
        run_cmd(["ddcutil", "--bus", str(bus), "setvcp", "10", str(value), "--noverify"], timeout=6)
        GLib.idle_add(self._bright_done, bus)

    def _bright_done(self, bus):
        self.bright_inflight.discard(bus)
        if bus in self.bright_targets and self.bright_flush_id is None:
            self.bright_flush_id = GLib.timeout_add(150, self._flush_brightness)
        return False

    def adjust_selected_brightness(self, delta):
        if not self.bright_items:
            return
        value = self.bright_item_value(self.bright_sel)
        if value is None:
            return
        self.set_brightness(self.bright_sel, value + delta)
        self.set_status(f"BRIGHTNESS: {self.bright_item_value(self.bright_sel)}%")

    # ---------------- SYSTEM MONITOR LOGIC ----------------
    def query_system_state(self):
        st = {}
        try:
            idle, total = read_cpu_times()
            p_idle, p_total = self.sys_cpu_prev
            self.sys_cpu_prev = (idle, total)
            if total > p_total:
                st["cpu"] = 100.0 * (1 - (idle - p_idle) / (total - p_total))
        except Exception:
            pass
        if self.cpu_temp_path:
            try:
                st["cpu_temp"] = int(self.cpu_temp_path.read_text()) / 1000
            except Exception:
                pass

        try:
            mem = {}
            with open("/proc/meminfo") as f:
                for ln in f:
                    k, v = ln.split(":", 1)
                    mem[k] = int(v.split()[0]) * 1024
            st["ram"] = (mem["MemTotal"] - mem["MemAvailable"], mem["MemTotal"])
        except Exception:
            pass

        out = run_cmd(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw",
                "--format=csv,noheader,nounits",
            ]
        )
        parts = [x.strip() for x in out.splitlines()[0].split(",")] if out else []
        if len(parts) >= 4:
            try:
                st["gpu"] = float(parts[0])
                st["gpu_temp"] = float(parts[1])
                st["vram"] = (float(parts[2]) * 1024**2, float(parts[3]) * 1024**2)
                st["gpu_power"] = float(parts[4])
            except (ValueError, IndexError):
                pass

        try:
            vfs = os.statvfs("/")
            used = (vfs.f_blocks - vfs.f_bfree) * vfs.f_frsize
            avail = vfs.f_bavail * vfs.f_frsize
            st["disk"] = (used, used + avail)
        except Exception:
            pass

        try:
            st["uptime"] = float(Path("/proc/uptime").read_text().split()[0])
            st["load"] = os.getloadavg()
        except Exception:
            pass
        return st

    def refresh_system(self):
        if self.sys_busy:
            return

        def _worker():
            st = self.query_system_state()
            GLib.idle_add(self._apply_system_state, st)

        self.sys_busy = True
        threading.Thread(target=_worker, daemon=True).start()

    def _apply_system_state(self, st):
        self.sys_busy = False

        def gib(n):
            return f"{n / 1024**3:.1f}"

        def put(key, text, frac):
            val_lbl, bar = self.sys_rows[key]
            val_lbl.set_text(text)
            bar.set_fraction(max(0.0, min(1.0, frac)))

        if "cpu" in st:
            temp = f"  •  {st['cpu_temp']:.0f}°C" if "cpu_temp" in st else ""
            put("cpu", f"{st['cpu']:.0f}%{temp}", st["cpu"] / 100)
        if "ram" in st:
            used, total = st["ram"]
            put("ram", f"{gib(used)} / {gib(total)} GiB", used / total)
        if "gpu" in st:
            extra = f"  •  {st['gpu_temp']:.0f}°C"
            if "gpu_power" in st:
                extra += f"  •  {st['gpu_power']:.0f}W"
            put("gpu", f"{st['gpu']:.0f}%{extra}", st["gpu"] / 100)
        if "vram" in st:
            used, total = st["vram"]
            put("vram", f"{gib(used)} / {gib(total)} GiB", used / total if total else 0)
        if "disk" in st:
            used, total = st["disk"]
            put("disk", f"{used / 1024**4:.2f} / {total / 1024**4:.2f} TiB", used / total if total else 0)

        info = []
        if "uptime" in st:
            mins = int(st["uptime"] // 60)
            info.append(f"UP {mins // 1440}d {mins % 1440 // 60}h {mins % 60}m" if mins >= 1440 else f"UP {mins // 60}h {mins % 60}m")
        if "load" in st:
            info.append("LOAD " + " ".join(f"{x:.2f}" for x in st["load"]))
        self.sys_info_lbl.set_text("  •  ".join(info))
        return False

    def check_updates(self):
        if self.upd_checking:
            return
        try:
            cached = json.loads(UPDATES_CACHE.read_text())
            if time.time() - cached["ts"] < UPDATES_CACHE_TTL:
                self.upd_counts = (cached["repo"], cached["aur"])
                self.render_updates()
                return
        except Exception:
            pass

        def _worker():
            repo = count_pending_updates(["checkupdates"])
            aur = count_pending_updates(["paru", "-Qua"])
            GLib.idle_add(self._finish_update_check, repo, aur)

        self.upd_checking = True
        self.render_updates()
        threading.Thread(target=_worker, daemon=True).start()

    def _finish_update_check(self, repo, aur):
        self.upd_checking = False
        self.upd_counts = (repo, aur)
        if repo is not None and aur is not None:
            try:
                UPDATES_CACHE.write_text(json.dumps({"ts": time.time(), "repo": repo, "aur": aur}))
            except Exception:
                pass
        self.render_updates()
        return False

    def render_updates(self):
        ctx = self.sys_update_btn.get_style_context()
        ctx.remove_class("mono-btn")
        ctx.remove_class("mono-btn-active")
        if self.upd_checking or self.upd_counts is None:
            self.sys_update_btn.set_label("[U] UPDATES: CHECKING...")
            ctx.add_class("mono-btn")
            return
        repo, aur = self.upd_counts
        total = (repo or 0) + (aur or 0)
        failed = "?" if repo is None or aur is None else ""
        self.sys_update_btn.set_label(f"[U] UPDATES: {total}{failed}")
        self.sys_update_btn.set_tooltip_text(f"repo: {repo if repo is not None else '?'}  •  AUR: {aur if aur is not None else '?'}")
        ctx.add_class("mono-btn-active" if total else "mono-btn")

    def open_btop(self):
        subprocess.Popen([TERMINAL, "-e", "btop"])
        self.hide_overlay()

    def run_system_update(self):
        UPDATES_CACHE.unlink(missing_ok=True)
        subprocess.Popen([TERMINAL, "-e", "paru"])
        self.hide_overlay()

    # ---------------- FOCUS & KEYBOARD NAVIGATION ----------------
    def on_fixed_draw(self, container, cr):
        for tid in self.z_order:
            tile = self.tiles.get(tid)
            if tile and tile.get_visible():
                container.propagate_draw(tile, cr)
        for hud_w in self.hud_widgets():
            if hud_w and hud_w.get_visible():
                container.propagate_draw(hud_w, cr)
        return True

    def focus_tile(self, tile_id: str):
        if tile_id in self.tile_order:
            self.search_active = False
            self.focused_tile_idx = self.tile_order.index(tile_id)
            self.update_focus_visuals()

    def cycle_focus(self, step: int):
        # Focus ring: search bar -> tiles in order -> back to the search bar
        ring = ["search"] + self.tile_order
        cur = "search" if self.search_active else self.tile_order[self.focused_tile_idx]
        nxt = ring[(ring.index(cur) + step) % len(ring)]
        if nxt == "search":
            self.activate_search()
        else:
            self.focus_tile(nxt)

    def update_focus_visuals(self):
        active_id = None if self.search_active else self.tile_order[self.focused_tile_idx]
        if active_id:
            if active_id in self.z_order:
                self.z_order.remove(active_id)
            self.z_order.append(active_id)

        for tid in self.z_order:
            tile = self.tiles[tid]
            tile.set_focused_style(tid == active_id)
            win = tile.get_window()
            if win:
                win.raise_()

        for hud_w in self.hud_widgets():
            if hud_w:
                win = hud_w.get_window()
                if win:
                    win.raise_()

        sctx = self.search_box.get_style_context()
        sctx.remove_class("spotlight-box")
        sctx.remove_class("spotlight-box-active")
        sctx.add_class("spotlight-box-active" if self.search_active else "spotlight-box")
        if self.search_active:
            if not self.launch_entry.has_focus():
                self.launch_entry.grab_focus_without_selecting()
        elif self.win is not None:
            self.win.set_focus(None)

        self.fixed.queue_draw()

    def on_backdrop_click(self, _widget, event):
        if (
            self.dragging_tile is None
            and self.resizing_tile is None
            and event.window == self.bg_ev.get_window()
        ):
            self.hide_overlay()
        return False

    def periodic_tick(self):
        if not self.is_visible:
            return True
        self.refresh_system()
        # Re-render on any sink/stream change (BT device connecting, default switched elsewhere)
        old_sig = self.audio_signature()
        new_items = self.query_audio_state()
        if (self.audio_default_sink, tuple(n for n, _ in self.audio_sinks), len(new_items)) != old_sig:
            self.refresh_audio()
        return True

    def on_key_press(self, _widget, event):
        key = Gdk.keyval_name(event.keyval) or ""
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)

        # Super+Tab is normally consumed by the Hyprland bind; handle it here too in case it gets through
        if key == "Escape" or (key in ("Tab", "ISO_Left_Tab") and event.state & Gdk.ModifierType.SUPER_MASK):
            # Spotlight-style Esc: first clear the query, then close
            if key == "Escape" and self.search_active and self.launch_entry.get_text():
                self.launch_entry.set_text("")
                return True
            self.hide_overlay()
            return True

        if key == "Tab":
            self.cycle_focus(+1)
            return True
        if key == "ISO_Left_Tab":
            self.cycle_focus(-1)
            return True
        if alt and key.isdigit() and 1 <= int(key) <= len(self.tile_order):
            self.focus_tile(self.tile_order[int(key) - 1])
            return True
        if self.search_active:
            return self.on_launcher_key(key)
        if key == "slash":
            self.activate_search()
            return True

        active_tile_id = self.tile_order[self.focused_tile_idx]
        active_tile_obj = self.tiles[active_tile_id]

        if ctrl and key in ("m", "M"):
            active_tile_obj.toggle_minimized()
            return True


        # Keyboard Resize: Ctrl + Arrows / HJKL
        if ctrl and key in ("Right", "l", "L", "Left", "h", "H", "Down", "j", "J", "Up", "k", "K"):
            if active_tile_obj.minimized:
                return True
            dw = 30 if key in ("Right", "l", "L") else (-30 if key in ("Left", "h", "H") else 0)
            dh = 30 if key in ("Down", "j", "J") else (-30 if key in ("Up", "k", "K") else 0)
            active_tile_obj.update_size_request(
                active_tile_obj.tile_width + dw, active_tile_obj.tile_height + dh
            )
            self.save_layout()
            if active_tile_id == "screenshots":
                self.rebuild_screenshot_ui()
            return True

        if key.isdigit() and 1 <= int(key) <= len(self.tile_order):
            self.focus_tile(self.tile_order[int(key) - 1])
            return True
        if key in ("r", "R"):
            self.reset_layout()
            return True

        if active_tile_id == "audio":
            if key in ("Down", "j", "J"):
                if self.audio_items:
                    self.audio_sel = (self.audio_sel + 1) % len(self.audio_items)
                    self.refresh_audio()
                return True
            if key in ("Up", "k", "K"):
                if self.audio_items:
                    self.audio_sel = (self.audio_sel - 1) % len(self.audio_items)
                    self.refresh_audio()
                return True
            if key in ("Right", "l", "L", "plus", "equal"):
                self.adjust_selected_audio(+5)
                return True
            if key in ("Left", "h", "H", "minus"):
                self.adjust_selected_audio(-5)
                return True
            if key in ("m", "M", "Return", "KP_Enter", "space"):
                self.toggle_audio_mute()
                return True
            if key == "o":
                self.cycle_audio_output(+1)
                return True
            if key == "O":
                self.cycle_audio_output(-1)
                return True

        elif active_tile_id == "brightness":
            if key in ("Down", "j", "J"):
                if self.bright_items:
                    self.bright_sel = (self.bright_sel + 1) % len(self.bright_items)
                    self.render_brightness()
                return True
            if key in ("Up", "k", "K"):
                if self.bright_items:
                    self.bright_sel = (self.bright_sel - 1) % len(self.bright_items)
                    self.render_brightness()
                return True
            if key in ("Right", "l", "L", "plus", "equal"):
                self.adjust_selected_brightness(+5)
                return True
            if key in ("Left", "h", "H", "minus"):
                self.adjust_selected_brightness(-5)
                return True
            if key in ("d", "D"):
                self.detect_displays(force=True)
                return True

        elif active_tile_id == "screenshots":
            if key in ("Down", "j", "J"):
                if self.screenshots:
                    self.shot_sel = (self.shot_sel + 1) % len(self.screenshots)
                    self.rebuild_screenshot_ui()
                return True
            if key in ("Up", "k", "K"):
                if self.screenshots:
                    self.shot_sel = (self.shot_sel - 1) % len(self.screenshots)
                    self.rebuild_screenshot_ui()
                return True
            if key in ("Return", "KP_Enter", "c", "C"):
                self.action_copy_screenshot()
                return True
            if key in ("o", "O"):
                self.action_open_screenshot()
                return True
            if key in ("Delete", "BackSpace", "x", "X"):
                self.action_delete_screenshot()
                return True

        elif active_tile_id == "wallpaper":
            if key in ("Down", "j", "J"):
                if self.wallpapers:
                    self.wall_sel = (self.wall_sel + 1) % len(self.wallpapers)
                    self.refresh_wallpapers()
                return True
            if key in ("Up", "k", "K"):
                if self.wallpapers:
                    self.wall_sel = (self.wall_sel - 1) % len(self.wallpapers)
                    self.refresh_wallpapers()
                return True
            if key in ("Left", "h", "H"):
                self.select_wall_monitor(self.wall_mon_idx - 1)
                return True
            if key in ("Right", "l", "L"):
                self.select_wall_monitor(self.wall_mon_idx + 1)
                return True
            if key in ("Return", "KP_Enter", "space"):
                self.apply_selected_wallpaper()
                return True

        elif active_tile_id == "bluetooth":
            if key in ("Down", "j", "J"):
                if self.bt_devices:
                    self.bt_sel = (self.bt_sel + 1) % len(self.bt_devices)
                    self.refresh_bluetooth()
                return True
            if key in ("Up", "k", "K"):
                if self.bt_devices:
                    self.bt_sel = (self.bt_sel - 1) % len(self.bt_devices)
                    self.refresh_bluetooth()
                return True
            if key in ("Return", "KP_Enter", "space"):
                self.toggle_bt_device()
                return True
            if key in ("p", "P"):
                self.toggle_bt_power()
                return True
            if key in ("s", "S"):
                self.trigger_bt_scan()
                return True

        elif active_tile_id == "system":
            if key in ("Return", "KP_Enter"):
                self.open_btop()
                return True
            if key in ("u", "U"):
                self.run_system_update()
                return True

        return False


def main():
    # --daemon: stay resident and hidden, Super+Tab only toggles the window (instant)
    # no flag:  signal a running instance, or start the daemon and show it right away
    #           (only the first press after a crash/reboot pays for the cold start)
    start_hidden = "--daemon" in sys.argv
    pid = find_running_pid()
    if pid:
        if start_hidden:
            sys.exit(0)
        try:
            os.kill(pid, signal.SIGUSR1)
            sys.exit(0)
        except ProcessLookupError:
            pass

    # Before the PID file exists nobody can signal us; after it, a Super+Tab during startup
    # would hit SIGUSR1's default action (terminate) – count those presses until the app is up
    early_toggles = []
    signal.signal(signal.SIGUSR1, lambda *_: early_toggles.append(1))
    PID_FILE.write_text(str(os.getpid()))
    try:
        app = CommandCenterApp(daemon=True)
        if not start_hidden:
            app.refresh_all_now()
            app.show_overlay()
        if len(early_toggles) % 2:
            app.toggle_visibility()
        Gtk.main()
    finally:
        if find_running_pid() is None or PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
