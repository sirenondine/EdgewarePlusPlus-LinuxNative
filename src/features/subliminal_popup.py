# Copyright (C) 2024 Araten & Marigold
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

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

import utils
from config.settings import Settings
from pack import Pack


class SubliminalPopup(Gtk.Window):
    def __init__(self, settings: Settings, pack: Pack, state=None, subliminal: str | None = None) -> None:
        self.subliminal = subliminal or pack.random_subliminal()
        if not self.should_init():
            return
        if state is not None and self.subliminal:
            try:
                state.recent_text.append(self.subliminal)
            except Exception:
                pass
        super().__init__()

        self.set_decorated(False)
        self.set_opacity(settings.subliminal_opacity)

        monitor = utils.random_monitor(settings)
        font_px = min(monitor.width, monitor.height) // 10

        label = Gtk.Label(label=self.subliminal, wrap=True)
        label.set_max_width_chars(30)
        label.set_justify(Gtk.Justification.CENTER)
        label.add_css_class("subliminal-text")
        self.set_child(label)

        provider = Gtk.CssProvider()
        provider.load_from_string(
            ".subliminal-text { color: white; text-shadow: 0 0 6px black; font-size: %dpx; font-weight: bold; }" % font_px
        )
        label.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        if LayerShell.is_supported():
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_namespace(self, "edgeware-subliminal")
            gdk_mon = utils.gdk_monitor_for(monitor)
            if gdk_mon:
                LayerShell.set_monitor(self, gdk_mon)
            # No edge anchors → compositor centers the window on the monitor

        self.present()
        GLib.timeout_add(settings.subliminal_timeout, lambda: (self.destroy(), GLib.SOURCE_REMOVE)[1])

    def should_init(self) -> bool:
        return self.subliminal
