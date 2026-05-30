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

# Screen capture for the companion's optional vision awareness. Grabs the
# screen, downscales it and returns base64 JPEG for a vision-capable LLM.
# Blocking (subprocess + encode) — call from a worker thread.
#
# PRIVACY: this sends an image of the whole screen (including Edgeware's own
# popups and anything else open) to the configured backend. With a cloud
# backend that leaves the machine. It is off by default and danger-gated.

import base64
import io
import logging
import shutil
import subprocess


def available() -> bool:
    """Whether a supported screen-capture tool is present (Wayland: grim)."""
    return shutil.which("grim") is not None


def capture_screenshot(max_dim: int = 1024, quality: int = 70) -> str | None:
    """Capture the screen, downscale to fit max_dim, return base64 JPEG (no data
    URI prefix), or None on failure / no capture tool."""
    if not available():
        return None
    try:
        raw = subprocess.run(["grim", "-"], capture_output=True, timeout=5).stdout
        if not raw:
            return None
        from PIL import Image
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image.thumbnail((max_dim, max_dim))  # in place, keeps aspect
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=quality)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception as e:
        logging.warning(f"Companion screenshot capture failed: {e}")
        return None
