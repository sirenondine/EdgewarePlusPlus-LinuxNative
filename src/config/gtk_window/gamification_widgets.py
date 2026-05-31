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

# Shared gamification UI bits so the full Progress page and the Home dashboard
# render the same level/XP widget and read the same summary numbers from one
# place.

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw, Gtk

from features import gamification


def level_row(prog) -> Adw.ActionRow:
    """An ActionRow showing the current level, XP-to-next, and a progress bar."""
    into, span = prog.xp_into_level()
    row = Adw.ActionRow(
        title=f"Level {prog.level}",
        subtitle=f"{into} / {span} XP to next level  ·  {prog.xp} total")
    bar = Gtk.ProgressBar()
    bar.set_fraction(into / span if span else 1.0)
    bar.set_valign(Gtk.Align.CENTER)
    bar.set_hexpand(True)
    bar.set_size_request(180, -1)
    row.add_suffix(bar)
    return row


_STATS = [
    ("Popups dismissed", "popup_closed"),
    ("Prompts completed", "prompt_completed"),
    ("Denials seen", "denial_seen"),
    ("Minutes active", "playtime_minute"),
]


def quest_groups(prog) -> list:
    """Daily/weekly quest groups (empty list if a pack defines no quests)."""
    groups = []
    for scope, title in (("daily", "Daily Quests"), ("weekly", "Weekly Quests")):
        items = prog.quests.get(scope, {}).get("items", [])
        if not items:
            continue
        group = Adw.PreferencesGroup(title=title)
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
        groups.append(group)
    return groups


def stats_group(prog) -> Adw.PreferencesGroup:
    """Lifetime counters."""
    group = Adw.PreferencesGroup(title="Stats")
    for label, key in _STATS:
        row = Adw.ActionRow(title=label)
        value = Gtk.Label(label=str(prog.counters.get(key, 0)))
        value.add_css_class("dim-label")
        row.add_suffix(value)
        group.add(row)
    return group


def achievements_group(prog) -> Adw.PreferencesGroup:
    """Achievements; locked ones stay hidden (no name/hint) until earned."""
    achievements = gamification.all_achievements()
    unlocked = sum(1 for a in achievements if a.id in prog.achievements)
    group = Adw.PreferencesGroup(
        title="Achievements", description=f"{unlocked} / {len(achievements)} unlocked")
    for ach in achievements:
        if ach.id in prog.achievements:
            row = Adw.ActionRow(title=ach.name, subtitle=ach.description)
            row.add_prefix(Gtk.Image.new_from_icon_name("starred-symbolic"))
        else:
            row = Adw.ActionRow(title="Hidden achievement", subtitle="Keep playing to unlock.")
            row.add_prefix(Gtk.Image.new_from_icon_name("changes-prevent-symbolic"))
            row.set_sensitive(False)
        group.add(row)
    return group


def summary(prog=None) -> dict:
    """A flat snapshot of progression numbers for compact displays (e.g. the
    Home dashboard pills)."""
    prog = prog or gamification.progress()
    into, span = prog.xp_into_level()
    achievements = gamification.all_achievements()
    daily = prog.quests.get("daily", {}).get("items", [])
    return {
        "level": prog.level,
        "xp": prog.xp,
        "into": into,
        "span": span,
        "daily_done": sum(1 for q in daily if q.done),
        "daily_total": len(daily),
        "ach_unlocked": sum(1 for a in achievements if a.id in prog.achievements),
        "ach_total": len(achievements),
    }
