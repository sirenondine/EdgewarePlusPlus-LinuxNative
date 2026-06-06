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

"""Censor engine for the denial overhaul.

Pure-PIL image censoring (blur / pixelate / black bars) plus optional in-image
caption burning, with an optional NudeNet/ONNX region detector so only the
explicit parts get covered. No GTK here so it stays unit-testable and runs on
the popup worker thread.

The ML path is fully optional: if `nudenet` (or its model) is unavailable,
`detect_regions` returns None and callers censor the whole image instead.
"""

import logging
import random
import threading
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from paths import Assets, Data

Region = tuple[int, int, int, int]  # (x, y, w, h) in pixel coords

STYLES = ("blur", "pixelate", "bars", "mixed")

# User-facing body parts -> the NudeNet 3.x detector classes that map to them.
# Covered variants are included so a part stays hidden even when clothed. Each
# part has its own censor chance (see config censorPart*), rolled per detection.
# Parts/classes not listed here (face, armpits, …) are never censored.
PART_CLASSES: dict[str, set[str]] = {
    "breasts": {"FEMALE_BREAST_EXPOSED", "FEMALE_BREAST_COVERED", "MALE_BREAST_EXPOSED"},
    "female_genitals": {"FEMALE_GENITALIA_EXPOSED", "FEMALE_GENITALIA_COVERED"},
    "male_genitals": {"MALE_GENITALIA_EXPOSED"},
    "buttocks": {"BUTTOCKS_EXPOSED", "BUTTOCKS_COVERED"},
    "anus": {"ANUS_EXPOSED", "ANUS_COVERED"},
    "belly": {"BELLY_EXPOSED", "BELLY_COVERED"},
    "armpits": {"ARMPITS_EXPOSED", "ARMPITS_COVERED"},
    "feet": {"FEET_EXPOSED", "FEET_COVERED"},
    "face": {"FACE_FEMALE", "FACE_MALE"},  # for anonymity / eye-bar censoring
}
# Stable display order for the UI sliders.
PART_KEYS = ("breasts", "female_genitals", "male_genitals", "buttocks", "anus", "belly", "armpits", "feet", "face")


def eye_strip(box: Region, height_scale: float = 1.0) -> Region:
    """A coarse, axis-aligned eye-bar sub-region of a face box (upper-middle band).
    Fallback for when the landmark model is unavailable. `height_scale` grows/shrinks
    the bar around the eye line."""
    x, y, w, h = box
    base_h = h * 0.30 * max(0.05, height_scale)
    center_y = y + h * 0.37  # ~eye line
    top = max(y, int(center_y - base_h / 2))
    return (x, top, w, max(1, int(base_h)))


# iBUG-68 eye landmark indices.
_LEFT_EYE = range(36, 42)
_RIGHT_EYE = range(42, 48)


def _get_landmarks():
    """Lazily load the bundled PFLD 68-point landmark ONNX session. Returns None
    (and latches) if onnxruntime or the model file is unavailable."""
    global _landmarks, _landmarks_failed
    if _landmarks is not None or _landmarks_failed:
        return _landmarks
    with _landmarks_lock:
        if _landmarks is not None or _landmarks_failed:
            return _landmarks
        try:
            import onnxruntime as ort

            _landmarks = ort.InferenceSession(str(Assets.FACE_LANDMARKS), providers=["CPUExecutionProvider"])
            logging.info("censor: face-landmark model loaded")
        except Exception as e:
            _landmarks_failed = True
            logging.warning(f"censor: landmark model unavailable, eye bar falls back to a flat strip ({e})")
    return _landmarks


def face_landmarks(image: Image.Image, box: Region):
    """Run PFLD on a face box; return 68 (x,y) landmark points in image pixel
    coords, or None if the model is unavailable / inference fails."""
    session = _get_landmarks()
    if session is None:
        return None
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return None
    try:
        import numpy as np

        crop = image.convert("RGB").crop((x, y, x + w, y + h)).resize((112, 112))
        arr = np.asarray(crop, dtype=np.float32) / 255.0
        arr = np.transpose(arr, (2, 0, 1))[None]  # NCHW
        out = session.run(None, {session.get_inputs()[0].name: arr})[0][0]
        pts = out.reshape(-1, 2)  # 68 x (x,y), normalised to the crop
        return [(x + float(px) * w, y + float(py) * h) for px, py in pts]
    except Exception as e:
        logging.warning(f"censor: landmark inference failed ({e})")
        return None


def draw_eye_bar(image: Image.Image, face_box: Region, height_scale: float = 1.0) -> None:
    """Draw a black eye-censor bar over a face. Uses landmark eye corners (rotated
    to the eye line, beta-protection style) when available, else a flat strip.
    `height_scale` scales the bar thickness."""
    import math

    height_scale = max(0.05, height_scale)
    pts = face_landmarks(image, face_box)
    draw = ImageDraw.Draw(image)
    if not pts:
        x, y, w, h = eye_strip(face_box, height_scale)  # fallback: axis-aligned bar
        draw.rectangle((x, y, x + w, y + h), fill=(0, 0, 0, 255))
        return

    lx = sum(pts[i][0] for i in _LEFT_EYE) / 6
    ly = sum(pts[i][1] for i in _LEFT_EYE) / 6
    rx = sum(pts[i][0] for i in _RIGHT_EYE) / 6
    ry = sum(pts[i][1] for i in _RIGHT_EYE) / 6
    cx, cy = (lx + rx) / 2, (ly + ry) / 2
    dx, dy = rx - lx, ry - ly
    eye_dist = math.hypot(dx, dy) or 1.0
    angle = math.atan2(dy, dx)

    # Vertical eye spread sets bar thickness; extend length past both eyes.
    eye_ys = [pts[i][1] for i in list(_LEFT_EYE) + list(_RIGHT_EYE)]
    spread = max(eye_ys) - min(eye_ys)
    half_len = eye_dist * 0.95
    half_thick = max(spread * 1.4, eye_dist * 0.32) * height_scale

    ux, uy = math.cos(angle), math.sin(angle)        # along the eye line
    px, py = -math.sin(angle), math.cos(angle)        # perpendicular
    corners = [
        (cx - ux * half_len - px * half_thick, cy - uy * half_len - py * half_thick),
        (cx + ux * half_len - px * half_thick, cy + uy * half_len - py * half_thick),
        (cx + ux * half_len + px * half_thick, cy + uy * half_len + py * half_thick),
        (cx - ux * half_len + px * half_thick, cy - uy * half_len + py * half_thick),
    ]
    draw.polygon(corners, fill=(0, 0, 0, 255))
_CLASS_TO_PART = {cls: part for part, classes in PART_CLASSES.items() for cls in classes}


def is_covered(cls: str) -> bool:
    """True if the NudeNet class is a 'covered' (clothed) variant."""
    return cls.endswith("_COVERED")

_DETECT_THRESHOLD = 0.2  # recall over precision: better to over-censor an intimate part
_BOX_PADDING = 0.18  # dilate each detection by this fraction so partial boxes fully cover


def part_for_class(cls: str) -> Optional[str]:
    """Map a NudeNet class name to a censor part key, or None if not censorable."""
    return _CLASS_TO_PART.get(cls)

_detector = None
_detector_lock = threading.Lock()
_detector_failed = False  # latch: don't retry an import/model that already failed

_landmarks = None
_landmarks_lock = threading.Lock()
_landmarks_failed = False

_anime = None
_anime_lock = threading.Lock()
_anime_failed = False

# 01miku/anime-nsfw-segm-yolo26 (medium, 1280px). MIT repo / AGPL ultralytics export.
_ANIME_URL = "https://huggingface.co/01miku/anime-nsfw-segm-yolo26/resolve/main/nsfw-anime-medium-x1280.onnx?download=true"
_ANIME_SIZE = 47600269  # expected bytes (sanity check after download)
_ANIME_INPUT = 1280
_ANIME_CONF = 0.25
_ANIME_IOU = 0.5
_ANIME_NAMES = {0: "anus", 1: "nipple", 2: "penis", 3: "vagina", 4: "female face", 5: "male face", 6: "pubic hair"}
_ANIME_TO_PART = {
    "nipple": "breasts",
    "vagina": "female_genitals",
    "pubic hair": "female_genitals",
    "penis": "male_genitals",
    "anus": "anus",
    "female face": "face",
    "male face": "face",
}


def is_available() -> bool:
    """True if the optional NudeNet dependency is importable (no model load)."""
    import importlib.util

    return importlib.util.find_spec("nudenet") is not None


def reset_detector() -> None:
    """Clear the cached detector + failure latch so a freshly-installed NudeNet is
    picked up without restarting Edgeware."""
    global _detector, _detector_failed
    with _detector_lock:
        _detector, _detector_failed = None, False


def install_detector() -> tuple[bool, str]:
    """Pip-install NudeNet into the running interpreter. Blocking; call off the UI
    thread. Returns (ok, message)."""
    import importlib
    import subprocess
    import sys

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "nudenet"],
            capture_output=True, text=True,
        )
    except Exception as e:
        return False, str(e)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "pip failed").strip().splitlines()
        return False, (tail[-1] if tail else "pip failed")[:200]
    importlib.invalidate_caches()
    reset_detector()
    return (is_available(), "Installed" if is_available() else "Installed, but import still fails")


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Detection (optional, lazy)
# ---------------------------------------------------------------------------
def _get_detector():
    """Lazily construct a single NudeDetector. Returns None (and latches) if the
    optional dependency or model is unavailable."""
    global _detector, _detector_failed
    if _detector is not None or _detector_failed:
        return _detector
    with _detector_lock:
        if _detector is not None or _detector_failed:
            return _detector
        try:
            from nudenet import NudeDetector

            _detector = NudeDetector()  # bundled 320 model; higher res tested worse
            logging.info("censor: NudeNet detector loaded")
        except Exception as e:
            _detector_failed = True
            logging.warning(f"censor: NudeNet unavailable, falling back to whole-image censor ({e})")
    return _detector


def _raw_detect(detector, image: Image.Image) -> Optional[list[dict]]:
    """Run NudeNet on one PIL image (via a temp file). Returns raw detections or
    None on failure."""
    import os
    import tempfile

    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        image.convert("RGB").save(tmp)
        return detector.detect(tmp)
    except Exception as e:
        logging.warning(f"censor: detection failed ({e})")
        return None
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _dilate(box: Region, iw: int, ih: int) -> Region:
    """Grow a box by _BOX_PADDING on each side, clamped to the image."""
    x, y, w, h = box
    px, py = int(w * _BOX_PADDING), int(h * _BOX_PADDING)
    x0 = max(0, x - px)
    y0 = max(0, y - py)
    x1 = min(iw, x + w + px)
    y1 = min(ih, y + h + py)
    return (x0, y0, x1 - x0, y1 - y0)


def _overlaps(a: Region, b: Region) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax >= bx + bw or bx >= ax + aw or ay >= by + bh or by >= ay + ah)


def _union(a: Region, b: Region) -> Region:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = min(ax, bx), min(ay, by)
    x1, y1 = max(ax + aw, bx + bw), max(ay + ah, by + bh)
    return (x0, y0, x1 - x0, y1 - y0)


def _merge_same_part(regions: list[tuple[Region, str, bool]]) -> list[tuple[Region, str, bool]]:
    """Collapse overlapping boxes of the same part into their bounding union (a
    region is 'covered' only if every box merged into it was covered)."""
    merged: list[list] = []  # [box, part, covered]
    for box, part, covered in regions:
        for m in merged:
            if m[1] == part and _overlaps(m[0], box):
                m[0] = _union(m[0], box)
                m[2] = m[2] and covered
                break
        else:
            merged.append([box, part, covered])
    return [(m[0], m[1], m[2]) for m in merged]


def detect_regions(image: Image.Image) -> Optional[list[tuple[Region, str, bool]]]:
    """Detect censorable regions. Returns a list of ((x,y,w,h), part_key, covered)
    triples, an empty list when nothing is found, or None when detection is
    unavailable (caller should censor the whole image). `covered` is True for
    clothed detections. The caller decides whether to censor each region using its
    part's chance + covered preference.

    Detection runs on the image AND its horizontal mirror; boxes are unioned. The
    single 320 model is pose-sensitive and often catches a breast/part on one side
    or orientation but not the other, so the flip pass markedly improves recall."""
    detector = _get_detector()
    if detector is None:
        return None

    from PIL import ImageOps

    iw, ih = image.size
    passes = [(image, False), (ImageOps.mirror(image), True)]
    raw: list[dict] = []
    any_ok = False
    for img, flipped in passes:
        res = _raw_detect(detector, img)
        if res is None:
            continue
        any_ok = True
        for det in res:
            if flipped:
                box = det.get("box")
                if box and len(box) == 4:
                    x, y, w, h = box
                    det = {**det, "box": [iw - (x + w), y, w, h]}  # mirror x back
            raw.append(det)
    if not any_ok:
        return None  # both passes errored -> treat as unavailable

    regions: list[tuple[Region, str, bool]] = []
    for det in raw:
        cls = det.get("class", "")
        part = part_for_class(cls)
        if part and det.get("score", 0) >= _DETECT_THRESHOLD:
            box = det.get("box")
            if box and len(box) == 4:
                x, y, w, h = (int(v) for v in box)
                regions.append((_dilate((x, y, w, h), iw, ih), part, is_covered(cls)))
    return _merge_same_part(regions)


def union_detections(a, b):
    """Merge two detection lists (e.g. NudeNet + anime), unioning overlapping
    same-part boxes. None inputs are treated as empty."""
    return _merge_same_part((a or []) + (b or []))


# ---------------------------------------------------------------------------
# Anime detector (optional, YOLOv8-seg, downloaded on demand)
# ---------------------------------------------------------------------------
def anime_available() -> bool:
    """True if the anime model file is present and onnxruntime is importable."""
    import importlib.util

    return Data.ANIME_MODEL.is_file() and importlib.util.find_spec("onnxruntime") is not None


def reset_anime() -> None:
    global _anime, _anime_failed
    with _anime_lock:
        _anime, _anime_failed = None, False


def install_anime_model() -> tuple[bool, str]:
    """Download the anime detector model to Data.ANIME_MODEL. Blocking; call off
    the UI thread. Returns (ok, message)."""
    import os

    try:
        import requests

        Data.ANIME_MODEL.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(Data.ANIME_MODEL) + ".part"
        with requests.get(_ANIME_URL, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
        if os.path.getsize(tmp) < _ANIME_SIZE * 0.9:
            os.unlink(tmp)
            return False, "Download incomplete"
        os.replace(tmp, Data.ANIME_MODEL)
    except Exception as e:
        return False, str(e)[:200]
    reset_anime()
    return (anime_available(), "Installed" if anime_available() else "Downloaded, but not loadable")


def _get_anime():
    """Lazily load the anime ONNX session. Returns None (and latches) if missing."""
    global _anime, _anime_failed
    if _anime is not None or _anime_failed:
        return _anime
    with _anime_lock:
        if _anime is not None or _anime_failed:
            return _anime
        try:
            if not Data.ANIME_MODEL.is_file():
                raise FileNotFoundError("anime model not downloaded")
            import onnxruntime as ort

            _anime = ort.InferenceSession(str(Data.ANIME_MODEL), providers=["CPUExecutionProvider"])
            logging.info("censor: anime detector loaded")
        except Exception as e:
            _anime_failed = True
            logging.warning(f"censor: anime detector unavailable ({e})")
    return _anime


def _nms(boxes, scores, iou_thr: float):
    """Greedy per-array NMS. boxes: Nx4 xyxy. Returns kept indices (list)."""
    import numpy as np

    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1).clip(min=0) * (y2 - y1).clip(min=0)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        ovr = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[ovr <= iou_thr]
    return keep


def detect_anime_regions(image: Image.Image) -> Optional[list[tuple[Region, str, bool]]]:
    """Run the anime YOLOv8-seg detector. Returns ((x,y,w,h), part, covered=False)
    triples (covered always False — the model only flags visible parts), [] when
    nothing is found, or None when the model is unavailable."""
    session = _get_anime()
    if session is None:
        return None
    try:
        import numpy as np

        iw, ih = image.size
        size = _ANIME_INPUT
        im = image.convert("RGB")
        r = min(size / iw, size / ih)
        nw, nh = int(round(iw * r)), int(round(ih * r))
        padx, pady = (size - nw) // 2, (size - nh) // 2
        canvas = Image.new("RGB", (size, size), (114, 114, 114))
        canvas.paste(im.resize((nw, nh)), (padx, pady))
        arr = np.transpose(np.asarray(canvas, dtype=np.float32) / 255.0, (2, 0, 1))[None]

        out0 = session.run(None, {session.get_inputs()[0].name: arr})[0]  # [1, 4+nc+32, N]
        p = out0[0].T  # [N, 43]
        ncls = len(_ANIME_NAMES)
        scores = p[:, 4:4 + ncls]
        conf = scores.max(1)
        cls = scores.argmax(1)
        keep = conf >= _ANIME_CONF
        if not keep.any():
            return []
        p, conf, cls = p[keep], conf[keep], cls[keep]
        cx, cy, bw, bh = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
        x1 = (cx - bw / 2 - padx) / r
        y1 = (cy - bh / 2 - pady) / r
        x2 = (cx + bw / 2 - padx) / r
        y2 = (cy + bh / 2 - pady) / r
        xyxy = np.stack([x1, y1, x2, y2], 1)

        regions: list[tuple[Region, str, bool]] = []
        for c in np.unique(cls):
            part = _ANIME_TO_PART.get(_ANIME_NAMES.get(int(c), ""))
            if not part:
                continue
            mask = cls == c
            for idx in _nms(xyxy[mask], conf[mask], _ANIME_IOU):
                ax, ay, bx, by = xyxy[mask][idx]
                x, y = max(0, int(ax)), max(0, int(ay))
                w, h = int(bx - ax), int(by - ay)
                if w > 0 and h > 0:
                    regions.append((_dilate((x, y, w, h), iw, ih), part, False))
        return regions
    except Exception as e:
        logging.warning(f"censor: anime detection failed ({e})")
        return None


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------
def _effect_blur(image: Image.Image, box: Region, intensity: int) -> None:
    x, y, w, h = box
    region = image.crop((x, y, x + w, y + h))
    sigma = 2 + (intensity / 100) * 28  # 2..30
    region = region.filter(ImageFilter.GaussianBlur(sigma))
    image.paste(region, (x, y))


def _effect_pixelate(image: Image.Image, box: Region, intensity: int) -> None:
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return
    region = image.crop((x, y, x + w, y + h))
    # Higher intensity -> blockier. Shrink factor 4..40 of the box's long edge.
    factor = 4 + (intensity / 100) * 36
    sw = max(1, int(w / factor))
    sh = max(1, int(h / factor))
    region = region.resize((sw, sh), Image.BILINEAR).resize((w, h), Image.NEAREST)
    image.paste(region, (x, y))


def _effect_bars(image: Image.Image, box: Region, _intensity: int) -> None:
    x, y, w, h = box
    draw = ImageDraw.Draw(image)
    draw.rectangle((x, y, x + w, y + h), fill=(0, 0, 0, 255))


_EFFECTS = {"blur": _effect_blur, "pixelate": _effect_pixelate, "bars": _effect_bars}


def _mixed_pool(detected: bool) -> tuple[str, ...]:
    """Effect choices for 'mixed'. Over an AI-detected part, blur is excluded —
    blurring a small region barely censors it, so use only pixelate/bars there."""
    return ("pixelate", "bars") if detected else ("blur", "pixelate", "bars")


def _apply_one(image: Image.Image, box: Region, style: str, intensity: int, detected: bool = False) -> None:
    """Apply one censor effect to one box, resolving 'mixed' to a random effect."""
    effect = random.choice(_mixed_pool(detected)) if style == "mixed" else style
    _EFFECTS[effect](image, box, intensity)


def _synth_bars(width: int, height: int) -> list[Region]:
    """When 'bars' is requested with no detected regions, lay a few horizontal
    black censor strips across the image (classic redaction look)."""
    bars: list[Region] = []
    count = random.randint(2, 4)
    for _ in range(count):
        bh = int(height * random.uniform(0.06, 0.12))
        by = random.randint(0, max(0, height - bh))
        bars.append((0, by, width, bh))
    return bars


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(Assets.CENSOR_FONT), size)
    except Exception:
        try:
            return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Greedy word-wrap `text` to `max_w` pixels for `font`."""
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _draw_lines(draw: ImageDraw.ImageDraw, lines: list[str], font: ImageFont.FreeTypeFont,
                size: int, cx: float, cy: float) -> None:
    """Draw centred, stroked white lines stacked around vertical centre `cy`."""
    stroke = max(2, size // 10)
    line_h = size + stroke * 2 + 4
    y = cy - (line_h * len(lines)) / 2
    for text in lines:
        tw = draw.textlength(text, font=font)
        draw.text(
            (cx - tw / 2, y), text, font=font, fill=(255, 255, 255, 255),
            stroke_width=stroke, stroke_fill=(0, 0, 0, 255),
        )
        y += line_h


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int, max_h: int) -> tuple[ImageFont.FreeTypeFont, int, list[str]]:
    """Largest font (>=8px) whose word-wrapped text fits inside max_w × max_h.
    Returns (font, size, wrapped_lines)."""
    size = _clamp(max_h, 8, 64)
    while size >= 8:
        font = _load_font(size)
        lines = _wrap(draw, text, font, max_w)
        line_h = size + max(2, size // 10) * 2 + 4
        widest = max((draw.textlength(ln, font=font) for ln in lines), default=0)
        if widest <= max_w and line_h * len(lines) <= max_h:
            return font, size, lines
        size -= 2
    font = _load_font(8)
    return font, 8, _wrap(draw, text, font, max_w)


def _burn_caption(image: Image.Image, caption: str, regions: Optional[list[Region]] = None) -> None:
    """Burn the caption into the pixels, white with a black outline (Beta-Caption
    look). With `regions`, draw it centred over each censored box; otherwise place
    it bottom-centre over the whole image."""
    draw = ImageDraw.Draw(image)
    w, h = image.size

    valid = [r for r in regions or [] if r[2] > 0 and r[3] > 0]
    if valid:
        # One caption, on the largest region — overlapping boxes would double it.
        x, y, bw, bh = max(valid, key=lambda r: r[2] * r[3])
        font, size, lines = _fit_font(draw, caption, int(bw * 0.92), int(bh * 0.9))
        _draw_lines(draw, lines, font, size, x + bw / 2, y + bh / 2)
        return

    size = _clamp(int(w / 14), 14, 72)
    font = _load_font(size)
    lines = _wrap(draw, caption, font, int(w * 0.92))
    stroke = max(2, size // 10)
    line_h = size + stroke * 2 + 4
    cy = h - (line_h * len(lines)) / 2 - int(h * 0.04)
    _draw_lines(draw, lines, font, size, w / 2, cy)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def apply_censor(
    image: Image.Image,
    style: str = "blur",
    intensity: int = 60,
    regions: Optional[list[Region]] = None,
    caption: Optional[str] = None,
    invert: bool = False,
) -> Image.Image:
    """Censor `image` and return a same-size RGBA image.

    style: "blur" | "pixelate" | "bars" | "mixed".
    intensity: 0..100 (mosaic blockiness / blur sigma).
    regions: explicit boxes; None censors the whole image (and, for "bars",
        synthesises redaction strips).
    caption: optional text burned into the pixels.
    invert: reverse mode — censor the WHOLE image except `regions` (the selected
        parts stay sharp). Needs `regions`; with none it just censors everything.
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    intensity = _clamp(int(intensity), 0, 100)
    w, h = image.size
    if style not in STYLES:
        style = "blur"

    if invert:
        keep = [b for b in (regions or []) if b[2] > 0 and b[3] > 0]
        sharp = image.copy()
        _apply_one(image, (0, 0, w, h), style, intensity)  # censor everything
        for x, y, bw, bh in keep:  # then restore the selected parts
            image.paste(sharp.crop((x, y, x + bw, y + bh)), (x, y))
        if caption:
            _burn_caption(image, caption, keep)
        return image

    # Resolve the boxes to censor. `detected` (regions came from AI) restricts
    # 'mixed' to pixelate/bars per box.
    detected = regions is not None
    if regions is None:
        boxes = _synth_bars(w, h) if style == "bars" else [(0, 0, w, h)]
    else:
        boxes = [b for b in regions if b[2] > 0 and b[3] > 0]

    for box in boxes:
        _apply_one(image, box, style, intensity, detected=detected)

    if caption:
        _burn_caption(image, caption, regions)

    return image
