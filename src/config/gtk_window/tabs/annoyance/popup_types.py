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

from gi import require_version

require_version("Gtk", "4.0")
require_version("Adw", "1")
from gi.repository import Adw

from config.gtk_window.widgets import AdwSliderRow, AdwSwitchRow
from config.vars import Vars

FREQUENCY_TEXT = (
    "Dictates how often each popup type appears at runtime. These chances feed into "
    "nearly every other tab."
)
SINGLE_TEXT = (
    "Stops the rolling process once one type is picked, for a more consistent experience. "
    "Each popup's chance becomes a weight used to choose a single type."
)
IMAGE_TEXT = "The most common popup type. Every pack has these."
AUDIO_TEXT = "No visuals, sound only."
VIDEO_TEXT = "Like image popups, but animated and with sound."
WEBSITE_TEXT = "Opens a website in your default browser when a roll passes."
PROMPT_TEXT = "Requires you to type a prompt before the popup can be closed."
SUBLIMINAL_TEXT = "Briefly flashes a caption on screen."
NOTIFICATION_TEXT = "Uses your operating system's notification feature."


class PopupTypesTab(Adw.PreferencesPage):
    def __init__(self, vars: Vars) -> None:
        super().__init__()

        freq = Adw.PreferencesGroup(title="General Popup Frequency", description=FREQUENCY_TEXT)
        self.add(freq)
        freq.add(AdwSliderRow("Popup Timer Delay (ms)", vars.delay, 10, 60000))
        freq.add(AdwSwitchRow("Single Popup Per Roll", vars.single_mode, subtitle=SINGLE_TEXT))
        freq.add(AdwSwitchRow(
            "Escalation Mode", vars.escalation,
            subtitle="Popups speed up the more you close them, and ease off when you stop."))

        image = Adw.PreferencesGroup(title="Image Popups", description=IMAGE_TEXT)
        self.add(image)
        image.add(AdwSliderRow("Image Popup Chance (%)", vars.image_chance, 0, 100))
        image.add(AdwSliderRow("Max Image Popups", vars.max_image, 1, 100))

        audio = Adw.PreferencesGroup(title="Audio Popups", description=AUDIO_TEXT)
        self.add(audio)
        audio.add(AdwSliderRow("Audio Popup Chance (%)", vars.audio_chance, 0, 100))
        audio.add(AdwSliderRow("Max Audio Popups", vars.max_audio, 1, 50))
        audio.add(AdwSliderRow("Audio Volume (%)", vars.audio_volume, 1, 100))
        audio.add(AdwSliderRow("Fade-In Duration (ms)", vars.fade_in_duration, 0, 10000))
        audio.add(AdwSliderRow("Fade-Out Duration (ms)", vars.fade_out_duration, 0, 10000))

        video = Adw.PreferencesGroup(title="Video Popups", description=VIDEO_TEXT)
        self.add(video)
        video.add(AdwSliderRow("Video Popup Chance (%)", vars.video_chance, 0, 100))
        video.add(AdwSliderRow("Max Video Popups", vars.max_video, 1, 50))
        video.add(AdwSliderRow("Video Volume (%)", vars.video_volume, 0, 100))

        website = Adw.PreferencesGroup(title="Website Popups", description=WEBSITE_TEXT)
        self.add(website)
        website.add(AdwSliderRow("Website Frequency (%)", vars.web_chance, 0, 100))
        website.add(AdwSwitchRow("Closing a popup opens a web page", vars.web_on_popup_close))

        prompt = Adw.PreferencesGroup(title="Prompt Popups", description=PROMPT_TEXT)
        self.add(prompt)
        prompt.add(AdwSliderRow("Prompt Chance (%)", vars.prompt_chance, 0, 100))
        prompt.add(AdwSliderRow("Allowed Prompt Mistakes", vars.prompt_max_mistakes, 0, 150))

        sub = Adw.PreferencesGroup(title="Subliminal Popups", description=SUBLIMINAL_TEXT)
        self.add(sub)
        sub.add(AdwSliderRow("Subliminal Popup Chance (%)", vars.subliminal_chance, 0, 100))
        sub.add(AdwSliderRow("Subliminal Popup Length (ms)", vars.subliminal_timeout, 1, 1000))
        sub.add(AdwSliderRow("Subliminal Popup Opacity (%)", vars.subliminal_opacity, 1, 100))

        notif = Adw.PreferencesGroup(title="Notification Popups", description=NOTIFICATION_TEXT)
        self.add(notif)
        notif.add(AdwSliderRow("Notification Chance (%)", vars.notification_chance, 0, 100))
        notif.add(AdwSliderRow("Notification Image Chance (%)", vars.notification_image_chance, 0, 100))
