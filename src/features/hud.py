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

# A small always-on progress HUD: level + XP-to-next bar pinned to a screen
# corner, updated live as XP is earned. Encourages keeping Edgeware running by
# making progress to the next level visible. Click-through so it never gets in
# the way. update() is thread-safe (marshals onto the GTK main thread).

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

_CSS_LOADED = False


def _ensure_css() -> None:
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    css = Gtk.CssProvider()
    # Follow the active GTK theme (light/dark + accent) via its named colors,
    # so the HUD reads as native chrome rather than a hardcoded black box.
    css.load_from_string("""
        window.hud { background: transparent; }
        .hud-box {
            background-color: alpha(@theme_bg_color, 0.94);
            color: @theme_fg_color;
            border: 1px solid @borders;
            border-radius: 12px;
            padding: 8px 12px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.35);
        }
        .hud-level { color: @theme_selected_bg_color; font-weight: bold; }
        .hud-xp { font-size: 0.85em; }
        .hud-box progressbar > trough > progress { min-height: 6px; }
        .hud-box progressbar > trough { min-height: 6px; }
    """)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _CSS_LOADED = True


class ProgressHUD(Gtk.Window):
    def __init__(self, level: int = 0, into: int = 0, span: int = 1) -> None:
        super().__init__()
        _ensure_css()
        self.set_decorated(False)
        self.set_resizable(False)
        self.add_css_class("hud")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.add_css_class("hud-box")
        self._level = Gtk.Label(halign=Gtk.Align.START)
        self._level.add_css_class("hud-level")
        self._bar = Gtk.ProgressBar()
        self._bar.set_size_request(150, -1)
        self._xp = Gtk.Label(halign=Gtk.Align.END)
        self._xp.add_css_class("hud-xp")
        self._xp.add_css_class("dim-label")
        box.append(self._level)
        box.append(self._bar)
        box.append(self._xp)
        self.set_child(box)

        if LayerShell.is_supported():
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_namespace(self, "edgeware-hud")
            LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)
            LayerShell.set_margin(self, LayerShell.Edge.TOP, 24)
            LayerShell.set_margin(self, LayerShell.Edge.RIGHT, 24)

        # Click-through: an empty input region lets clicks pass to whatever is
        # behind the HUD.
        self.connect("realize", self._make_click_through)

        self._apply(level, into, span)
        self.set_visible(True)
        self.present()

    def _make_click_through(self, _w) -> None:
        try:
            surface = self.get_surface()
            if surface:
                surface.set_input_region(self._empty_region())
        except Exception:
            pass

    def _empty_region(self):
        import cairo
        return cairo.Region()

    def update(self, level: int, into: int, span: int) -> None:
        GLib.idle_add(self._apply, level, into, span)

    def _apply(self, level: int, into: int, span: int) -> bool:
        self._level.set_text(f"Level {level}")
        self._bar.set_fraction(into / span if span else 1.0)
        self._xp.set_text(f"{into} / {span} XP")
        return False
