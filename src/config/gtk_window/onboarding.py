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

"""First-launch onboarding assistant.

Shown automatically when no config exists (first install) or when the
config window is opened with --first-launch-configure.  Also callable
manually from the UI.  Five steps:

  1. Welcome — what is Edgeware++
  2. Import Pack — pick a .zip (required to proceed meaningfully)
  3. Panic Key — set it now while we have attention
  4. Panic Wallpaper — auto-import current wallpaper
  5. Done — save & optionally launch
"""

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk


def show_onboarding(parent: Gtk.Window, vars, pack) -> None:
    """Show the onboarding dialog attached to *parent*."""
    dialog = _OnboardingDialog(vars, pack)
    dialog.set_transient_for(parent)
    dialog.present()


class _OnboardingDialog(Adw.Window):
    def __init__(self, vars, pack) -> None:
        super().__init__()
        self._vars = vars
        self._pack = pack
        self._pack_imported = False

        self.set_default_size(540, 580)
        self.set_resizable(False)
        self.set_modal(True)
        self.set_title("Welcome to Edgeware++")

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        self._title_widget = Adw.WindowTitle(title="Welcome to Edgeware++", subtitle="Step 1 of 5")
        header.set_title_widget(self._title_widget)
        toolbar_view.add_top_bar(header)
        self.set_content(toolbar_view)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        toolbar_view.set_content(outer)

        # Progress bar
        self._progress = Gtk.ProgressBar()
        self._progress.set_fraction(0.2)
        self._progress.add_css_class("osd")
        outer.append(self._progress)

        # Page stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_vexpand(True)
        outer.append(self._stack)

        self._pages = [
            ("welcome",    self._make_welcome()),
            ("import",     self._make_import()),
            ("panic_key",  self._make_panic_key()),
            ("wallpaper",  self._make_wallpaper()),
            ("done",       self._make_done()),
        ]
        for name, page in self._pages:
            self._stack.add_named(page, name)

        # Nav buttons
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav.set_margin_start(16)
        nav.set_margin_end(16)
        nav.set_margin_top(8)
        nav.set_margin_bottom(16)
        outer.append(nav)

        self._back_btn = Gtk.Button(label="Back")
        self._back_btn.set_sensitive(False)
        self._back_btn.connect("clicked", self._on_back)
        nav.append(self._back_btn)

        spacer = Gtk.Label()
        spacer.set_hexpand(True)
        nav.append(spacer)

        self._skip_btn = Gtk.Button(label="Skip")
        self._skip_btn.connect("clicked", self._on_skip)
        self._skip_btn.add_css_class("flat")
        nav.append(self._skip_btn)

        self._next_btn = Gtk.Button(label="Next")
        self._next_btn.add_css_class("suggested-action")
        self._next_btn.connect("clicked", self._on_next_or_finish)
        nav.append(self._next_btn)

        self._page_idx = 0
        self._update_nav()

    # ------------------------------------------------------------------
    # Page builders
    # ------------------------------------------------------------------

    def _make_welcome(self) -> Gtk.Widget:
        return _page(
            icon="application-x-executable-symbolic",
            title="Welcome to Edgeware++ LinuxNative",
            body=(
                "Edgeware++ is a popup program that fills your screen with images, "
                "video, audio and text from a content pack while you use your computer.\n\n"
                "It's designed to feel like a playful virus — harmless unless you "
                "intentionally enable the dangerous options (Fill Drive, Replace Images), "
                "which are clearly marked and off by default.\n\n"
                "This setup wizard will walk you through the three things you must do "
                "before running Edgeware for the first time:\n\n"
                "  1. Import a content pack\n"
                "  2. Set a panic key (your emergency exit)\n"
                "  3. Set a panic wallpaper\n\n"
                "You can always come back to any of these from the config tabs."
            ),
        )

    def _make_import(self) -> Gtk.Widget:
        box = _page_box(
            icon="folder-download-symbolic",
            title="Import a Content Pack",
            body=(
                "Packs are .zip files — don't extract them. Pick yours below.\n\n"
                "\"Import New\" copies it into data/packs/ so you can switch between "
                "packs easily. \"Change Default\" overwrites the built-in default pack. "
                "Import New is recommended for most users.\n\n"
                "Don't have a pack yet? You can skip this step and import one later "
                "from the Import Pack button in the header bar."
            ),
        )

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.CENTER)
        btn_row.set_margin_top(12)

        import_new_btn = Gtk.Button(label="Import New Pack")
        import_new_btn.add_css_class("suggested-action")
        import_new_btn.connect("clicked", lambda _: self._do_import(False))
        btn_row.append(import_new_btn)

        change_default_btn = Gtk.Button(label="Change Default Pack")
        change_default_btn.connect("clicked", lambda _: self._do_import(True))
        btn_row.append(change_default_btn)

        self._import_status = Gtk.Label(label="No pack imported yet.")
        self._import_status.add_css_class("dim-label")
        self._import_status.set_margin_top(8)

        box.append(btn_row)
        box.append(self._import_status)
        return box

    def _make_panic_key(self) -> Gtk.Widget:
        box = _page_box(
            icon="dialog-warning-symbolic",
            title="Set a Panic Key",
            body=(
                "The panic key instantly stops Edgeware and reverts your wallpaper — "
                "your emergency exit.\n\n"
                "Click the button below and press any key to set it. F9 or F12 are "
                "good choices: easy to reach, unlikely to fire by accident.\n\n"
                "On Niri: the GlobalShortcuts portal is not supported. After setup, "
                "also add the keybind shown on the Start tab to ~/.config/niri/config.kdl."
            ),
        )

        from config.gtk_window.utils import pretty_panic_key
        self._panic_key_btn = Gtk.Button(
            label=f"Current: <{pretty_panic_key(self._vars.global_panic_key.get())}>"
        )
        self._panic_key_btn.set_halign(Gtk.Align.CENTER)
        self._panic_key_btn.add_css_class("suggested-action")
        self._panic_key_btn.set_margin_top(12)
        self._panic_key_btn.connect("clicked", self._on_set_panic_key)
        box.append(self._panic_key_btn)
        return box

    def _make_wallpaper(self) -> Gtk.Widget:
        box = _page_box(
            icon="image-x-generic-symbolic",
            title="Set a Panic Wallpaper",
            body=(
                "When you panic, Edgeware reverts your desktop wallpaper to the "
                "\"panic wallpaper\". Without this set, panicking leaves a blank desktop.\n\n"
                "Click \"Auto Import\" to use your current wallpaper — this is almost "
                "always what you want. Or pick a file manually."
            ),
        )

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.CENTER)
        btn_row.set_margin_top(12)

        auto_btn = Gtk.Button(label="Auto Import (Recommended)")
        auto_btn.add_css_class("suggested-action")
        auto_btn.connect("clicked", self._on_auto_wallpaper)
        btn_row.append(auto_btn)

        manual_btn = Gtk.Button(label="Choose File…")
        manual_btn.connect("clicked", self._on_manual_wallpaper)
        btn_row.append(manual_btn)

        self._wallpaper_status = Gtk.Label()
        self._wallpaper_status.add_css_class("dim-label")
        self._wallpaper_status.set_margin_top(8)
        self._refresh_wallpaper_status()

        box.append(btn_row)
        box.append(self._wallpaper_status)
        return box

    def _make_done(self) -> Gtk.Widget:
        return _page(
            icon="emblem-ok-symbolic",
            title="You're All Set!",
            body=(
                "Your panic key and panic wallpaper are configured. You're ready to run "
                "Edgeware++.\n\n"
                "Click \"Save & Launch\" to save settings and start the runtime now, "
                "or \"Save\" to save and stay in the config window.\n\n"
                "Tips:\n"
                "• Start tab → Popup Timer Delay: 8000–10000 ms is a gentle start.\n"
                "• Popup Types → set chances for each type.\n"
                "• Wallpaper → auto-import your panic wallpaper any time it changes.\n"
                "• Tutorial tab → full documentation in the config window.\n\n"
                "Have fun, stay safe, and remember your panic key!"
            ),
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _page_names(self):
        return [n for n, _ in self._pages]

    def _on_next_or_finish(self, _btn) -> None:
        if self._page_idx == len(self._pages) - 1:
            self._do_save(launch=True)
        else:
            self._page_idx = min(self._page_idx + 1, len(self._pages) - 1)
            self._stack.set_visible_child_name(self._page_names()[self._page_idx])
            self._update_nav()

    def _on_back(self, _btn) -> None:
        self._page_idx = max(self._page_idx - 1, 0)
        self._stack.set_visible_child_name(self._page_names()[self._page_idx])
        self._update_nav()

    def _on_skip(self, _btn) -> None:
        if self._page_idx < len(self._pages) - 1:
            self._on_next(None)
        else:
            self._do_save(launch=False)

    def _update_nav(self) -> None:
        idx = self._page_idx
        total = len(self._pages)
        self._progress.set_fraction((idx + 1) / total)
        self._title_widget.set_subtitle(f"Step {idx + 1} of {total}")
        self._back_btn.set_sensitive(idx > 0)

        if idx == total - 1:
            self._next_btn.set_label("Save & Launch")
            self._skip_btn.set_label("Save Only")
        else:
            self._next_btn.set_label("Next")
            self._skip_btn.set_label("Skip")

        # Skip not available on welcome or done
        self._skip_btn.set_visible(idx not in (0, total - 1))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _do_import(self, default: bool) -> None:
        from config.gtk_window.import_pack import import_pack
        import_pack(default)
        self._pack_imported = True
        self._import_status.set_text("Pack imported! Click Next to continue.")
        self._import_status.remove_css_class("dim-label")
        self._import_status.add_css_class("success")

    def _on_set_panic_key(self, btn: Gtk.Button) -> None:
        from config.gtk_window.utils import pretty_panic_key, request_global_panic_key
        request_global_panic_key(btn, self._vars.global_panic_key)

        def update_label():
            btn.set_label(f"Current: <{pretty_panic_key(self._vars.global_panic_key.get())}>")
            return False

        GLib.timeout_add(200, update_label)

    def _on_auto_wallpaper(self, _btn) -> None:
        try:
            from PIL import Image
            from os_utils import get_wallpaper
            from paths import Data
            Image.open(get_wallpaper()).convert("RGB").save(Data.PANIC_WALLPAPER)
            self._wallpaper_status.set_text("Panic wallpaper set from current wallpaper.")
            self._wallpaper_status.remove_css_class("dim-label")
            self._wallpaper_status.add_css_class("success")
        except Exception as e:
            self._wallpaper_status.set_text(f"Failed: {e}")

    def _on_manual_wallpaper(self, _btn) -> None:
        fd = Gtk.FileDialog.new()
        fd.set_title("Choose Panic Wallpaper")
        filt = Gtk.FileFilter()
        filt.set_name("Image files")
        filt.add_mime_type("image/jpeg")
        filt.add_mime_type("image/png")
        fd.set_default_filter(filt)
        fd.open(self, None, self._on_wallpaper_selected, None)

    def _on_wallpaper_selected(self, fd, result, _ud) -> None:
        try:
            file = fd.open_finish(result)
            if not file:
                return
            from PIL import Image
            from paths import Data
            Image.open(file.get_path()).convert("RGB").save(Data.PANIC_WALLPAPER)
            self._wallpaper_status.set_text("Panic wallpaper set.")
            self._wallpaper_status.remove_css_class("dim-label")
            self._wallpaper_status.add_css_class("success")
        except Exception as e:
            self._wallpaper_status.set_text(f"Failed: {e}")

    def _refresh_wallpaper_status(self) -> None:
        from paths import CustomAssets
        wp = CustomAssets.panic_wallpaper()
        if wp.is_file():
            self._wallpaper_status.set_text(f"Currently set: {wp.name}")
        else:
            self._wallpaper_status.set_text("No panic wallpaper set yet.")

    def _do_save(self, launch: bool) -> None:
        from config.gtk_window.utils import write_save
        write_save(self._vars, launch)
        self.close()


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _page_box(icon: str, title: str, body: str) -> Gtk.Box:
    """Scrollable page with icon + title + body, returns the box for appending."""
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    outer.set_margin_start(24)
    outer.set_margin_end(24)
    outer.set_margin_top(24)
    outer.set_margin_bottom(8)
    scroll.set_child(outer)

    img = Gtk.Image.new_from_icon_name(icon)
    img.set_pixel_size(48)
    img.set_margin_bottom(12)
    outer.append(img)

    title_lbl = Gtk.Label(label=title)
    title_lbl.add_css_class("title-2")
    title_lbl.set_wrap(True)
    title_lbl.set_xalign(0.5)
    title_lbl.set_margin_bottom(12)
    outer.append(title_lbl)

    body_lbl = Gtk.Label(label=body, wrap=True, xalign=0)
    outer.append(body_lbl)

    return outer


def _page(icon: str, title: str, body: str) -> Gtk.Widget:
    """Full scrollable page (no extra widgets needed)."""
    return _page_box(icon, title, body)
