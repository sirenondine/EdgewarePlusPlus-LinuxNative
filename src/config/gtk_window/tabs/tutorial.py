from pathlib import Path

from gi import require_version

require_version("Gtk", "4.0")
require_version("WebKit", "6.0")
from gi.repository import Gtk, WebKit

from paths import Assets

_tutorial_popover: Gtk.Popover | None = None


def open_tutorial(anchor: Gtk.Widget, parent: Gtk.Window) -> None:
    global _tutorial_popover
    if _tutorial_popover is not None:
        _tutorial_popover.popdown()
        _tutorial_popover = None

    popover = Gtk.Popover()
    popover.set_position(Gtk.PositionType.RIGHT)
    popover.set_default_size(700, 850)
    popover.set_transient_for(parent)

    notebook = Gtk.Notebook()
    popover.set_child(notebook)

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

    def _on_closed(_p):
        global _tutorial_popover
        _tutorial_popover = None
    popover.connect("closed", _on_closed)
    popover.set_parent(anchor)
    popover.popup()
    _tutorial_popover = popover


def _read_html(path: Path) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return f"<html><body><p>Could not load {path}</p></body></html>"
