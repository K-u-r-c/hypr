#!/usr/bin/env python3
import json
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, GtkLayerShell, Pango

HOME = Path.home()
LAYOUT_FILE = HOME / ".config/hypr/command_center_layout.json"
WALL_SCRIPT = HOME / ".config/hypr/wallpaper.sh"
WALL_DIR = HOME / "Pictures/wallpapers"
THUMB_DIR = HOME / ".cache/wallpaper-thumbs"
SHOT_THUMB_DIR = HOME / ".cache/screenshot-thumbs"
PICTURES_DIR = HOME / "Pictures"
PID_FILE = Path("/tmp/hypr_command_center.pid")

THUMB_DIR.mkdir(parents=True, exist_ok=True)
SHOT_THUMB_DIR.mkdir(parents=True, exist_ok=True)

CSS = b"""
* {
    font-family: "JetBrainsMono Nerd Font", monospace;
    border-radius: 0;
    box-shadow: none;
    outline: none;
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
    background-color: rgba(255, 255, 255, 0.09);
    border-left: 2px solid #ffffff;
    padding: 6px 10px;
    margin: 2px 0;
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
    background-color: #0f0f0f;
    color: #cccccc;
    border: 1px solid #3a3a3a;
    padding: 4px 10px;
    font-size: 12px;
}

.mono-btn:hover {
    background-color: #222222;
    color: #ffffff;
    border: 1px solid #888888;
}

.mono-btn-active {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #ffffff;
    font-weight: bold;
    padding: 4px 10px;
    font-size: 12px;
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
        self.header_ev.set_above_child(True)
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
        self.set_size_request(self.tile_width, self.tile_height)

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
                if lx >= self.tile_width - 18 or ly >= self.tile_height - 24:
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
    def __init__(self, start_hidden=False):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.win.set_name("overlay-win")
        self.win.set_title("Command Center")

        screen = self.win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.win.set_visual(visual)

        GtkLayerShell.init_for_window(self.win)
        GtkLayerShell.set_namespace(self.win, "command-center")
        GtkLayerShell.set_layer(self.win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_exclusive_zone(self.win, -1)
        GtkLayerShell.set_keyboard_mode(self.win, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        for edge in (
            GtkLayerShell.Edge.TOP,
            GtkLayerShell.Edge.BOTTOM,
            GtkLayerShell.Edge.LEFT,
            GtkLayerShell.Edge.RIGHT,
        ):
            GtkLayerShell.set_anchor(self.win, edge, True)

        self.screen_w, self.screen_h = self.detect_focused_monitor_size()

        self.dragging_tile = None
        self.drag_offset = (0, 0)
        self.resizing_tile = None
        self.resize_start_mouse = (0, 0)
        self.resize_start_size = (0, 0)
        self.is_visible = not start_hidden

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
        self.win.add(self.bg_ev)

        self.fixed = Gtk.Fixed()
        self.fixed.connect("draw", self.on_fixed_draw)
        self.bg_ev.add(self.fixed)

        self.focused_tile_idx = 0
        self.tile_order = ["audio", "screenshots", "wallpaper", "bluetooth"]
        self.z_order = list(self.tile_order)
        self.tiles = {}
        self.left_ev = None
        self.right_ev = None
        self.info_popup = None

        self.audio_items = []
        self.audio_sel = 0

        self.screenshots = []
        self.shot_sel = 0

        self.wall_monitors = ["DP-1", "HDMI-A-1", "ALL"]
        self.wall_mon_idx = 0
        self.wallpapers = []
        self.wall_sel = 0

        self.bt_powered = True
        self.bt_scanning = False
        self.bt_devices = []
        self.bt_sel = 0

        self.build_tiles()
        self.build_hud()
        self.load_layout()
        self.update_focus_visuals()

        self.win.connect("key-press-event", self.on_key_press)
        self.win.connect("delete-event", lambda *_: self.hide_overlay() or True)

        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGUSR1, self.toggle_visibility)
        GLib.idle_add(self.refresh_all_data)
        GLib.timeout_add(2000, self.periodic_tick)

    def refresh_all_data(self):
        self.refresh_audio()
        self.refresh_screenshots()
        self.refresh_wallpapers()
        self.refresh_bluetooth()
        return False

    def show_overlay(self):
        self.is_visible = True
        self.win.show_all()
        self.info_popup.hide()
        self.update_focus_visuals()
        GLib.idle_add(self.refresh_audio)
        GLib.idle_add(self.refresh_screenshots)
        GLib.idle_add(self.refresh_bluetooth)

    def hide_overlay(self):
        self.is_visible = False
        self.dragging_tile = None
        self.resizing_tile = None
        self.info_popup.hide()
        self.win.hide()

    def toggle_visibility(self):
        if self.is_visible:
            self.hide_overlay()
        else:
            self.show_overlay()
        return True

    def start_tile_drag(self, tile: DraggableTile, off_x: int, off_y: int):
        self.resizing_tile = None
        self.dragging_tile = tile
        self.drag_offset = (off_x, off_y)

    def move_tile_drag(self, canvas_x: int, canvas_y: int):
        tile = self.dragging_tile
        if not tile:
            return
        nx = max(10, min(self.screen_w - tile.tile_width - 10, canvas_x - self.drag_offset[0]))
        ny = max(64, min(self.screen_h - tile.tile_height - 10, canvas_y - self.drag_offset[1]))
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
                    return int(m.get("width", 3440)), int(m.get("height", 1440))
        except Exception:
            pass
        return 3440, 1440

    def default_positions(self):
        if self.screen_w >= 2000:
            total_w = 430 + 470 + 480 + 440 + 72
            start_x = max(24, (self.screen_w - total_w) // 2)
            top_y = max(84, (self.screen_h - 650) // 2)
            return {
                "audio": (start_x, top_y, 430, 650),
                "screenshots": (start_x + 454, top_y, 470, 650),
                "wallpaper": (start_x + 948, top_y, 480, 650),
                "bluetooth": (start_x + 1452, top_y, 440, 650),
            }
        return {
            "audio": (40, 80, 430, 650),
            "screenshots": (500, 80, 470, 650),
            "wallpaper": (980, 80, 480, 650),
            "bluetooth": (1460, 80, 440, 650),
        }

    def load_layout(self):
        defaults = self.default_positions()
        saved = {}
        if LAYOUT_FILE.exists():
            try:
                saved = json.loads(LAYOUT_FILE.read_text())
            except Exception:
                saved = {}
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

    def save_layout(self):
        data = {
            tid: [tile.x, tile.y, tile.tile_width, tile.tile_height]
            for tid, tile in self.tiles.items()
        }
        try:
            LAYOUT_FILE.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def reset_layout(self):
        if LAYOUT_FILE.exists():
            LAYOUT_FILE.unlink(missing_ok=True)
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

        self.status_lbl = Gtk.Label(label="READY")
        self.status_lbl.get_style_context().add_class("hud-status")
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
            "• TAB / 1 / 2 / 3 / 4: Switch active tile",
            "• ↑/↓ or J/K         : Select item in tile",
            "• ←/→ or H/L         : Volume -/+5% or Monitor",
            "• ENTER              : Apply / Copy / Connect",
            "• M (Tile 01)        : Toggle audio mute",
            "• O / DEL (Tile 02)  : Open / Delete screenshot",
            "• P / S (Tile 04)    : BT Power ON/OFF / Scan",
            "• R                  : Reset tile positions & sizes",
            "• ESC / Click empty  : Close Command Center",
        ]
        for ln in lines:
            l = Gtk.Label(label=ln)
            l.get_style_context().add_class("info-text")
            l.set_xalign(0)
            pbox.pack_start(l, False, False, 0)

        self.fixed.put(self.info_popup, self.screen_w - 460, 66)

    def on_info_hover_enter(self, *_):
        self.info_popup.show_all()
        return False

    def on_info_hover_leave(self, *_):
        self.info_popup.hide()
        return False

    def set_status(self, text: str):
        self.status_lbl.set_text(text)

    def build_tiles(self):
        pos = self.default_positions()

        # 1. AUDIO TILE
        ax, ay, aw, ah = pos["audio"]
        t_audio = DraggableTile(self, "audio", "01 // AUDIO MIXER", aw, ah, ax, ay)
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
            self, "screenshots", "02 // RECENT SCREENSHOTS", sw, sh, sx, sy
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
            self, "wallpaper", "03 // QUICK WALLPAPER", ww, wh, wx, wy
        )
        mon_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        mon_lbl = Gtk.Label(label="TARGET:")
        mon_lbl.get_style_context().add_class("row-title")
        mon_bar.pack_start(mon_lbl, False, False, 0)

        self.mon_btns = []
        for idx, mname in enumerate(["DP-1 (21:9)", "HDMI-A-1 (16:9)", "BOTH"]):
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
            self, "bluetooth", "04 // BLUETOOTH", bw, bh, bx, by
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

    def refresh_audio(self):
        self.audio_items = self.query_audio_state()
        if self.audio_sel >= len(self.audio_items):
            self.audio_sel = max(0, len(self.audio_items) - 1)

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
        self.screenshots = [p for _, p in shots[:15]]
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
        ref = "DP-1" if mon == "ALL" else mon
        sf = HOME / f".config/hypr/.wallpaper_{ref}"
        if sf.exists():
            return sf.read_text().strip()
        return ""

    def select_wall_monitor(self, idx):
        self.focus_tile("wallpaper")
        self.wall_mon_idx = idx % len(self.wall_monitors)
        self.refresh_wallpapers()

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
        self.wallpapers = (uw + fhd) if target_mon in ("DP-1", "ALL") else (fhd + uw)

        if self.wall_sel >= len(self.wallpapers):
            self.wall_sel = max(0, len(self.wallpapers) - 1)

        for child in self.wall_list_box.get_children():
            self.wall_list_box.remove(child)

        for idx, wpath in enumerate(self.wallpapers):
            ev = Gtk.EventBox()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.get_style_context().add_class(
                "item-row-selected" if idx == self.wall_sel else "item-row"
            )
            ev.add(row)

            tfile = THUMB_DIR / f"{wpath.name}.png"
            if tfile.exists():
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(tfile), 120, 68, True)
                    img = Gtk.Image.new_from_pixbuf(pb)
                    img.get_style_context().add_class("preview-box")
                    row.pack_start(img, False, False, 0)
                except Exception:
                    pass

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            is_act = str(wpath) == active_wp
            act_str = "[ACTIVE] " if is_act else ""
            clean_name = wpath.stem.removeprefix("uw-")
            lbl = Gtk.Label(label=f"{act_str}{clean_name}")
            lbl.get_style_context().add_class("row-title")
            lbl.set_xalign(0)
            vbox.pack_start(lbl, False, False, 0)

            ratio = "21:9 (3440x1440)" if wpath.name.startswith("uw-") else "16:9 (1920x1080)"
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

    def on_wall_row_click(self, _widget, _event, idx):
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

    # ---------------- FOCUS & KEYBOARD NAVIGATION ----------------
    def on_fixed_draw(self, container, cr):
        for tid in self.z_order:
            tile = self.tiles.get(tid)
            if tile and tile.get_visible():
                container.propagate_draw(tile, cr)
        for hud_w in (self.left_ev, self.right_ev, self.info_popup):
            if hud_w and hud_w.get_visible():
                container.propagate_draw(hud_w, cr)
        return True

    def focus_tile(self, tile_id: str):
        if tile_id in self.tile_order:
            self.focused_tile_idx = self.tile_order.index(tile_id)
            self.update_focus_visuals()

    def update_focus_visuals(self):
        active_id = self.tile_order[self.focused_tile_idx]
        if active_id in self.z_order:
            self.z_order.remove(active_id)
        self.z_order.append(active_id)

        for tid in self.z_order:
            tile = self.tiles[tid]
            tile.set_focused_style(tid == active_id)
            win = tile.get_window()
            if win:
                win.raise_()

        for hud_w in (self.left_ev, self.right_ev, self.info_popup):
            if hud_w:
                win = hud_w.get_window()
                if win:
                    win.raise_()

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
        new_items = self.query_audio_state()
        if len(new_items) != len(self.audio_items):
            self.refresh_audio()
        return True

    def on_key_press(self, _widget, event):
        key = Gdk.keyval_name(event.keyval)
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)

        if key in ("Escape", "g", "G") and (
            key == "Escape" or (event.state & Gdk.ModifierType.SUPER_MASK)
        ):
            self.hide_overlay()
            return True

        active_tile_id = self.tile_order[self.focused_tile_idx]
        active_tile_obj = self.tiles[active_tile_id]

        # Keyboard Resize: Ctrl + Arrows / HJKL
        if ctrl and key in ("Right", "l", "L", "Left", "h", "H", "Down", "j", "J", "Up", "k", "K"):
            dw = 30 if key in ("Right", "l", "L") else (-30 if key in ("Left", "h", "H") else 0)
            dh = 30 if key in ("Down", "j", "J") else (-30 if key in ("Up", "k", "K") else 0)
            active_tile_obj.update_size_request(
                active_tile_obj.tile_width + dw, active_tile_obj.tile_height + dh
            )
            self.save_layout()
            if active_tile_id == "screenshots":
                self.rebuild_screenshot_ui()
            return True

        if key == "Tab":
            self.focused_tile_idx = (self.focused_tile_idx + 1) % len(self.tile_order)
            self.update_focus_visuals()
            return True
        if key == "ISO_Left_Tab":
            self.focused_tile_idx = (self.focused_tile_idx - 1) % len(self.tile_order)
            self.update_focus_visuals()
            return True
        if key in ("1", "2", "3", "4"):
            self.focused_tile_idx = int(key) - 1
            self.update_focus_visuals()
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

        return False


def main():
    daemon_flag = "--daemon" in sys.argv
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if not daemon_flag:
                os.kill(old_pid, signal.SIGUSR1)
            sys.exit(0)
        except Exception:
            PID_FILE.unlink(missing_ok=True)

    PID_FILE.write_text(str(os.getpid()))
    try:
        app = CommandCenterApp(start_hidden=daemon_flag)
        if not daemon_flag:
            app.show_overlay()
        Gtk.main()
    finally:
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
