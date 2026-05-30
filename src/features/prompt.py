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

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk
from gi.repository import Gtk4LayerShell as LayerShell

import utils
from config.settings import Settings
from pack import Pack
from state import State


class Prompt(Gtk.Window):
    def __init__(self, settings: Settings, pack: Pack, state: State, prompt: str | None = None, on_close: Callable[[], None] | None = None) -> None:
        self.prompt = prompt or pack.random_prompt()
        self.state = state
        if not self.should_init():
            return
        super().__init__()

        self.settings = settings
        self.on_close = on_close

        self.set_decorated(False)

        # While a prompt is up, pause new popup spawns so nothing stacks over it
        # (it is the newest layer-shell surface, so it sits above whatever is
        # already on screen). Resumed when the prompt closes.
        import roll
        roll.add_pause_reason("prompt")

        # Size the window to the prompt length: longer text gets a bigger window
        # so the user can actually read what they are typing, capped to the
        # monitor.
        monitor = utils.primary_monitor()
        chars = len(self.prompt or "")
        width = max(monitor.width // 5, min(int(monitor.width * 0.7), 360 + chars * 4))
        height = max(monitor.height // 4, min(int(monitor.height * 0.7), 220 + chars * 2))
        self.set_default_size(width, height)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)
        self.set_child(vbox)

        command = Gtk.Label(label=pack.index.default.prompt_command)
        command.add_css_class("title-2")
        vbox.append(command)

        prompt_label = Gtk.Label(label=self.prompt, wrap=True)
        prompt_label.set_selectable(False)
        vbox.append(prompt_label)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self._input = Gtk.TextView()
        self._input.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scrolled.set_child(self._input)
        vbox.append(scrolled)

        button = Gtk.Button(label=pack.index.default.prompt_submit)
        button.add_css_class("suggested-action")
        button.set_halign(Gtk.Align.END)
        button.connect("clicked", lambda _: self._on_submit())
        vbox.append(button)

        if LayerShell.is_supported():
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_namespace(self, "edgeware-prompt")
            LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)
            gdk_mon = utils.gdk_monitor_for(monitor)
            if gdk_mon:
                LayerShell.set_monitor(self, gdk_mon)

        self.present()

        # Sex-toy: hold a continuous vibration while the prompt is open; stop it
        # whenever the window goes away (submit, panic, or close).
        from features.vibration_mixin import start_continuous, stop_continuous
        self._vib_token = f"prompt:{id(self)}"
        start_continuous(self.settings, self.state.sextoy, self._vib_token,
                         "sextoy_prompt_enabled", "sextoy_prompt_vibration_force")
        self.connect("close-request", lambda _w: (
            stop_continuous(self._vib_token, self.state.sextoy),
            self._resume_popups(), False)[2])

    def _resume_popups(self) -> None:
        import roll
        roll.remove_pause_reason("prompt")

    def _get_text(self) -> str:
        buffer = self._input.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)

    def _on_submit(self) -> None:
        self.submit(self.settings.prompt_max_mistakes, self.prompt, self._get_text())

    def should_init(self) -> bool:
        if not self.state.prompt_active and self.prompt:
            self.state.prompt_active = True
            return True
        return False

    # Checks that the number of mistakes is at most max_mistakes and if so,
    # closes the prompt window. The number of mistakes is computed as the edit
    # (Levenshtein) distance between a and b.
    # https://en.wikipedia.org/wiki/Levenshtein_distance
    def submit(self, max_mistakes: int, a: str, b: str) -> None:
        d = [[j for j in range(0, len(b) + 1)]] + [[i] for i in range(1, len(a) + 1)]

        for j in range(1, len(b) + 1):
            for i in range(1, len(a) + 1):
                d[i].append(
                    min(
                        d[i - 1][j] + 1,
                        d[i][j - 1] + 1,
                        d[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1)
                    )
                )  # fmt: skip

        if d[len(a)][len(b)] <= max_mistakes:
            from features.vibration_mixin import stop_continuous
            stop_continuous(getattr(self, "_vib_token", ""), self.state.sextoy)
            self._resume_popups()
            self.destroy()
            self.state.prompt_active = False
            if self.settings.gamification:
                from features import gamification
                gamification.record("prompt_completed")
            if self.on_close:
                self.on_close()
        elif self.settings.gamification:
            # Too many mistakes: the prompt stays open, but it costs XP.
            from features import gamification
            gamification.record("prompt_failed")
