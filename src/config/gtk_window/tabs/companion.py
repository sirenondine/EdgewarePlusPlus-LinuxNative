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

import threading

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from config.gtk_window.widgets import AdwComboRow, AdwEntryRow, AdwSliderRow, AdwSwitchRow
from config.vars import Vars
from features.companion import llm

COMPANION_TEXT = (
    "An optional AI companion that reacts to you on screen. Bring your own "
    "inference: a local Ollama server keeps everything on your machine, any "
    "OpenAI-compatible endpoint works too, or the scripted mode needs no AI at "
    "all. Choose a model and use Test to check it responds."
)
BACKENDS = {
    "ollama": "Ollama (local)",
    "openai": "OpenAI-compatible",
    "scripted": "Scripted (no AI)",
}
PRIVACY_TEXT = (
    "Window awareness feeds the name of the app you are focused on to the "
    "companion. With a cloud backend, that — and the companion's prompts — "
    "leave your machine. Keep it on a local backend to stay private."
)


class CompanionTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        self._vars = vars

        group = Adw.PreferencesGroup(title="AI Companion", description=COMPANION_TEXT)
        self.add(group)
        group.add(AdwSwitchRow("Enable Companion", vars.companion_enabled))
        group.add(AdwComboRow("Backend", vars.companion_backend, BACKENDS))
        group.add(AdwEntryRow("Server URL", vars.companion_base_url))
        group.add(AdwEntryRow("Model", vars.companion_model))
        group.add(AdwEntryRow("API key", vars.companion_api_key, password=True))

        behaviour = Adw.PreferencesGroup(title="Behaviour")
        self.add(behaviour)
        behaviour.add(AdwSliderRow("Idle Chatter Chance", vars.companion_chatter_chance, 0, 100))
        behaviour.add(AdwSliderRow("Reaction Chance", vars.companion_react_chance, 0, 100,
                                   subtitle="How often the companion reacts to popups and denials."))
        behaviour.add(AdwSwitchRow("Greet on Start", vars.companion_greet_on_start))
        behaviour.add(AdwSwitchRow(
            "Window Awareness", vars.companion_window_awareness, subtitle=PRIVACY_TEXT))

        # ---- Test --------------------------------------------------------
        test_group = Adw.PreferencesGroup(
            title="Test", description="Ask the configured backend to say hello.")
        self.add(test_group)
        self._test_btn = Gtk.Button(label="Test")
        self._test_btn.add_css_class("suggested-action")
        self._test_btn.connect("clicked", self._on_test)
        self._spinner = Gtk.Spinner()
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(self._spinner)
        head.append(self._test_btn)
        test_group.set_header_suffix(head)

        self._reply = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self._reply.add_css_class("dim-label")
        self._reply.set_margin_top(4)
        self._reply.set_margin_bottom(4)
        test_group.add(self._reply)

    def _on_test(self, _btn: Gtk.Button) -> None:
        backend = self._vars.companion_backend.get() or "scripted"
        url = self._vars.companion_base_url.get() or ""
        model = self._vars.companion_model.get() or ""
        key = self._vars.companion_api_key.get() or ""
        self._reply.set_text("")
        self._test_btn.set_sensitive(False)
        self._spinner.start()
        threading.Thread(target=self._test_worker, args=(backend, url, model, key), daemon=True).start()

    def _test_worker(self, backend: str, url: str, model: str, key: str) -> None:
        client = llm.make_backend(
            backend, base_url=url, model=model, api_key=(key or None),
            scripted_corpus=["Hello! (scripted mode — no AI backend in use.)"])
        messages = [
            {"role": "system", "content": "You are a brief, friendly companion. Reply in one short sentence."},
            {"role": "user", "content": "Say hello."},
        ]
        acc = {"text": ""}

        def tok(t: str) -> None:
            acc["text"] += t
            GLib.idle_add(self._reply.set_text, acc["text"])

        def done(_full: str) -> None:
            GLib.idle_add(self._finish, acc["text"] or "(no response)")

        def err(e: Exception) -> None:
            GLib.idle_add(self._finish, f"Error: {e}")

        client.stream(messages, tok, done, err)

    def _finish(self, text: str) -> bool:
        self._spinner.stop()
        self._test_btn.set_sensitive(True)
        self._reply.set_text(text)
        return False
