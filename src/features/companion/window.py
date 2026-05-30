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

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

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
            border-radius: 14px;
            padding: 12px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.35);
        }
        .companion-name { color: @theme_selected_bg_color; font-weight: bold; }
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

        self.set_decorated(False)
        self.set_resizable(False)
        self.add_css_class("companion-window")  # transparent toplevel; only the rounded box paints

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_valign(Gtk.Align.END)

        # Animated sprite (pet) takes precedence over a static avatar.
        self._sprite = self._load_sprite(pack, persona)
        if self._sprite:
            box.append(self._sprite)
        else:
            avatar_path = self._resolve_avatar(pack, persona)
            if avatar_path:
                avatar = Gtk.Picture.new_for_filename(str(avatar_path))
                avatar.set_size_request(96, 96)
                avatar.set_content_fit(Gtk.ContentFit.COVER)
                avatar.add_css_class("companion-avatar")
                box.append(avatar)

        self._text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._text_col.add_css_class("companion-bg")  # only the speech bubble paints; the pet floats free
        self._text_col.set_valign(Gtk.Align.END)
        name = Gtk.Label(label=persona.name, halign=Gtk.Align.START)
        name.add_css_class("companion-name")
        self._bubble = Gtk.Label(label="", wrap=True, halign=Gtk.Align.START, xalign=0.0)
        self._bubble.set_max_width_chars(34)
        self._bubble.add_css_class("companion-bubble")
        self._text_col.append(name)
        self._text_col.append(self._bubble)
        self._text_col.set_visible(False)  # shown only while speaking
        box.append(self._text_col)

        self.set_child(box)

        if LayerShell.is_supported():
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_namespace(self, "edgeware-companion")
            LayerShell.set_anchor(self, LayerShell.Edge.BOTTOM, True)
            LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)
            LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, 28)
            LayerShell.set_margin(self, LayerShell.Edge.RIGHT, 28)

        # A pet (sprite) is persistent and idles on screen; an avatar-only
        # companion stays hidden until it speaks.
        if self._sprite:
            self.set_visible(True)
            self.present()
        else:
            self.set_visible(False)

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

    def _resolve_avatar(self, pack, persona):
        try:
            if persona.avatar:
                p = pack.paths.root / persona.avatar
                if p.is_file():
                    return p
            return pack.icon
        except Exception:
            return None

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
        if self._hide_id is not None:
            GLib.source_remove(self._hide_id)
            self._hide_id = None
        self._buf = ""
        self._bubble.set_text("")
        self._text_col.set_visible(True)
        if self._sprite:
            self._sprite.set_state(sprite.TALK_STATE)
        self.set_visible(True)
        self.present()
        return False

    def _append_impl(self, token: str) -> bool:
        self._buf += token
        self._bubble.set_text(self._buf)
        return False

    def _finish_impl(self, full_text: str) -> bool:
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
