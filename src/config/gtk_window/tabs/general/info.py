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

from gi import require_version

require_version("Gtk", "4.0")
from gi.repository import Gtk

from config.gtk_window.widgets import ConfigSection
from pack import Pack

MULTI_PACK_TEXT = (
    "NOTE: If you have multiple packs loaded, make sure to apply the pack you want "
    "using the \"Switch Pack\" button at the bottom of the window!"
)
INFO_TEXT = (
    "This section requires an optional \"information file\" that pack creators can choose "
    "to add. If the section is greyed out but other sections on this page are working fine, "
    "chances are the pack just doesn't have one!"
)
DISCORD_TEXT = (
    "These will only display on your discord if you turn the associated "
    "\"Show on Discord\" setting on (found in the Dangerous Settings tab)."
)


class StatusItem(Gtk.Box):
    def __init__(self, text: str, includes: bool, tooltip: str | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_hexpand(True)

        lbl = Gtk.Label(label=text, wrap=True)
        lbl.add_css_class("heading")
        self.append(lbl)

        status = "\u2713" if includes else "\u2717"
        status_lbl = Gtk.Label(label=status)
        status_lbl.add_css_class("status-ok" if includes else "status-fail")
        if tooltip:
            status_lbl.set_tooltip_text(tooltip)
        self.append(status_lbl)


class StatsItem(Gtk.Box):
    def __init__(self, text: str, number: int) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_hexpand(True)

        lbl = Gtk.Label(label=text)
        lbl.add_css_class("heading")
        self.append(lbl)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        num_lbl = Gtk.Label(label=str(number))
        num_lbl.add_css_class("stats-number")
        self.append(num_lbl)


class InfoTab(Gtk.ScrolledWindow):
    def __init__(self, pack: Pack) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        # Stats
        stats_section = ConfigSection("Stats", MULTI_PACK_TEXT)
        vbox.append(stats_section)

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        stats_section.append(status_row)
        status_row.append(StatusItem("Pack Loaded", pack.paths.root.exists()))
        status_row.append(StatusItem("Info File", pack.paths.info.is_file()))
        status_row.append(StatusItem("Pack has Wallpaper", pack.paths.wallpaper.is_file()))
        status_row.append(
            StatusItem(
                "Custom Startup",
                bool(pack.paths.splash),
                "If you are looking to add this to packs made before Edgeware++, "
                'put the desired file in /resource/ and name it "loading_splash.png"',
            )
        )
        status_row.append(StatusItem("Custom Discord Status", pack.paths.discord.is_file()))
        status_row.append(
            StatusItem(
                "Custom Icon",
                pack.paths.icon.is_file(),
                'put the desired file in /resource/ and name it "icon.ico".',
            )
        )
        status_row.append(
            StatusItem(
                "Corruption",
                pack.paths.corruption.is_file(),
                "An Edgeware++ feature that changes content over time.",
            )
        )

        # Stats numbers
        stats_row_1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        stats_section.append(stats_row_1)
        stats_row_1.append(StatsItem("Images", len(pack.images)))
        stats_row_1.append(StatsItem("Audio Files", len(pack.audio)))
        stats_row_1.append(StatsItem("Videos", len(pack.videos)))
        stats_row_1.append(StatsItem("Web Links", _list_length(pack, "web")))

        stats_row_2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        stats_section.append(stats_row_2)
        stats_row_2.append(StatsItem("Prompts", _list_length(pack, "prompts")))
        stats_row_2.append(StatsItem("Captions", _list_length(pack, "captions")))
        stats_row_2.append(StatsItem("Hypnos", len(pack.hypnos)))

        # Information
        info_section = ConfigSection("Information", INFO_TEXT)
        vbox.append(info_section)

        info_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        info_section.append(info_row)

        desc_frame = Gtk.Frame()
        desc_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        desc_frame.set_child(desc_vbox)
        desc_title = Gtk.Label(label="Description")
        desc_title.add_css_class("heading")
        desc_vbox.append(desc_title)
        desc_lbl = Gtk.Label(label=pack.info.description, wrap=True)
        desc_lbl.set_xalign(0)
        desc_vbox.append(desc_lbl)
        info_row.append(desc_frame)

        basic_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        basic_frame.set_hexpand(True)
        info_row.append(basic_frame)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        basic_frame.append(name_row)
        Gtk.Label(label="Pack Name:").add_css_class("heading")
        name_lbl = Gtk.Label(label=pack.info.name, wrap=True)
        name_lbl.set_hexpand(True)
        name_row.append(name_lbl)

        creator_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        basic_frame.append(creator_row)
        Gtk.Label(label="Author Name:").add_css_class("heading")
        creator_lbl = Gtk.Label(label=pack.info.creator, wrap=True)
        creator_lbl.set_hexpand(True)
        creator_row.append(creator_lbl)

        version_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        basic_frame.append(version_row)
        Gtk.Label(label="Version:").add_css_class("heading")
        version_lbl = Gtk.Label(label=pack.info.version, wrap=True)
        version_lbl.set_hexpand(True)
        version_row.append(version_lbl)

        has_info = pack.paths.info.is_file()
        desc_frame.set_sensitive(has_info)
        basic_frame.set_sensitive(has_info)

        # Discord
        discord_section = ConfigSection("Discord Information", DISCORD_TEXT)
        vbox.append(discord_section)

        discord_frame = Gtk.Frame()
        discord_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        discord_frame.set_child(discord_row)
        discord_section.append(discord_frame)

        c1 = Gtk.Label(label="Custom Discord Status:")
        c1.add_css_class("heading")
        dc_lbl = Gtk.Label(label=pack.discord.text, wrap=True)
        dc_lbl.set_hexpand(True)
        discord_row.append(dc_lbl)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        discord_row.append(sep)

        c2 = Gtk.Label(label="Discord Status Image:")
        c2.add_css_class("heading")
        discord_row.append(c2)
        img_lbl = Gtk.Label(label=pack.discord.image)
        img_lbl.set_tooltip_text(
            "As much as I would like to show you this image, it's fetched from the discord "
            "application API- which I cannot access without permissions."
        )
        discord_row.append(img_lbl)

        discord_frame.set_sensitive(pack.paths.discord.is_file())


def _list_length(pack: Pack, attr: str) -> int:
    return len(getattr(pack.index.default, attr)) + sum(
        [len(getattr(mood, attr)) for mood in pack.index.moods]
    )
