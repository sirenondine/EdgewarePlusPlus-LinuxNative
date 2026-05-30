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

# The companion's on-screen presence: a small persistent layer-shell window
# (avatar + speech bubble) anchored to a screen corner. One instance is reused
# for the whole session; it hides when idle and reappears for each utterance.
#
# begin()/append()/finish() are the engine-facing API and are thread-safe — the
# engine calls them from its worker thread; each marshals onto the GTK main
# thread via GLib.idle_add. Keep all actual widget work in the _impl methods.

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

_CSS_LOADED = False


def _ensure_css() -> None:
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    from gi.repository import Gdk
    css = Gtk.CssProvider()
    css.load_from_string("""
        .companion-bg {
            background: rgba(0,0,0,0.82);
            border: 1px solid rgba(255,255,255,0.45);
            border-radius: 14px;
            padding: 12px;
        }
        .companion-name { color: #ff9ed8; font-weight: bold; text-shadow: 0 0 3px black; }
        .companion-bubble { color: white; text-shadow: 0 0 4px black; }
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

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.add_css_class("companion-bg")

        avatar_path = self._resolve_avatar(pack, persona)
        if avatar_path:
            avatar = Gtk.Picture.new_for_filename(str(avatar_path))
            avatar.set_size_request(96, 96)
            avatar.set_content_fit(Gtk.ContentFit.COVER)
            avatar.add_css_class("companion-avatar")
            box.append(avatar)

        text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name = Gtk.Label(label=persona.name, halign=Gtk.Align.START)
        name.add_css_class("companion-name")
        self._bubble = Gtk.Label(label="", wrap=True, halign=Gtk.Align.START, xalign=0.0)
        self._bubble.set_max_width_chars(34)
        self._bubble.add_css_class("companion-bubble")
        text_col.append(name)
        text_col.append(self._bubble)
        box.append(text_col)

        self.set_child(box)

        if LayerShell.is_supported():
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_namespace(self, "edgeware-companion")
            LayerShell.set_anchor(self, LayerShell.Edge.BOTTOM, True)
            LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)
            LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, 28)
            LayerShell.set_margin(self, LayerShell.Edge.RIGHT, 28)

        self.set_visible(False)

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
        self.set_visible(False)
        self._hide_id = None
        return False
