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

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from config.gtk_window.widgets import AdwSwitchRow
from config.vars import Vars
from features import gamification

GAMIFICATION_TEXT = (
    "Earn XP and unlock achievements as you use Edgeware. Fully local: progress "
    "is kept in a plain file on your machine, with no account or leaderboard. "
    "This page is a snapshot from when it was opened."
)

_STATS = [
    ("Popups dismissed", "popup_closed"),
    ("Prompts completed", "prompt_completed"),
    ("Denials seen", "denial_seen"),
    ("Minutes active", "playtime_minute"),
]


class ProgressTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        prog = gamification.progress()

        # ---- Enable + reset ----------------------------------------------
        general = Adw.PreferencesGroup(title="Gamification", description=GAMIFICATION_TEXT)
        self.add(general)
        general.add(AdwSwitchRow(
            "Enable Gamification", vars.gamification,
            subtitle="Track XP, levels and achievements."))
        general.add(AdwSwitchRow(
            "Milestone Rewards", vars.gamification_rewards,
            subtitle="A burst of popups and a strong toy buzz on each achievement or quest."))
        general.add(AdwSwitchRow(
            "On-screen Progress HUD", vars.gamification_hud,
            subtitle="Show a live level and XP bar in the corner while running."))

        reset_row = Adw.ActionRow(title="Reset Progress", subtitle="Erase all XP, levels and achievements.")
        reset_btn = Gtk.Button(label="Reset")
        reset_btn.add_css_class("destructive-action")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_reset)
        reset_row.add_suffix(reset_btn)
        general.add(reset_row)

        # ---- Level + XP --------------------------------------------------
        into, span = prog.xp_into_level()
        level_group = Adw.PreferencesGroup(title="Level")
        self.add(level_group)
        level_row = Adw.ActionRow(
            title=f"Level {prog.level}",
            subtitle=f"{into} / {span} XP to next level · {prog.xp} total")
        bar = Gtk.ProgressBar()
        bar.set_fraction(into / span if span else 1.0)
        bar.set_valign(Gtk.Align.CENTER)
        bar.set_hexpand(True)
        bar.set_size_request(180, -1)
        level_row.add_suffix(bar)
        level_group.add(level_row)

        # ---- Quests ------------------------------------------------------
        for scope, title in (("daily", "Daily Quests"), ("weekly", "Weekly Quests")):
            items = prog.quests.get(scope, {}).get("items", [])
            if not items:
                continue
            group = Adw.PreferencesGroup(title=title)
            self.add(group)
            for q in items:
                row = Adw.ActionRow(
                    title=q.desc,
                    subtitle=f"{min(q.progress, q.target)} / {q.target}  ·  +{q.reward} XP")
                if q.done:
                    row.add_prefix(Gtk.Image.new_from_icon_name("emblem-ok-symbolic"))
                else:
                    qbar = Gtk.ProgressBar()
                    qbar.set_fraction(q.progress / q.target if q.target else 1.0)
                    qbar.set_valign(Gtk.Align.CENTER)
                    qbar.set_size_request(120, -1)
                    row.add_suffix(qbar)
                group.add(row)

        # ---- Stats -------------------------------------------------------
        stats = Adw.PreferencesGroup(title="Stats")
        self.add(stats)
        for label, key in _STATS:
            row = Adw.ActionRow(title=label)
            value = Gtk.Label(label=str(prog.counters.get(key, 0)))
            value.add_css_class("dim-label")
            row.add_suffix(value)
            stats.add(row)

        # ---- Achievements ------------------------------------------------
        achievements = gamification.all_achievements()
        unlocked = sum(1 for a in achievements if a.id in prog.achievements)
        ach_group = Adw.PreferencesGroup(
            title="Achievements", description=f"{unlocked} / {len(achievements)} unlocked")
        self.add(ach_group)
        for ach in achievements:
            is_unlocked = ach.id in prog.achievements
            # Hidden until earned: locked entries reveal neither name nor hint.
            if is_unlocked:
                row = Adw.ActionRow(title=ach.name, subtitle=ach.description)
                row.add_prefix(Gtk.Image.new_from_icon_name("starred-symbolic"))
            else:
                row = Adw.ActionRow(title="Hidden achievement", subtitle="Keep playing to unlock.")
                row.add_prefix(Gtk.Image.new_from_icon_name("changes-prevent-symbolic"))
                row.set_sensitive(False)
            ach_group.add(row)

    def _on_reset(self, button: Gtk.Button) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading="Reset progress?",
            body="This erases all XP, levels and achievements. It cannot be undone.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dlg, response: str) -> None:
            if response == "reset":
                gamification.reset()
                toast = Adw.Toast.new("Progress reset. Reopen this page to refresh.")
                root = self.get_root()
                if hasattr(root, "_toast_overlay"):
                    root._toast_overlay.add_toast(toast)

        dialog.connect("response", on_response)
        dialog.present()
