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

import os
import random
import shutil
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk
from gi.repository import Gtk4LayerShell as LayerShell

import utils
from config.settings import Settings
from features.misc import mitosis_popup, open_web
from pack import Pack
from PIL import ImageFilter
from paths import Data
from roll import roll
from state import State

_LAYER_OK = LayerShell.is_supported()
_CSS_LOADED = False


def _ensure_css() -> None:
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    css = Gtk.CssProvider()
    css.load_from_string("""
        .popup-text {
            color: white;
            text-shadow: 0 0 4px black, 0 0 4px black;
            font-weight: bold;
        }
        .popup-close {
            font-weight: bold;
            color: white;
            background: rgba(0,0,0,0.78);
            border: 1px solid rgba(255,255,255,0.55);
            border-radius: 8px;
            padding: 4px 14px;
            text-shadow: 0 0 3px black;
        }
        .popup-close:hover { background: rgba(0,0,0,0.92); }
        .popup-close:active { background: rgba(40,40,40,0.95); }
        .popup-bg { background: rgba(0,0,0,0.85); }
    """)
    from gi.repository import Gdk
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _CSS_LOADED = True


class Popup(Gtk.Window):
    media: Path  # Defined by subclasses
    # Sex-toy vibration event names, set by subclasses (e.g. "image_open").
    vibration_open_event: str | None = None
    vibration_close_event: str | None = None
    # Continuous-mode key (e.g. "image"): if the device has
    # sextoy_<key>_continuous on, vibrate from open until close (stacking with
    # other open popups) instead of the timed open/close pulses.
    vibration_continuous_key: str | None = None

    def __init__(self, settings: Settings, pack: Pack, state: State, on_close: Callable[[], None] | None = None) -> None:
        super().__init__()
        _ensure_css()

        state.popup_number += 1
        state.popups.append(self)

        self.settings = settings
        self.pack = pack
        self.state = state
        self.on_close = on_close

        self.denial = roll(self.settings.denial_chance)
        self.opacity = self.settings.opacity
        self._move_id: int | None = None
        self._timeout_id: int | None = None

        # Geometry defaults; subclasses call compute_geometry to refine
        self.width = 300
        self.height = 300
        self.x = 0
        self.y = 0

        # Overlay stacks media (set by subclass via set_media_widget) with text/buttons
        self._overlay = Gtk.Overlay()
        self.set_child(self._overlay)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_opacity(self.opacity)

        # Layer-shell: float as an overlay on the chosen monitor, positioned by
        # margins. Unavailable on X11 and for sandboxed clients on compositors
        # that restrict it (e.g. niri via the Wayland security-context) — fall
        # back to an ordinary toplevel that the compositor places.
        if _LAYER_OK:
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(self, LayerShell.Edge.LEFT, True)
            LayerShell.set_namespace(self, "edgeware-popup")

        # Record whether Alt was held at click-time (for alt+click blacklist) —
        # capture phase so it fires before the button/buttonless handler.
        self._alt_at_click = False
        alt_capture = Gtk.GestureClick.new()
        alt_capture.set_button(0)
        alt_capture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        alt_capture.connect("pressed", self._record_modifiers)
        self.add_controller(alt_capture)

    def _record_modifiers(self, gesture: Gtk.GestureClick, _n: int, _x: float, _y: float) -> None:
        self._alt_at_click = bool(gesture.get_current_event_state() & Gdk.ModifierType.ALT_MASK)

    def set_media_widget(self, widget: Gtk.Widget) -> None:
        widget.set_size_request(self.width, self.height)
        self._overlay.set_child(widget)

    def _apply_position(self) -> None:
        if not _LAYER_OK:
            self.set_default_size(self.width, self.height)
            return
        gdk_mon = utils.gdk_monitor_for(self.monitor)
        if gdk_mon:
            LayerShell.set_monitor(self, gdk_mon)
        # Layer-shell margins are monitor-local
        local_x = self.x - self.monitor.x
        local_y = self.y - self.monitor.y
        LayerShell.set_margin(self, LayerShell.Edge.LEFT, max(0, local_x))
        LayerShell.set_margin(self, LayerShell.Edge.TOP, max(0, local_y))
        self.set_default_size(self.width, self.height)

    def init_finish(self) -> None:
        self._apply_position()
        self.try_denial_text()
        self.try_caption()
        self.try_corruption_dev()
        self.try_button()
        self.try_multi_click()
        self.present()
        self.try_move()
        self.try_timeout()
        self.try_pump_scare()
        # Sex toy: start continuous contribution first (so the timed pulse below
        # is auto-suppressed on devices already held continuous), then the
        # timed open pulse (which fires only on devices in timed mode).
        if self.vibration_continuous_key:
            from features.vibration_mixin import start_continuous
            self._vib_token = f"{self.vibration_continuous_key}:{id(self)}"
            start_continuous(
                self.settings, self.state.sextoy, self._vib_token,
                f"sextoy_{self.vibration_continuous_key}_continuous",
                f"sextoy_{self.vibration_continuous_key}_continuous_force")
        if self.vibration_open_event:
            from features.vibration_mixin import vibrate_event
            vibrate_event(self.vibration_open_event, self.settings, self.state.sextoy)

    def compute_geometry(self, source_width: int, source_height: int) -> None:
        # Monitor may be pre-selected on the main thread (e.g. ImagePopup, which
        # then sizes on a worker thread where GDK/screeninfo are unsafe).
        if getattr(self, "monitor", None) is None:
            self.monitor = utils.random_monitor(self.settings)

        source_size = max(source_width, source_height) / min(self.monitor.width, self.monitor.height)
        target_size = (random.randint(30, 70) if not self.settings.lowkey_mode else random.randint(20, 50)) / 100
        scale = target_size / source_size

        self.width = int(source_width * scale)
        self.height = int(source_height * scale)

        if self.settings.lowkey_mode:
            corner = self.settings.lowkey_corner
            if corner == 4:  # Random corner
                corner = random.randint(0, 3)

            right = corner == 0 or corner == 3  # Top right or bottom right
            bottom = corner == 2 or corner == 3  # Bottom left or bottom right
            self.x = self.monitor.x + (self.monitor.width - self.width if right else 0)
            self.y = self.monitor.y + (self.monitor.height - self.height if bottom else 0)
        else:
            self.x = self.monitor.x + random.randint(0, max(0, self.monitor.width - self.width))
            self.y = self.monitor.y + random.randint(0, max(0, self.monitor.height - self.height))

    def try_denial_filter(self) -> ImageFilter.Filter | str:
        """Pick a denial filter for still images. Video denial uses a GStreamer
        gaussianblur instead (see gtk_media.VideoController)."""
        if not self.denial:
            return ""

        image_filters = [ImageFilter.GaussianBlur(5), ImageFilter.GaussianBlur(10), ImageFilter.GaussianBlur(20), "resizeblur"]
        weights = [1, 1, 1, 3]
        return random.choices(image_filters, weights=weights)[0]

    def _add_text(self, text: str, halign: Gtk.Align, valign: Gtk.Align) -> None:
        label = Gtk.Label(label=text, wrap=True)
        label.add_css_class("popup-text")
        label.set_halign(halign)
        label.set_valign(valign)
        label.set_max_width_chars(40)
        label.set_margin_start(6)
        label.set_margin_end(6)
        label.set_margin_top(6)
        label.set_margin_bottom(6)
        self._overlay.add_overlay(label)

    def try_denial_text(self) -> None:
        if self.denial:
            self._add_text(self.pack.random_denial(), Gtk.Align.CENTER, Gtk.Align.CENTER)

    def try_caption(self) -> None:
        caption = self.pack.random_caption(self.media)
        if self.settings.captions_in_popups and caption:
            self._add_text(caption, Gtk.Align.START, Gtk.Align.START)
            from features.vibration_mixin import vibrate_event
            vibrate_event("caption", self.settings, self.state.sextoy)

    def try_corruption_dev(self) -> None:
        if self.settings.corruption_dev_mode:
            mood = self.pack.index.media_moods.get(self.media.name, None)
            levels = [self.pack.corruption_levels.index(level) + 1
                      for level in self.pack.corruption_levels if mood in level.moods]
            text = f"Popup mood: {mood}\nValid Levels: {levels}\nCurrent Level: {self.state.corruption_level}"
            self._add_text(text, Gtk.Align.START, Gtk.Align.CENTER)

    def try_button(self) -> None:
        if self.settings.buttonless:
            gesture = Gtk.GestureClick.new()
            gesture.connect("released", lambda *_: self.click())
            self._overlay.add_controller(gesture)
        else:
            button = Gtk.Button(label=self.pack.index.default.popup_close)
            button.add_css_class("popup-close")
            button.set_halign(Gtk.Align.END)
            button.set_valign(Gtk.Align.END)
            button.set_margin_end(10)
            button.set_margin_bottom(10)
            button.connect("clicked", lambda _: self.click())
            self._overlay.add_overlay(button)

    def try_move(self) -> None:
        if not _LAYER_OK:
            return  # can't reposition an ordinary toplevel on Wayland
        if not roll(self.settings.moving_chance):
            return

        speed = self.settings.moving_speed
        sx = sy = 0
        while sx == 0 and sy == 0:
            sx = random.randint(-speed, speed)
            sy = random.randint(-speed, speed)
        self._speed = [sx, sy]

        def move() -> bool:
            self.x += self._speed[0]
            self.y += self._speed[1]

            if self.x <= self.monitor.x or self.x + self.width >= self.monitor.x + self.monitor.width:
                self._speed[0] = -self._speed[0]
            if self.y <= self.monitor.y or self.y + self.height >= self.monitor.y + self.monitor.height:
                self._speed[1] = -self._speed[1]

            local_x = max(0, self.x - self.monitor.x)
            local_y = max(0, self.y - self.monitor.y)
            LayerShell.set_margin(self, LayerShell.Edge.LEFT, local_x)
            LayerShell.set_margin(self, LayerShell.Edge.TOP, local_y)
            return GLib.SOURCE_CONTINUE

        self._move_id = GLib.timeout_add(10, move)

    def try_multi_click(self) -> None:
        self.clicks_to_close = self.pack.random_clicks_to_close(self.media) if self.settings.multi_click_popups else 1

    def try_timeout(self) -> None:
        if not (self.settings.timeout_enabled and not self.state.pump_scare):
            return

        def begin_fade() -> bool:
            def fade() -> bool:
                self.opacity -= 0.01
                if self.opacity <= 0:
                    self.close()
                    return GLib.SOURCE_REMOVE
                self.set_opacity(self.opacity)
                return GLib.SOURCE_CONTINUE
            GLib.timeout_add(15, fade)
            return GLib.SOURCE_REMOVE

        self._timeout_id = GLib.timeout_add(self.settings.timeout, begin_fade)

    def try_pump_scare(self) -> None:
        if self.state.pump_scare:
            GLib.timeout_add(2500, lambda: (self.close(), GLib.SOURCE_REMOVE)[1])

    def try_web_open(self) -> None:
        if self.settings.web_on_popup_close and roll((100 - self.settings.web_chance) / 2):
            open_web(self.pack)

    def try_mitosis(self) -> None:
        if self.settings.mitosis_mode and not self.settings.lowkey_mode:
            for _ in range(self.settings.mitosis_strength):
                mitosis_popup(self.settings, self.pack, self.state)

    def click(self) -> None:
        self.clicks_to_close -= 1
        if self.clicks_to_close <= 0:
            if self._alt_at_click or self.state.alt_held:
                self.blacklist_media()
            self.close()
            self.try_mitosis()

    def blacklist_media(self) -> None:
        filename = os.path.basename(self.media).split("/")[-1]
        path_blacklist = Data.BLACKLIST / "".join(self.pack.info.name.split())
        if not os.path.exists(path_blacklist):
            os.makedirs(path_blacklist)
        shutil.move(self.media, path_blacklist)
        from features.misc import notify
        notify(self.pack.info.name, f"{filename} has been successfully sent to blacklist", icon=self.pack.icon)

    def close(self) -> None:
        # Engagement escalation: closing a popup counts as interaction.
        if self.settings.escalation:
            from features import escalation
            escalation.record_interaction()
        # Fire the timed close pulse first (suppressed on continuous devices
        # while the contribution is still held), then drop the contribution.
        if self.vibration_close_event:
            from features.vibration_mixin import vibrate_event
            vibrate_event(self.vibration_close_event, self.settings, self.state.sextoy)
        if self.vibration_continuous_key and getattr(self, "_vib_token", None):
            from features.vibration_mixin import stop_continuous
            stop_continuous(self._vib_token, self.state.sextoy)
        if self._move_id is not None:
            utils.after_cancel(self._move_id)
            self._move_id = None
        self.state.popup_number -= 1
        if self in self.state.popups:
            self.state.popups.remove(self)
        self.try_web_open()
        self.destroy()
        if self.on_close:
            self.on_close()
