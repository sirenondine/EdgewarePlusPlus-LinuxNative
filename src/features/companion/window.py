# Copyright (C) 2025 Araten & Marigold
#
# This file is part of Edgeware++.
#
# Edgeware++ is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Edgeware++ is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Edgeware++.  If not, see <https://www.gnu.org/licenses/>.

# The companion's on-screen presence: a small layer-shell window anchored to a
# screen corner, showing an animated sprite (codex-pet-share format, see
# sprite.py) or a static avatar, plus a speech bubble.
#
# With a spritesheet the window behaves like a desktop pet: always visible,
# idling, switching to a "talk" animation while speaking. With only a static
# avatar it is ephemeral: it appears to speak and hides when idle.
#
# begin()/append()/finish() are the engine-facing API and are thread-safe — the
# engine calls them from its worker thread; each marshals onto the GTK main
# thread via GLib.idle_add. Keep all widget work in the _impl methods.

import logging
import random

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

import utils

_FOLLOW_SIZE = (420, 260)   # approx companion footprint, for keeping it on-screen
_ROAM_STEP_MS = 30          # ms between roam steps
_ROAM_SPEED = 8             # px per step
_ROAM_DWELL_MS = (6000, 14000)  # pause range between wanders

from features.companion import sprite

_CSS_LOADED = False


def _ensure_css() -> None:
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    from gi.repository import Gdk
    css = Gtk.CssProvider()
    # Follow the active GTK theme (light/dark + accent) like the gamification
    # HUD, so the companion bubble reads as native chrome.
    css.load_from_string("""
        window.companion-window { background: transparent; }
        .companion-bg {
            background-color: alpha(@theme_bg_color, 0.94);
            color: @theme_fg_color;
            border: 1px solid @borders;
            border-radius: 16px;
            padding: 16px 18px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.35);
        }
        .companion-name { color: @theme_selected_bg_color; font-weight: bold; font-size: 1.05em; }
        .companion-bubble { font-size: 1.15em; }
        .companion-avatar { border-radius: 10px; }
    """)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _CSS_LOADED = True


class CompanionWindow(Gtk.Window):
    def __init__(self, settings, pack, persona) -> None:
        super().__init__()
        _ensure_css()
        self.settings = settings
        self.persona = persona
        self._buf = ""
        self._hide_id: int | None = None
        self._thinking_id: int | None = None
        self._thinking = False
        self._input_handler = None  # set_input_handler() -> called with typed chat text

        self.set_decorated(False)
        self.set_resizable(False)
        self.add_css_class("companion-window")  # transparent toplevel; only the rounded box paints

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_valign(Gtk.Align.END)

        # Animated sprite (pet) takes precedence over a static avatar — unless
        # the user explicitly set their own avatar image, which wins over the
        # pack's spritesheet.
        user_avatar = (getattr(settings, "companion_avatar", "") or "").strip()
        self._sprite = None if user_avatar else self._load_sprite(pack, persona)
        if self._sprite:
            box.append(self._sprite)
        else:
            avatar_path = self._resolve_avatar(pack, persona)
            if avatar_path:
                avatar = self._build_avatar(avatar_path)
                if avatar:
                    box.append(avatar)

        self._text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._text_col.add_css_class("companion-bg")  # only the speech bubble paints; the pet floats free
        self._text_col.set_valign(Gtk.Align.END)
        name = Gtk.Label(label=persona.name, halign=Gtk.Align.START)
        name.add_css_class("companion-name")
        self._bubble = Gtk.Label(label="", wrap=True, halign=Gtk.Align.START, xalign=0.0)
        self._bubble.set_width_chars(28)       # roomy minimum so short lines aren't cramped
        self._bubble.set_max_width_chars(52)   # wrap point for long replies
        self._bubble.add_css_class("companion-bubble")
        # Click-to-chat input, hidden until the companion is clicked.
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Say something…")
        self._entry.set_visible(False)
        self._entry.connect("activate", self._on_input_activate)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_entry_key)
        self._entry.add_controller(key)
        self._text_col.append(name)
        self._text_col.append(self._bubble)
        self._text_col.append(self._entry)
        self._text_col.set_visible(False)  # shown only while speaking
        box.append(self._text_col)

        self.set_child(box)

        # Click the companion to talk to it.
        click = Gtk.GestureClick.new()
        click.connect("released", self._on_clicked)
        box.add_controller(click)

        # Position state: when following, the companion roams the screen and
        # migrates to the focused monitor; otherwise it sits bottom-right.
        self._follow = bool(getattr(settings, "companion_follow", False))
        self._mon = None
        self._x = 0
        self._y = 0
        self._roam_id: int | None = None
        self._target = None

        if LayerShell.is_supported():
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_namespace(self, "edgeware-companion")
            # Anchor top-left and position by margins (so we can move freely).
            LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(self, LayerShell.Edge.LEFT, True)
            # Allow keyboard focus on demand so the chat entry can be typed in.
            LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND)
            self._init_position()

        # A pet (sprite) is persistent and idles on screen; an avatar-only
        # companion stays hidden until it speaks.
        if self._sprite:
            self.set_visible(True)
            self.present()
        else:
            self.set_visible(False)

        if self._follow:
            self._schedule_roam(initial=True)

    # ------------------------------------------------------------------
    # Positioning / roaming.
    def _init_position(self) -> None:
        """Start bottom-right of the focused (or a default) monitor."""
        self._mon = utils.focused_monitor() or utils.random_monitor(self.settings)
        w, h = _FOLLOW_SIZE
        self._x = self._mon.x + max(0, self._mon.width - w - 28)
        self._y = self._mon.y + max(0, self._mon.height - h - 28)
        self._apply_position()

    def _apply_position(self) -> None:
        if not LayerShell.is_supported() or not self._mon:
            return
        try:
            gdk_mon = utils.gdk_monitor_for(self._mon)
            if gdk_mon:
                LayerShell.set_monitor(self, gdk_mon)
            LayerShell.set_margin(self, LayerShell.Edge.LEFT, max(0, int(self._x - self._mon.x)))
            LayerShell.set_margin(self, LayerShell.Edge.TOP, max(0, int(self._y - self._mon.y)))
        except Exception as e:
            logging.debug(f"companion reposition failed: {e}")

    def _schedule_roam(self, initial: bool = False) -> None:
        delay = 1500 if initial else random.randint(*_ROAM_DWELL_MS)
        GLib.timeout_add(delay, self._pick_target)

    def _pick_target(self) -> bool:
        # Migrate to whatever monitor the user is now focused on, then wander.
        self._mon = utils.focused_monitor() or self._mon or utils.random_monitor(self.settings)
        w, h = _FOLLOW_SIZE
        tx = self._mon.x + random.randint(0, max(0, self._mon.width - w))
        ty = self._mon.y + random.randint(0, max(0, self._mon.height - h))
        self._target = (tx, ty)
        if self._roam_id is None:
            self._roam_id = GLib.timeout_add(_ROAM_STEP_MS, self._roam_step)
        return False

    def _roam_step(self) -> bool:
        if not self._target:
            self._roam_id = None
            return False
        # Hold still while speaking or being chatted with (bubble visible).
        if self._text_col.get_visible():
            return True
        tx, ty = self._target
        dx, dy = tx - self._x, ty - self._y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= _ROAM_SPEED:
            self._x, self._y = tx, ty
            self._apply_position()
            self._roam_id = None
            self._target = None
            self._schedule_roam()  # arrived; dwell, then wander again
            return False
        self._x += _ROAM_SPEED * dx / dist
        self._y += _ROAM_SPEED * dy / dist
        self._apply_position()
        return True

    def _load_sprite(self, pack, persona):
        path = None
        try:
            if persona.spritesheet:
                p = pack.paths.root / persona.spritesheet
                if p.is_file():
                    path = p
            if path is None:
                for cand in (pack.paths.root / "companion" / "spritesheet.webp",
                             pack.paths.root / "spritesheet.webp"):
                    if cand.is_file():
                        path = cand
                        break
        except Exception:
            return None
        if path is None:
            return None
        sheet = sprite.load_sheet(path)
        return sprite.SpriteWidget(sheet) if sheet else None

    _AVATAR_SIZE = 96  # px; fixed on-screen avatar size

    def _build_avatar(self, path):
        """A fixed-size avatar widget. Loads the image pre-scaled so the
        Picture's natural size is small — otherwise a large source image would
        blow the window up (size_request is only a minimum)."""
        size = self._AVATAR_SIZE
        try:
            import gi as _gi
            _gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import Gdk, GdkPixbuf
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True)
            avatar = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
        except Exception as e:
            logging.debug(f"avatar load failed ({path}): {e}")
            avatar = Gtk.Picture.new_for_filename(str(path))
            avatar.set_can_shrink(True)
        avatar.set_size_request(size, size)
        avatar.set_content_fit(Gtk.ContentFit.CONTAIN)
        avatar.set_halign(Gtk.Align.CENTER)
        avatar.set_valign(Gtk.Align.END)
        avatar.set_hexpand(False)
        avatar.set_vexpand(False)
        avatar.add_css_class("companion-avatar")
        return avatar

    def _resolve_avatar(self, pack, persona):
        from features.companion import resolve_avatar
        return resolve_avatar(self.settings, pack, persona)

    def set_input_handler(self, handler) -> None:
        """handler(text) is called with what the user types into the chat box."""
        self._input_handler = handler

    # ------------------------------------------------------------------
    # Click-to-chat.
    def _on_clicked(self, _gesture, _n, _x, _y) -> None:
        if self._input_handler is None:
            return
        self._cancel_hide()
        self._text_col.set_visible(True)
        self.set_visible(True)
        self.present()
        self._entry.set_visible(True)
        self._entry.grab_focus()

    def _on_entry_key(self, _ctrl, keyval, _code, _mods) -> bool:
        from gi.repository import Gdk
        if keyval == Gdk.KEY_Escape:
            self._entry.set_visible(False)
            return True
        return False

    def _on_input_activate(self, entry: Gtk.Entry) -> None:
        text = entry.get_text().strip()
        entry.set_text("")
        if text and self._input_handler:
            self._input_handler(text)  # reply streams back via begin/append/finish

    # ------------------------------------------------------------------
    # Thinking indicator (pulsing dots while waiting for the first token).
    def _start_thinking(self) -> None:
        self._thinking = True
        state = {"n": 0}

        def tick() -> bool:
            state["n"] = (state["n"] % 3) + 1
            self._bubble.set_text("." * state["n"])
            return True

        tick()
        self._thinking_id = GLib.timeout_add(400, tick)

    def _stop_thinking(self) -> None:
        if self._thinking_id is not None:
            GLib.source_remove(self._thinking_id)
            self._thinking_id = None
        self._thinking = False

    def _cancel_hide(self) -> None:
        if self._hide_id is not None:
            GLib.source_remove(self._hide_id)
            self._hide_id = None

    # ------------------------------------------------------------------
    # Engine-facing, thread-safe API.
    def begin(self) -> None:
        GLib.idle_add(self._begin_impl)

    def append(self, token: str) -> None:
        GLib.idle_add(self._append_impl, token)

    def finish(self, full_text: str) -> None:
        GLib.idle_add(self._finish_impl, full_text)

    # ------------------------------------------------------------------
    def _begin_impl(self) -> bool:
        self._cancel_hide()
        self._buf = ""
        self._text_col.set_visible(True)
        if self._sprite:
            self._sprite.set_state(sprite.TALK_STATE)
        self.set_visible(True)
        self.present()
        self._start_thinking()  # pulse dots until the first token arrives
        return False

    def _append_impl(self, token: str) -> bool:
        if self._thinking:
            self._stop_thinking()
            self._buf = ""
        self._buf += token
        self._bubble.set_text(self._buf)
        return False

    def _finish_impl(self, full_text: str) -> bool:
        self._stop_thinking()
        if full_text:
            self._bubble.set_text(full_text)
        # Auto-hide after a dwell time that scales with reading length.
        dwell = max(4000, min(15000, 1500 + 55 * len(self._bubble.get_text())))
        self._hide_id = GLib.timeout_add(dwell, self._hide_impl)
        return False

    def _hide_impl(self) -> bool:
        self._hide_id = None
        self._text_col.set_visible(False)
        if self._sprite:
            # Pet stays on screen, back to idling.
            self._sprite.set_state(sprite.IDLE_STATE)
        else:
            self.set_visible(False)
        return False
