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

from config.gtk_window.widgets import ConfigMessage, ConfigRow, ConfigScale, ConfigSection, ConfigToggle
from config.vars import Vars

FREQUENCY_TEXT = (
    "This tab dictates the frequency of every popup type you will see during runtime, "
    "which in turn affects nearly every other tab in the config window!"
)
SINGLE_TEXT = (
    "\"Single Popup Per Roll\" stops the \"rolling process\" once one type is picked. "
    "This allows for a much more consistent experience."
)
IMAGE_TEXT = "Image popups are the most common type of popup. Every single pack will have these."
AUDIO_TEXT = "Audio popups have no visuals attached, focusing only on sound."
VIDEO_TEXT = "Video popups are functionally the same as image popups, just animated and with sound."
WEBSITE_TEXT = "Opens up a website in your default browser whenever a roll is passed."
PROMPT_TEXT = "Prompt popups require you to repeat a prompt via a text box before they can be closed."
NOTIFICATION_TEXT = "Notification popups use your operating system's notification feature."
SUBLIMINAL_TEXT = "Subliminal message popups briefly flash a caption on screen."


class PopupTypesTab(Gtk.ScrolledWindow):
    def __init__(self, vars: Vars) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_child(vbox)

        # Frequency
        freq_section = ConfigSection("General Popup Frequency", FREQUENCY_TEXT)
        vbox.append(freq_section)
        freq_section.append(ConfigScale("Popup Timer Delay (ms)", vars.delay, 10, 60000))
        freq_section.append(ConfigMessage(SINGLE_TEXT))
        single = ConfigToggle("Single Popup Per Roll", vars.single_mode,
            tooltip="The chance of a popup appearing is used as a weight to choose a single popup type.")
        freq_section.append(single)

        # Image
        img_section = ConfigSection("Image Popups", IMAGE_TEXT)
        vbox.append(img_section)
        img_section.append(ConfigScale("Image Popup Chance (%)", vars.image_chance, 0, 100))

        # Audio
        audio_section = ConfigSection("Audio Popups", AUDIO_TEXT)
        vbox.append(audio_section)
        r1 = ConfigRow()
        audio_section.append(r1)
        r1.append(ConfigScale("Audio Popup Chance (%)", vars.audio_chance, 0, 100))
        r1.append(ConfigScale("Max Audio Popups", vars.max_audio, 1, 50))
        r1.append(ConfigScale("Audio Volume (%)", vars.audio_volume, 1, 100))
        r2 = ConfigRow()
        audio_section.append(r2)
        r2.append(ConfigScale("Fade-In Duration (ms)", vars.fade_in_duration, 0, 10000))
        r2.append(ConfigScale("Fade-Out Duration (ms)", vars.fade_out_duration, 0, 10000))

        # Video
        vid_section = ConfigSection("Video Popups", VIDEO_TEXT)
        vbox.append(vid_section)
        vr = ConfigRow()
        vid_section.append(vr)
        vr.append(ConfigScale("Video Popup Chance (%)", vars.video_chance, 0, 100))
        vr.append(ConfigScale("Max Video Popups", vars.max_video, 1, 50))
        vr.append(ConfigScale("Video Volume (%)", vars.video_volume, 0, 100))

        # Website
        web_section = ConfigSection("Website Popups", WEBSITE_TEXT)
        vbox.append(web_section)
        wr = ConfigRow()
        web_section.append(wr)
        wr.append(ConfigScale("Website Freq (%)", vars.web_chance, 0, 100))
        web_section.append(ConfigToggle("Popup close opens web page", vars.web_on_popup_close))

        # Prompt
        prompt_section = ConfigSection("Prompt Popups", PROMPT_TEXT)
        vbox.append(prompt_section)
        pr = ConfigRow()
        prompt_section.append(pr)
        pr.append(ConfigScale("Prompt Chance (%)", vars.prompt_chance, 0, 100))
        pr.append(ConfigScale("Prompt Mistakes", vars.prompt_max_mistakes, 0, 150))

        # Subliminal
        sub_section = ConfigSection("Subliminal Popups", SUBLIMINAL_TEXT)
        vbox.append(sub_section)
        sr = ConfigRow()
        sub_section.append(sr)
        sr.append(ConfigScale("Subliminal Popup Chance (%)", vars.subliminal_chance, 0, 100))
        sr.append(ConfigScale("Subliminal Popup Length (ms)", vars.subliminal_timeout, 1, 1000))
        sr.append(ConfigScale("Subliminal Popup Opacity (%)", vars.subliminal_opacity, 1, 100))

        # Notification
        notif_section = ConfigSection("Notification Popups", NOTIFICATION_TEXT)
        vbox.append(notif_section)
        nr = ConfigRow()
        notif_section.append(nr)
        nr.append(ConfigScale("Notification Chance (%)", vars.notification_chance, 0, 100))
        nr.append(ConfigScale("Notification Image Chance (%)", vars.notification_image_chance, 0, 100))
