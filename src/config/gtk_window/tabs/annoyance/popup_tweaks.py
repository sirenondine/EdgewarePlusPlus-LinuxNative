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

import threading

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from config.gtk_window.widgets import AdwComboRow, AdwSliderRow, AdwSwitchRow
from config.gtk_window.utils import config
from config.vars import Vars
from screeninfo import get_monitors

OVERLAY_TEXT = (
    "Modifiers applied on top of popups. Hypno overlays a transparent gif; "
    "Denial censors a popup — blur, pixelate or black bars, optionally over only "
    "AI-detected explicit regions, with the denial caption burned into the image."
)

_DENIAL_STYLES = {"blur": "Blur", "pixelate": "Pixelate", "bars": "Bars", "mixed": "Mixed"}
PARTS_TEXT = "With AI Region Detection on, the chance to censor each detected body part."
_PART_LABELS = {
    "breasts": "Breasts", "female_genitals": "Female Genitals", "male_genitals": "Male Genitals",
    "buttocks": "Buttocks", "anus": "Anus", "belly": "Belly", "armpits": "Armpits", "feet": "Feet",
}
CAPTION_TEXT = "Small bits of text that adorn each popup."
MONITORS_TEXT = "Choose which monitors Edgeware++ may spawn popups on."
MOVEMENT_TEXT = "Give each popup a chance to drift around the screen."
TIMEOUT_TEXT = "After a set time, popups fade out and delete themselves."


def _monitor_row(monitor) -> Adw.SwitchRow:
    """A switch row that enables/disables popups on one monitor (writes the
    disabledMonitors config list directly, not a ConfigVar)."""
    row = Adw.SwitchRow(title=monitor.name, subtitle=f"{monitor.width}×{monitor.height}")
    row.set_active(monitor.name not in config.get("disabledMonitors", []))

    def on_toggled(r, _p):
        disabled = config.setdefault("disabledMonitors", [])
        if r.get_active():
            if monitor.name in disabled:
                disabled.remove(monitor.name)
        elif monitor.name not in disabled:
            disabled.append(monitor.name)

    row.connect("notify::active", on_toggled)
    return row


class PopupTweaksTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()

        captions = Adw.PreferencesGroup(title="Captions", description=CAPTION_TEXT)
        self.add(captions)
        captions.add(AdwSwitchRow("Enable Popup Captions", vars.captions_in_popups))

        overlays = Adw.PreferencesGroup(title="Overlays", description=OVERLAY_TEXT)
        self.add(overlays)
        overlays.add(AdwSliderRow("Hypno Chance (%)", vars.hypno_chance, 0, 100))
        overlays.add(AdwSliderRow("Hypno Opacity (%)", vars.hypno_opacity, 1, 99))
        overlays.add(AdwSliderRow("Denial Chance (%)", vars.denial_chance, 0, 100))
        overlays.add(AdwComboRow("Denial Style", vars.denial_style, _DENIAL_STYLES))
        overlays.add(AdwSliderRow("Censor Intensity (%)", vars.denial_intensity, 0, 100))
        overlays.add(AdwSwitchRow(
            "AI Region Detection", vars.denial_detect,
            subtitle="Censor only explicit regions (needs NudeNet; stills only)."))
        overlays.add(AdwSwitchRow(
            "Caption In Image", vars.denial_caption_in_image,
            subtitle="Burn the denial caption into the image, Beta-Caption style."))
        overlays.add(AdwSwitchRow(
            "Reverse (Blur Background)", vars.denial_reverse,
            subtitle="Censor everything EXCEPT the selected parts (needs AI detection)."))
        overlays.add(self._build_nudenet_row())
        overlays.add(AdwSwitchRow(
            "Anime Detection (Union)", vars.denial_detect_anime,
            subtitle="Add an anime-tuned detector — better on 2D/stylised art. Needs the model below."))
        overlays.add(self._build_anime_row())

        parts = Adw.PreferencesGroup(title="Censor Body Parts", description=PARTS_TEXT)
        self.add(parts)
        for key, label in _PART_LABELS.items():
            parts.add(AdwSliderRow(f"{label} (%)", getattr(vars, f"censor_part_{key}"), 0, 100))
            parts.add(AdwSwitchRow(
                f"{label}: Censor When Covered", getattr(vars, f"censor_part_{key}_covered"),
                subtitle="Also censor when clothed, not just when exposed."))
        # Face has no covered variant; offer an eye-bar mode instead.
        parts.add(AdwSliderRow("Face (%)", vars.censor_part_face, 0, 100))
        parts.add(AdwSwitchRow(
            "Face: Eyes Only", vars.censor_face_eyes_only,
            subtitle="Censor just a bar over the eyes instead of the whole face."))

        opacity = Adw.PreferencesGroup(title="Opacity")
        self.add(opacity)
        opacity.add(AdwSliderRow("Popup Opacity (%)", vars.opacity, 5, 100))

        timeout = Adw.PreferencesGroup(title="Popup Timeout", description=TIMEOUT_TEXT)
        self.add(timeout)
        timeout.add(AdwSwitchRow("Enable Popup Timeout", vars.timeout_enabled))
        timeout.add(AdwSliderRow("Timeout", vars.timeout, 1, 120, unit="s"))

        misc = Adw.PreferencesGroup(title="Misc. Tweaks")
        self.add(misc)
        misc.add(AdwSwitchRow(
            "Buttonless Closing Popups", vars.buttonless,
            subtitle="Removes the close button; click a popup anywhere to close it."))
        misc.add(AdwSwitchRow(
            "Multi-Click Popups", vars.multi_click_popups,
            subtitle="Popups take several clicks to close."))

        monitors = Adw.PreferencesGroup(title="Monitors", description=MONITORS_TEXT)
        self.add(monitors)
        monitors.add(AdwSwitchRow(
            "Spawn on Active Monitor", vars.spawn_on_active_monitor,
            subtitle="Put popups on the monitor you're focused on (niri only)."))
        for monitor in get_monitors():
            monitors.add(_monitor_row(monitor))

        movement = Adw.PreferencesGroup(title="Popup Movement", description=MOVEMENT_TEXT)
        self.add(movement)
        movement.add(AdwSliderRow("Moving Popup Chance (%)", vars.moving_chance, 0, 100))
        movement.add(AdwSliderRow("Max Move Speed", vars.moving_speed, 1, 15))

    def _model_install_row(self, title, available_fn, install_fn,
                           installed_sub, missing_sub, installing_sub) -> Adw.ActionRow:
        """Generic status + one-click installer row for an optional model/dependency.
        available_fn() -> bool; install_fn() -> (ok, msg), run off the UI thread."""
        row = Adw.ActionRow(title=title)
        spinner = Adw.Spinner(valign=Gtk.Align.CENTER)
        button = Gtk.Button(valign=Gtk.Align.CENTER)
        button.add_css_class("flat")
        row.add_suffix(button)

        def show_installed() -> None:
            row.set_subtitle(installed_sub)
            button.set_visible(False)

        def show_missing(label: str = "Install", subtitle: str | None = None) -> None:
            row.set_subtitle(subtitle or missing_sub)
            button.set_label(label)
            button.set_sensitive(True)
            button.set_visible(True)

        def on_done(ok: bool, msg: str) -> bool:
            if spinner.get_parent():
                row.remove(spinner)
            if ok:
                show_installed()
            else:
                show_missing("Retry", f"Failed: {msg}")
            return False

        def on_click(_b: Gtk.Button) -> None:
            button.set_visible(False)
            row.add_suffix(spinner)
            row.set_subtitle(installing_sub)

            def work() -> None:
                ok, msg = install_fn()
                GLib.idle_add(on_done, ok, msg)

            threading.Thread(target=work, daemon=True).start()

        button.connect("clicked", on_click)
        show_installed() if available_fn() else show_missing()
        return row

    def _build_nudenet_row(self) -> Adw.ActionRow:
        """Status + installer for the optional NudeNet detector (whole-image fallback without it)."""
        from features import censor

        return self._model_install_row(
            "AI Detector (NudeNet)", censor.is_available, censor.install_detector,
            "Installed — region detection ready.",
            "Not installed — detection falls back to censoring the whole image.",
            "Installing NudeNet… (downloads ~100 MB, first run fetches a model)")

    def _build_anime_row(self) -> Adw.ActionRow:
        """Status + downloader for the optional anime-tuned detector model."""
        from features import censor

        return self._model_install_row(
            "Anime Detector Model", censor.anime_available, censor.install_anime_model,
            "Installed — anime detection ready.",
            "Not downloaded — enable & download to union an anime-tuned detector.",
            "Downloading anime model… (~48 MB)")
