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

from config.gtk_window.widgets import AdwComboRow, AdwSwitchRow
from config.vars import Vars
from features import gamification
from features.hud import CORNERS

GAMIFICATION_TEXT = (
    "Earn XP and unlock achievements as you use Edgeware. Fully local: progress "
    "is kept in a plain file on your machine, with no account or leaderboard. "
    "Your level, quests, stats and achievements are shown on the Home dashboard."
)


class ProgressTab(Adw.PreferencesPage):
    """Gamification settings only — the live stats live on the Home dashboard."""

    def __init__(self, vars: Vars) -> None:
        super().__init__()

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
        general.add(AdwComboRow(
            "HUD Corner", vars.gamification_hud_corner,
            {c: c.replace("-", " ").title() for c in CORNERS}))

        reset_row = Adw.ActionRow(title="Reset Progress", subtitle="Erase all XP, levels and achievements.")
        reset_btn = Gtk.Button(label="Reset")
        reset_btn.add_css_class("destructive-action")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_reset)
        reset_row.add_suffix(reset_btn)
        general.add(reset_row)

    def _on_reset(self, button: Gtk.Button) -> None:
        dialog = Adw.AlertDialog(
            heading="Reset progress?",
            body="This erases all XP, levels and achievements. It cannot be undone.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset Progress")
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
        dialog.present(self.get_root())
