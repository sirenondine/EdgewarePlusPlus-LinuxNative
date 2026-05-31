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

# Optional AI companion. BYO inference backend (local Ollama by default, any
# OpenAI-compatible endpoint, or a no-network scripted fallback). See llm.py.

import logging
from pathlib import Path


def resolve_avatar(settings, pack, persona=None):
    """The companion's avatar image as a Path, or None. Used both for the
    on-screen bubble and as the icon on companion notifications.

    Priority: a user-set image (companion_avatar) overrides the pack's persona
    avatar (companion.json), which overrides the pack's own icon."""
    try:
        user = (getattr(settings, "companion_avatar", "") or "").strip()
        if user:
            p = Path(user).expanduser()
            if p.is_file():
                return p
        if persona is not None and getattr(persona, "avatar", None):
            p = pack.paths.root / persona.avatar
            if p.is_file():
                return p
        return getattr(pack, "icon", None)
    except Exception as e:
        logging.debug(f"avatar resolution failed: {e}")
        return None
