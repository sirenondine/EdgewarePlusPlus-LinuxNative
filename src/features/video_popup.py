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

from pathlib import Path
from typing import Callable

from config.settings import Settings
from features.gtk_media import stop_media, video_widget
from features.popup import Popup
from pack import Pack
from state import State


class VideoPopup(Popup):
    vibration_open_event = "video_open"
    vibration_close_event = "video_close"
    vibration_continuous_key = "video"

    def __init__(self, settings: Settings, pack: Pack, state: State, media: Path | None = None, on_close: Callable[[], None] | None = None) -> None:
        self.media = media or pack.random_video()
        if not self.should_init(settings, state):
            return
        super().__init__(settings, pack, state, on_close)

        from videoprops import get_video_properties  # deferred (~12ms)
        properties = get_video_properties(self.media)
        self.compute_geometry(properties["width"], properties["height"])

        video, self._media_file = video_widget(
            self.media, self.width, self.height, loop=True, volume=self.settings.video_volume / 100,
            blur=self.denial, hardware_acceleration=self.settings.video_hardware_acceleration,
        )
        self.set_media_widget(video)

        self.init_finish()

    def should_init(self, settings: Settings, state: State) -> bool:
        if state.video_number < settings.max_video and self.media:
            state.video_number += 1
            return True
        return False

    def close(self) -> None:
        stop_media(self._media_file)
        super().close()
        self.state.video_number -= 1
