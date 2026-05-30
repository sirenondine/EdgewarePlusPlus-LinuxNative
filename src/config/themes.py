# Copyright (C) 2024 Araten & Marigold
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

# Legacy Tkinter-era palettes, retained only as data: the GTK config window and
# Wayland popups use GTK CSS / the system theme. Resolved by items._resolve_theme.

from dataclasses import dataclass


@dataclass
class Theme:
    fg: str
    bg: str
    active_bg: str
    disabled_bg: str
    trough: str
    transparent_bg: str
    tab_bg: str
    tab_frame_bg: str
    button_fg: str
    text_fg: str
    text_bg: str
    check_select: str
    font: str = "IosevkaTerm NF"
    font_size: int = 9
    title_font: str = "IosevkaTerm NF"


THEMES = {
    "Original": Theme(fg="#e0def4", bg="#ce2b24", active_bg="#191724", disabled_bg="#100f18", trough="#e0def4", transparent_bg="#191724", tab_bg="#ebbcba", tab_frame_bg="#191724", button_fg="#100f18", text_fg="#e0def4", text_bg="#f4c0be", check_select="#ebbcba"),
    "Dark": Theme(fg="ghost white", bg="#282c34", active_bg="#282c34", disabled_bg="gray65", trough="#c8c8c8", transparent_bg="#f9fafe", tab_bg="#1b1d23", tab_frame_bg="#282c34", button_fg="ghost white", text_fg="ghost white", text_bg="#1b1d23", check_select="#1b1d23"),
    "The One": Theme(fg="#00ff41", bg="#282c34", active_bg="#1b1d23", disabled_bg="#37573d", trough="#009a22", transparent_bg="#00ff42", tab_bg="#1b1d23", tab_frame_bg="#282c34", button_fg="#00ff41", text_fg="#00ff41", text_bg="#1b1d23", check_select="#1b1d23", font="Consolas", font_size=8, title_font="Consolas"),
    "Ransom": Theme(fg="white", bg="#841212", active_bg="#841212", disabled_bg="573737", trough="#c8c8c8", transparent_bg="#fffffe", tab_bg="#5c0d0d", tab_frame_bg="#841212", button_fg="yellow", text_fg="black", text_bg="white", check_select="#5c0d0d", font="Arial", title_font="Arial Bold"),
    "Goth": Theme(fg="MediumPurple1", bg="#282c34", active_bg="#282c34", disabled_bg="#4b3757", trough="MediumOrchid2", transparent_bg="#ba9afe", tab_bg="#1b1d23", tab_frame_bg="#282c34", button_fg="MediumPurple1", text_fg="purple4", text_bg="MediumOrchid2", check_select="#1b1d23", font="Constantia", title_font="Constantia"),
    "Bimbo": Theme(fg="deep pink", bg="pink", active_bg="hot pink", disabled_bg="#bc7abf", trough="hot pink", transparent_bg="#ff3aa4", tab_bg="light pink", tab_frame_bg="pink", button_fg="deep pink", text_fg="magenta2", text_bg="light pink", check_select="light pink", font="Constantia", title_font="Constantia"),
}
