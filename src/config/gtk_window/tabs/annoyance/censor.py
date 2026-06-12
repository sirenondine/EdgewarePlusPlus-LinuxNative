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
from config.vars import Vars

DENIAL_TEXT = (
    "Censor a popup: blur, pixelate or black-bar it — optionally over only the "
    "AI-detected explicit regions, following their exact shape, with the denial "
    "caption burned in."
)
PARTS_TEXT = "With AI detection on, the chance to censor each detected body part."
DETECT_TEXT = (
    "Detectors find body parts to censor. They stack (union); without any, denial "
    "censors the whole popup. Region shape needs a segmentation model.\n\n"
    "PERFORMANCE: each enabled detector runs once per censored popup. They run "
    "on the CPU by default (inference is serialised so it won't freeze the UI, but "
    "many detectors = slower popups). Enable only what you need."
)

_DENIAL_STYLES = {"blur": "Blur", "pixelate": "Pixelate", "bars": "Bars", "mixed": "Mixed"}
_CAPTION_FONTS = {
    "dejavu": "DejaVu Bold", "anton": "Anton", "bebas": "Bebas Neue",
    "fredoka": "Fredoka", "pacifico": "Pacifico", "random": "Random (per popup)",
}
_GLOW_COLORS = {
    "auto": "Auto (boldest colour)", "white": "White", "red": "Red",
    "pink": "Pink", "cyan": "Cyan", "green": "Green", "gold": "Gold",
}
_PART_LABELS = {
    "breasts": "Breasts", "female_genitals": "Female Genitals", "male_genitals": "Male Genitals",
    "buttocks": "Buttocks", "anus": "Anus", "belly": "Belly", "armpits": "Armpits", "feet": "Feet",
}


class CensorTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()

        denial = Adw.PreferencesGroup(title="Denial / Censor", description=DENIAL_TEXT)
        self.add(denial)
        denial.add(AdwSliderRow("Denial Chance (%)", vars.denial_chance, 0, 100))
        denial.add(AdwComboRow("Censor Style", vars.denial_style, _DENIAL_STYLES))
        denial.add(AdwSliderRow("Censor Intensity (%)", vars.denial_intensity, 0, 100))

        effects = Adw.PreferencesGroup(title="Effects")
        self.add(effects)
        effects.add(AdwSwitchRow(
            "Reverse (Blur Background)", vars.denial_reverse,
            subtitle="Censor everything EXCEPT the selected parts (needs detection)."))
        effects.add(AdwSwitchRow(
            "Mask-Shaped Censor", vars.denial_mask_shape,
            subtitle="Follow the exact body-part outline instead of a box (needs a segmentation model)."))
        effects.add(AdwSwitchRow(
            "Outline Glow", vars.denial_outline_glow,
            subtitle="Draw a soft glow around the region — pairs well with Reverse."))
        effects.add(AdwComboRow("Glow Color", vars.denial_glow_color, _GLOW_COLORS))
        effects.add(AdwSliderRow("Outline Thickness (%)", vars.denial_glow_thickness, 10, 400))

        caption = Adw.PreferencesGroup(title="Caption")
        self.add(caption)
        caption.add(AdwSwitchRow(
            "Caption In Image", vars.denial_caption_in_image,
            subtitle="Burn the denial caption into the image, Beta-Caption style."))
        caption.add(AdwComboRow("Caption Font", vars.denial_caption_font, _CAPTION_FONTS))
        caption.add(AdwSwitchRow(
            "Label Body Parts", vars.denial_part_labels,
            subtitle="Burn each detected part's name onto its censored region."))

        detect = Adw.PreferencesGroup(title="AI Detection", description=DETECT_TEXT)
        self.add(detect)
        detect.add(self._compute_row())
        detect.add(AdwSwitchRow(
            "AI Region Detection", vars.denial_detect,
            subtitle="Censor only the detected explicit regions (bundled model; stills only). Cost: light."))
        detect.add(AdwSwitchRow(
            "Anime Detection (Union)", vars.denial_detect_anime,
            subtitle="Anime-tuned detector — better on 2D/stylised art. Cost: HEAVY (1280px). Needs the model below."))
        detect.add(self._build_anime_row())
        detect.add(AdwSwitchRow(
            "Full-Breast Detection", vars.denial_detect_breasts,
            subtitle="Bundled breast segmentation — whole-breast shape (vs nipple-only). Cost: medium."))
        detect.add(AdwSwitchRow(
            "Full-Face Detection", vars.denial_detect_face,
            subtitle="Bundled face segmentation — whole-face masks (clean anonymity). Cost: medium."))
        detect.add(AdwSwitchRow(
            "Body Detection", vars.denial_detect_body,
            subtitle="Whole-body seg — best with Reverse. Cost: HEAVY (large model, not bundled — download separately)."))
        for label, var, sub in (
            ("Armpit Detection", vars.denial_detect_armpits, "Bundled armpit segmentation → armpits part. Cost: medium."),
            ("Belly Detection", vars.denial_detect_belly, "Bundled belly segmentation → belly part. Cost: medium."),
            ("Mouth Detection", vars.denial_detect_mouth, "Bundled mouth segmentation — gag/mouth censor. Cost: medium."),
            ("Underwear Detection", vars.denial_detect_underwear, "Bundled panties/underwear segmentation. Cost: medium."),
            ("Socks Detection", vars.denial_detect_socks, "Bundled socks segmentation. Cost: medium."),
            ("Skin Detection", vars.denial_detect_skin, "Bundled skin segmentation — exposed skin (aggressive). Cost: medium."),
        ):
            detect.add(AdwSwitchRow(label, var, subtitle=sub))

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
        parts.add(AdwSliderRow("Eye Bar Height (%)", vars.censor_eye_height, 10, 400))
        parts.add(AdwSliderRow("Body (%)", vars.censor_part_body, 0, 100))
        parts.add(AdwSliderRow("Mouth (%)", vars.censor_part_mouth, 0, 100))
        parts.add(AdwSliderRow("Underwear (%)", vars.censor_part_underwear, 0, 100))
        parts.add(AdwSliderRow("Socks (%)", vars.censor_part_socks, 0, 100))
        parts.add(AdwSliderRow("Skin (%)", vars.censor_part_skin, 0, 100))

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
            show_installed() if ok else show_missing("Retry", f"Failed: {msg}")
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

    def _compute_row(self) -> Adw.ActionRow:
        """Show whether detectors run on CPU or a GPU execution provider."""
        from features import censor

        prov = censor.active_provider()
        if prov == "CPU":
            sub = "CPU — install a GPU-enabled onnxruntime (ROCm/CUDA) to offload and speed this up."
        else:
            sub = f"GPU via {prov} — detectors are hardware-accelerated."
        row = Adw.ActionRow(title="Compute Backend", subtitle=sub)
        row.add_prefix(Gtk.Image.new_from_icon_name(
            "video-display-symbolic" if prov != "CPU" else "computer-symbolic"))
        return row

    def _build_anime_row(self) -> Adw.ActionRow:
        """Status + downloader for the optional anime-tuned detector model."""
        from features import censor

        return self._model_install_row(
            "Anime Detector Model", censor.anime_available, censor.install_anime_model,
            "Installed — anime detection ready.",
            "Not downloaded — enable & download to union an anime-tuned detector.",
            "Downloading anime model… (~48 MB)")
