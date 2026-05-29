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

from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("WebKit", "6.0")
from gi.repository import Gtk, WebKit

from config.gtk_window.utils import config
from paths import Assets


def open_tutorial(parent: Gtk.Window) -> None:
    window = Gtk.Window(title="Edgeware++ Tutorial")
    window.set_default_size(740, 900)
    window.set_transient_for(parent)
    window.set_modal(True)

    notebook = Gtk.Notebook()
    window.set_child(notebook)

    pages = [
        ("Intro/About", Assets.TUTORIAL_INTRO),
        ("Quick Start", Assets.TUTORIAL_QUICKGUIDE),
        ("Getting Started", Assets.TUTORIAL_GETSTARTED),
        ("Settings 101", Assets.TUTORIAL_BASICSETTINGS),
    ]

    for title, html_file in pages:
        webview = WebKit.WebView()
        webview.load_html(_read_html(html_file), None)
        notebook.append_page(webview, Gtk.Label(label=title))

    # Hibernate types tab (plain text)
    hib_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_child(hib_box)
    notebook.append_page(scrolled, Gtk.Label(label="Hibernate Types"))

    hib_text = (
        "Original: Spawns a barrage of popups instantly.\n\n"
        "Spaced: Runs Edgeware normally over a brief period.\n\n"
        "Glitch: Creates popups at random intervals.\n\n"
        "Ramp: Popup frequency increases over time.\n\n"
        "Pump-Scare: Popup with audio appears briefly.\n\n"
        "Chaos: Randomly selects any other mode."
    )
    hib_label = Gtk.Label(label=hib_text, wrap=True)
    hib_label.set_margin_start(10)
    hib_label.set_margin_end(10)
    hib_label.set_margin_top(10)
    hib_label.set_margin_bottom(10)
    scrolled.set_child(hib_label)

    window.present()


def _read_html(path: Path) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return f"<html><body><p>Could not load {path}</p></body></html>"
