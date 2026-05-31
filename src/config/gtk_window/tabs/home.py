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

# The Home dashboard: the landing view of the Dashboard window. A ViewStack with
# an Overview (pack hero, quick actions, level/quests/stats, config pills,
# version) and, when gamification is on, an Achievements view. The Dashboard
# window puts a ViewSwitcher for this stack in its header.

import logging

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.gtk_window.widgets import AdwSwitchRow
from config.vars import Vars
from pack import Pack

_CSS_LOADED = False


def _ensure_css() -> None:
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    from gi.repository import Gdk
    css = Gtk.CssProvider()
    css.load_from_string("""
        .home-pill {
            background-color: alpha(@accent_bg_color, 0.18);
            color: @accent_fg_color;
            border-radius: 999px;
            padding: 4px 12px;
            margin: 2px;
        }
        .home-pill.dim { background-color: alpha(@window_fg_color, 0.10); color: @window_fg_color; }
        .home-hero { padding: 16px; }
        .home-hero-art { border-radius: 12px; }
    """)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _CSS_LOADED = True


def _pill(text: str, accent: bool = True) -> Gtk.Widget:
    label = Gtk.Label(label=text)
    label.add_css_class("home-pill")
    if not accent:
        label.add_css_class("dim")
    return label


def _pack_thumbnail(path, size: int = 64):
    try:
        import gi as _gi
        _gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import Gdk, GdkPixbuf
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True)
        pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
    except Exception as e:
        logging.debug(f"home thumbnail failed ({path}): {e}")
        return None
    pic.set_size_request(size, size)
    pic.set_content_fit(Gtk.ContentFit.CONTAIN)
    pic.set_valign(Gtk.Align.CENTER)
    pic.add_css_class("home-hero-art")
    return pic


class HomeTab(Gtk.Box):
    def __init__(self, vars: Vars, pack: Pack, local_version: str, live_version: str,
                 *, on_navigate, on_launch) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        _ensure_css()
        self._vars = vars
        self._pack = pack
        self._gamified = bool(vars.gamification.get())

        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)
        self.view_stack.set_hexpand(True)
        self.append(self.view_stack)

        # ---- Overview view ----------------------------------------------
        overview = Adw.PreferencesPage()
        self._build_hero(overview, pack, on_navigate)
        self._build_actions(overview, on_navigate, on_launch)
        if self._gamified:
            self._build_progression(overview)
        else:
            self._build_teaser(overview, vars)
        self._build_summary(overview, vars)
        self._build_version(overview, local_version, live_version)
        self.view_stack.add_titled_with_icon(overview, "overview", "Overview", "go-home-symbolic")

        # ---- Pack view (status / content / information / Discord) --------
        from config.gtk_window.tabs.general.info import pack_detail_groups
        pack_page = Adw.PreferencesPage()
        self._build_pack_actions(pack_page, pack, on_navigate)
        for group in pack_detail_groups(pack):
            pack_page.add(group)
        self.view_stack.add_titled_with_icon(pack_page, "pack", "Pack", "folder-symbolic")

        # Overview + Pack always exist, so the header switcher is always shown.
        self.has_multiple_views = True

        # ---- Achievements view (only when gamification is on) -----------
        if self._gamified:
            from config.gtk_window.gamification_widgets import achievements_group
            from features import gamification
            ach_page = Adw.PreferencesPage()
            ach_page.add(achievements_group(gamification.progress()))
            self.view_stack.add_titled_with_icon(
                ach_page, "achievements", "Achievements", "starred-symbolic")

    # ------------------------------------------------------------------
    def _build_pack_actions(self, page, pack, on_navigate) -> None:
        group = Adw.PreferencesGroup()
        page.add(group)
        row = Adw.ActionRow(title=getattr(pack.info, "name", "default") or "default",
                            subtitle="Active pack")
        thumb = _pack_thumbnail(getattr(pack, "icon", None), 48)
        if thumb:
            row.add_prefix(thumb)
        btn = Gtk.Button(label="Manage Packs", valign=Gtk.Align.CENTER)
        btn.connect("clicked", lambda _b: on_navigate("Packs"))
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        group.add(row)

    # ------------------------------------------------------------------
    def _build_hero(self, page, pack, on_navigate) -> None:
        group = Adw.PreferencesGroup()
        page.add(group)

        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        card.add_css_class("card")
        card.add_css_class("home-hero")

        thumb = _pack_thumbnail(getattr(pack, "icon", None), 88)
        if thumb:
            card.append(thumb)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                       hexpand=True, valign=Gtk.Align.CENTER)
        name = Gtk.Label(label=getattr(pack.info, "name", "default") or "default", xalign=0)
        name.add_css_class("title-2")
        info.append(name)
        creator = (getattr(pack.info, "creator", "") or "").strip()
        if creator and creator != "Anonymous":
            by = Gtk.Label(label=f"by {creator}", xalign=0)
            by.add_css_class("dim-label")
            by.add_css_class("caption")
            info.append(by)

        if self._gamified:
            from config.gtk_window.gamification_widgets import summary
            from features import gamification
            prog = gamification.progress()
            s = summary(prog)
            lvl = Gtk.Label(label=f"Level {s['level']}  ·  {s['xp']} XP", xalign=0)
            lvl.add_css_class("caption")
            lvl.set_margin_top(4)
            info.append(lvl)
            bar = Gtk.ProgressBar()
            bar.set_fraction(s["into"] / s["span"] if s["span"] else 1.0)
            info.append(bar)
        card.append(info)

        switch = Gtk.Button(label="Switch", valign=Gtk.Align.CENTER)
        switch.connect("clicked", lambda _b: on_navigate("Packs"))
        card.append(switch)

        group.add(card)

    # ------------------------------------------------------------------
    def _build_actions(self, page, on_navigate, on_launch) -> None:
        group = Adw.PreferencesGroup()
        page.add(group)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(bar, f"set_margin_{m}")(4)

        launch = Gtk.Button()
        launch.set_child(Adw.ButtonContent(label="Launch Edgeware",
                                           icon_name="media-playback-start-symbolic"))
        launch.add_css_class("suggested-action")
        launch.add_css_class("pill")
        launch.set_hexpand(True)
        launch.connect("clicked", lambda _b: on_launch())
        bar.append(launch)

        settings = Gtk.Button()
        settings.set_child(Adw.ButtonContent(label="Settings", icon_name="emblem-system-symbolic"))
        settings.add_css_class("pill")
        settings.connect("clicked", lambda _b: on_navigate("General"))
        bar.append(settings)

        panic = Gtk.Button()
        panic.set_child(Adw.ButtonContent(label="Panic", icon_name="process-stop-symbolic"))
        panic.add_css_class("destructive-action")
        panic.add_css_class("pill")
        panic.connect("clicked", self._on_panic)
        bar.append(panic)

        group.add(bar)

    # ------------------------------------------------------------------
    def _build_progression(self, page) -> None:
        from config.gtk_window.gamification_widgets import quest_groups, stats_group
        from features import gamification
        prog = gamification.progress()
        for group in quest_groups(prog):
            page.add(group)
        page.add(stats_group(prog))

    def _build_teaser(self, page, vars: Vars) -> None:
        group = Adw.PreferencesGroup(title="Progression")
        page.add(group)
        group.add(AdwSwitchRow(
            "Track Your Progress", vars.gamification,
            subtitle="Earn XP, levels and achievements as you play. Fully local, no "
                     "account. Turn on, then reopen to see your stats here."))

    # ------------------------------------------------------------------
    def _build_summary(self, page, vars: Vars) -> None:
        group = Adw.PreferencesGroup(title="At a Glance")
        page.add(group)
        pills = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                            column_spacing=4, row_spacing=4)
        pills.append(_pill(f"Popups {vars.image_chance.get()}%"))
        pills.append(_pill("Companion on" if vars.companion_enabled.get() else "Companion off",
                           accent=bool(vars.companion_enabled.get())))
        modes = []
        if vars.hibernate_mode.get():
            modes.append("Hibernate")
        if vars.corruption_mode.get():
            modes.append("Corruption")
        if vars.mitosis_mode.get():
            modes.append("Mitosis")
        pills.append(_pill("Modes: " + ", ".join(modes) if modes else "No special modes",
                           accent=bool(modes)))
        if vars.sextoys.get():
            pills.append(_pill("Toy configured"))
        row = Adw.ActionRow()
        row.set_activatable(False)
        row.set_child(pills)
        group.add(row)

    # ------------------------------------------------------------------
    def _build_version(self, page, local_version: str, live_version: str) -> None:
        group = Adw.PreferencesGroup(title="Version")
        page.add(group)
        local_row = Adw.ActionRow(title="Installed")
        local_lbl = Gtk.Label(label=local_version)
        local_lbl.add_css_class("dim-label")
        local_row.add_suffix(local_lbl)
        group.add(local_row)
        latest_row = Adw.ActionRow(title="Latest on GitHub")
        if live_version:
            text = live_version
            mismatch = local_version != live_version
        else:
            from config.gtk_window.utils import config
            # Empty means either checks are off or the fetch hasn't landed/failed.
            text = "Update checks off" if config.get("toggleInternet") else "Checking…"
            mismatch = False
        latest_lbl = Gtk.Label(label=text)
        latest_lbl.add_css_class("version-mismatch" if mismatch else "dim-label")
        latest_row.add_suffix(latest_lbl)
        group.add(latest_row)

    def _on_panic(self, _btn: Gtk.Button) -> None:
        from panic import send_panic
        send_panic()
