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
# PRIVACY: this sends an image of (preferably) the focused window — or, as a
# fallback, the whole screen — to the configured backend. With a cloud backend
# that leaves the machine. It is off by default and danger-gated.

import base64
import io
import logging
import os
import shutil
import subprocess
import time


def _encode(raw: bytes, max_dim: int, quality: int) -> str | None:
    """PNG/JPEG bytes -> downscaled base64 JPEG (no data URI prefix)."""
    if not raw:
        return None
    from PIL import Image
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    image.thumbnail((max_dim, max_dim))  # in place, keeps aspect
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def capture(max_dim: int = 1024, quality: int = 70) -> str | None:
    """Capture the focused window if possible (niri), else the whole screen."""
    return capture_window(max_dim, quality) or capture_screenshot(max_dim, quality)


def capture_window(max_dim: int = 1024, quality: int = 70) -> str | None:
    """Capture only the focused window via niri's built-in screenshot, which
    lands on the clipboard; read it back with wl-paste. Restores the previous
    text clipboard afterwards (best effort). None if niri/wl-clipboard absent."""
    if not (os.environ.get("NIRI_SOCKET") and shutil.which("wl-paste")):
        return None
    prev = None
    try:
        prev = subprocess.run(["wl-paste", "-n"], capture_output=True, timeout=2).stdout or None
    except Exception:
        pass
    try:
        subprocess.run(["niri", "msg", "action", "screenshot-window"], capture_output=True, timeout=3)
        time.sleep(0.15)  # let the clipboard populate
        raw = subprocess.run(["wl-paste", "--type", "image/png"], capture_output=True, timeout=3).stdout
        return _encode(raw, max_dim, quality)
    except Exception as e:
        logging.warning(f"Companion window capture failed: {e}")
        return None
    finally:
        if prev and shutil.which("wl-copy"):
            try:
                subprocess.run(["wl-copy"], input=prev, timeout=2)
            except Exception:
                pass


def capture_screenshot(max_dim: int = 1024, quality: int = 70) -> str | None:
    """Whole-screen fallback via grim. None if grim is absent."""
    if not shutil.which("grim"):
        return None
    try:
        raw = subprocess.run(["grim", "-"], capture_output=True, timeout=5).stdout
        return _encode(raw, max_dim, quality)
    except Exception as e:
        logging.warning(f"Companion screenshot capture failed: {e}")
        return None


def available() -> bool:
    """Whether any capture path is usable."""
    return bool(os.environ.get("NIRI_SOCKET") and shutil.which("wl-paste")) or shutil.which("grim") is not None


def encode_image_file(path, max_dim: int = 1024, quality: int = 70) -> str | None:
    """Encode an image file (e.g. a popup's media) to a downscaled base64 JPEG,
    or None on failure. Cheaper and more targeted than a full screenshot."""
    try:
        from PIL import Image
        image = Image.open(path).convert("RGB")
        image.thumbnail((max_dim, max_dim))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=quality)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception as e:
        logging.warning(f"Companion image encode failed ({path}): {e}")
        return None
