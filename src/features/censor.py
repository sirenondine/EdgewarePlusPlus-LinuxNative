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

_breasts = None
_breasts_lock = threading.Lock()
_breasts_failed = False
# Anzhc Breasts Seg v1 (1024n), exported to ONNX. Bundled. Full-breast instance
# segmentation (single class) — gives whole-breast masks vs the anime nipple.
_BREASTS_INPUT = 1024
_BREASTS_CONF = 0.3
_BREASTS_IOU = 0.5
_BREASTS_IDX_TO_PART = {0: "breasts"}

_face = None
_face_lock = threading.Lock()
_face_failed = False
# Anzhc Face Seg (1024n) -> ONNX, bundled. Full-face masks for the 'face' part.
_FACE_INPUT = 1024
_FACE_CONF = 0.3
_FACE_IOU = 0.5
_FACE_IDX_TO_PART = {0: "face"}

_body = None
_body_lock = threading.Lock()
_body_failed = False
# person_yolov8m-seg -> ONNX (~105 MB, not bundled; lives in Data). Whole-body
# silhouette for the 'body' part — best with Reverse (sharp body, blurred bg).
_BODY_INPUT = 640
_BODY_CONF = 0.3
_BODY_IOU = 0.5
_BODY_IDX_TO_PART = {0: "body"}

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
_ANIME_IDX_TO_PART = {i: _ANIME_TO_PART[n] for i, n in _ANIME_NAMES.items() if n in _ANIME_TO_PART}

# Bundled NudeNet YOLOv8-detect model (best.onnx, 320px, 18 classes). Replaces the
# old pip `nudenet` dependency: run directly via onnxruntime like the seg models.
_NUDENET_NAMES = {
    0: "FEMALE_GENITALIA_COVERED", 1: "FACE_FEMALE", 2: "BUTTOCKS_EXPOSED",
    3: "FEMALE_BREAST_EXPOSED", 4: "FEMALE_GENITALIA_EXPOSED", 5: "MALE_BREAST_EXPOSED",
    6: "ANUS_EXPOSED", 7: "FEET_EXPOSED", 8: "BELLY_COVERED", 9: "FEET_COVERED",
    10: "ARMPITS_COVERED", 11: "ARMPITS_EXPOSED", 12: "FACE_MALE", 13: "BELLY_EXPOSED",
    14: "MALE_GENITALIA_EXPOSED", 15: "ANUS_COVERED", 16: "FEMALE_BREAST_COVERED",
    17: "BUTTOCKS_COVERED",
}
_NUDENET_IDX_TO_PART = {i: part_for_class(n) for i, n in _NUDENET_NAMES.items() if part_for_class(n)}
_NUDENET_INPUT = 320
_NUDENET_CONF = 0.2
_NUDENET_IOU = 0.5


def is_available() -> bool:
    """True if the bundled NudeNet model + onnxruntime are present."""
    import importlib.util

    return Assets.NUDENET_MODEL.is_file() and importlib.util.find_spec("onnxruntime") is not None


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Detection (optional, lazy)
# ---------------------------------------------------------------------------
def _get_detector():
    """Lazily load the bundled NudeNet YOLOv8-detect ONNX session. Returns None
    (and latches) if onnxruntime or the model file is unavailable."""
    global _detector, _detector_failed
    if _detector is not None or _detector_failed:
        return _detector
    with _detector_lock:
        if _detector is not None or _detector_failed:
            return _detector
        try:
            import onnxruntime as ort

            _detector = ort.InferenceSession(str(Assets.NUDENET_MODEL), providers=["CPUExecutionProvider"])
            logging.info("censor: NudeNet detect model loaded")
        except Exception as e:
            _detector_failed = True
            logging.warning(f"censor: NudeNet unavailable, falling back to whole-image censor ({e})")
    return _detector


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
    session = _get_detector()
    if session is None:
        return None

    from PIL import ImageOps

    iw, ih = image.size
    out: list[tuple[Region, str, bool]] = []
    any_ok = False
    for img, flipped in ((image, False), (ImageOps.mirror(image), True)):
        try:
            res = _run_yolo_seg(session, img, _NUDENET_INPUT, _NUDENET_IDX_TO_PART,
                                _NUDENET_CONF, _NUDENET_IOU, False, seg=False, names=_NUDENET_NAMES)
        except Exception as e:
            logging.warning(f"censor: detection failed ({e})")
            continue
        any_ok = True
        for box, part, covered in res:
            if flipped:
                x, y, w, h = box
                box = (iw - (x + w), y, w, h)  # mirror x back
            out.append((box, part, covered))
    if not any_ok:
        return None  # both passes errored -> treat as unavailable
    return _merge_same_part(out)


def union_detections(a, b):
    """Merge two detection lists (e.g. NudeNet + anime), unioning overlapping
    same-part boxes. None inputs are treated as empty."""
    return _merge_same_part((a or []) + (b or []))


def prefer_masked(items):
    """In mask mode, drop box-only detections for any part that has a mask
    somewhere in the set — keep the precise shell, never render a plain square
    alongside it (e.g. a NudeNet armpit box next to the armpit-seg shell)."""
    masked_parts = {it[1] for it in items if len(it) > 3 and it[3] is not None}
    out = []
    for it in items:
        has_mask = len(it) > 3 and it[3] is not None
        if not has_mask and it[1] in masked_parts:
            continue
        out.append(it)
    return out


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


def _run_yolo_seg(session, image: Image.Image, size: int, idx_to_part: dict,
                  conf_thr: float, iou_thr: float, with_masks: bool,
                  seg: bool = True, names: Optional[dict] = None):
    """Generic YOLOv8/11 inference + decode. Returns ((x,y,w,h), part, covered)
    triples, or 4-tuples with a box-local boolean mask when `with_masks`. Shared by
    every detector. `idx_to_part` maps class index -> part; `seg` False = plain
    detect head (no mask coeffs); `names` (idx->class) sets covered via is_covered."""
    import numpy as np

    iw, ih = image.size
    r = min(size / iw, size / ih)
    nw, nh = int(round(iw * r)), int(round(ih * r))
    padx, pady = (size - nw) // 2, (size - nh) // 2
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    canvas.paste(image.convert("RGB").resize((nw, nh)), (padx, pady))
    arr = np.transpose(np.asarray(canvas, dtype=np.float32) / 255.0, (2, 0, 1))[None]

    out = session.run(None, {session.get_inputs()[0].name: arr})
    p = out[0][0].T  # [N, 4 + ncls (+32 mask coeffs when seg)]
    ncls = p.shape[1] - (4 + 32 if seg else 4)  # derive class count from the tensor
    if ncls < 1:
        return []
    scores = p[:, 4:4 + ncls]
    conf = scores.max(1)
    cls = scores.argmax(1)
    keep = conf >= conf_thr
    if not keep.any():
        return []
    p, conf, cls = p[keep], conf[keep], cls[keep]
    cx, cy, bw, bh = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
    x1 = (cx - bw / 2 - padx) / r
    y1 = (cy - bh / 2 - pady) / r
    x2 = (cx + bw / 2 - padx) / r
    y2 = (cy + bh / 2 - pady) / r
    xyxy = np.stack([x1, y1, x2, y2], 1)

    protos_flat = coeffs = cv2 = None
    if seg and with_masks and len(out) > 1:
        try:
            import cv2 as _cv2

            cv2 = _cv2
            protos = out[1][0]  # (32, mh, mw)
            pc, mh, mw = protos.shape
            protos_flat = protos.reshape(pc, -1)
            coeffs = p[:, 4 + ncls:4 + ncls + 32]
        except Exception:
            protos_flat = None

    regions = []
    for c in np.unique(cls):
        part = idx_to_part.get(int(c))
        if not part:
            continue
        covered = is_covered(names[int(c)]) if names else False
        cls_mask = cls == c
        cidx = np.where(cls_mask)[0]
        for idx in _nms(xyxy[cls_mask], conf[cls_mask], iou_thr):
            gi = int(cidx[idx])
            ax, ay, bx, by = xyxy[gi]
            x, y = max(0, int(ax)), max(0, int(ay))
            w, h = int(bx - ax), int(by - ay)
            if w <= 0 or h <= 0:
                continue
            dbox = _dilate((x, y, w, h), iw, ih)
            if with_masks:
                bmask = None
                if protos_flat is not None:
                    try:
                        m = 1.0 / (1.0 + np.exp(-(coeffs[gi] @ protos_flat)))
                        m = m.reshape(mh, mw)
                        m = cv2.resize(m, (size, size))
                        m = m[pady:size - pady, padx:size - padx]
                        m = cv2.resize(m, (iw, ih))
                        # Smooth the soft mask before thresholding so the shell
                        # outline is rounded, not squiggly/pixel-stepped.
                        k = (max(1, int(min(iw, ih) * 0.01)) | 1)  # odd kernel ~1% of short side
                        m = cv2.GaussianBlur(m, (k, k), 0)
                        dx, dy, dw, dh = dbox
                        bmask = (m[dy:dy + dh, dx:dx + dw] > 0.5)
                    except Exception:
                        bmask = None
                regions.append((dbox, part, covered, bmask))
            else:
                regions.append((dbox, part, covered))
    return regions


def detect_anime_regions(image: Image.Image, with_masks: bool = False):
    """Run the anime YOLOv8-seg detector (7 NSFW classes). See `_run_yolo_seg`.
    Returns None when the model is unavailable."""
    session = _get_anime()
    if session is None:
        return None
    try:
        return _run_yolo_seg(session, image, _ANIME_INPUT, _ANIME_IDX_TO_PART, _ANIME_CONF, _ANIME_IOU, with_masks)
    except Exception as e:
        logging.warning(f"censor: anime detection failed ({e})")
        return None


def _get_breasts():
    """Lazily load the bundled full-breast seg model. Returns None (and latches)
    if onnxruntime or the model file is unavailable."""
    global _breasts, _breasts_failed
    if _breasts is not None or _breasts_failed:
        return _breasts
    with _breasts_lock:
        if _breasts is not None or _breasts_failed:
            return _breasts
        try:
            import onnxruntime as ort

            _breasts = ort.InferenceSession(str(Assets.BREASTS_MODEL), providers=["CPUExecutionProvider"])
            logging.info("censor: breast-seg model loaded")
        except Exception as e:
            _breasts_failed = True
            logging.warning(f"censor: breast-seg model unavailable ({e})")
    return _breasts


def breasts_available() -> bool:
    import importlib.util

    return Assets.BREASTS_MODEL.is_file() and importlib.util.find_spec("onnxruntime") is not None


def detect_breast_regions(image: Image.Image, with_masks: bool = False):
    """Run the bundled full-breast seg model (single class -> 'breasts'). Gives
    whole-breast masks. Returns None when unavailable."""
    session = _get_breasts()
    if session is None:
        return None
    try:
        return _run_yolo_seg(session, image, _BREASTS_INPUT, _BREASTS_IDX_TO_PART, _BREASTS_CONF, _BREASTS_IOU, with_masks)
    except Exception as e:
        logging.warning(f"censor: breast detection failed ({e})")
        return None


def _get_face():
    global _face, _face_failed
    if _face is not None or _face_failed:
        return _face
    with _face_lock:
        if _face is not None or _face_failed:
            return _face
        try:
            import onnxruntime as ort

            _face = ort.InferenceSession(str(Assets.FACE_SEG), providers=["CPUExecutionProvider"])
            logging.info("censor: face-seg model loaded")
        except Exception as e:
            _face_failed = True
            logging.warning(f"censor: face-seg model unavailable ({e})")
    return _face


def face_seg_available() -> bool:
    import importlib.util

    return Assets.FACE_SEG.is_file() and importlib.util.find_spec("onnxruntime") is not None


def detect_face_regions(image: Image.Image, with_masks: bool = False):
    """Bundled full-face seg (single class -> 'face'). Returns None when unavailable."""
    session = _get_face()
    if session is None:
        return None
    try:
        return _run_yolo_seg(session, image, _FACE_INPUT, _FACE_IDX_TO_PART, _FACE_CONF, _FACE_IOU, with_masks)
    except Exception as e:
        logging.warning(f"censor: face detection failed ({e})")
        return None


def _get_body():
    global _body, _body_failed
    if _body is not None or _body_failed:
        return _body
    with _body_lock:
        if _body is not None or _body_failed:
            return _body
        try:
            if not Data.BODY_MODEL.is_file():
                raise FileNotFoundError("body model not present")
            import onnxruntime as ort

            _body = ort.InferenceSession(str(Data.BODY_MODEL), providers=["CPUExecutionProvider"])
            logging.info("censor: body-seg model loaded")
        except Exception as e:
            _body_failed = True
            logging.warning(f"censor: body-seg model unavailable ({e})")
    return _body


def body_available() -> bool:
    import importlib.util

    return Data.BODY_MODEL.is_file() and importlib.util.find_spec("onnxruntime") is not None


def detect_body_regions(image: Image.Image, with_masks: bool = False):
    """Whole-body seg (single class -> 'body'); best with reverse mode. None when
    the model isn't present (it is large and not bundled)."""
    session = _get_body()
    if session is None:
        return None
    try:
        return _run_yolo_seg(session, image, _BODY_INPUT, _BODY_IDX_TO_PART, _BODY_CONF, _BODY_IOU, with_masks)
    except Exception as e:
        logging.warning(f"censor: body detection failed ({e})")
        return None


# Generic registry for bundled single-class seg models: key -> (path, input,
# idx->part). Adding a model is one entry here + a toggle; no bespoke loader.
_SEG_REGISTRY = {
    "armpits": (Assets.ARMPIT_SEG, 640, {0: "armpits"}),
    "belly": (Assets.BELLY_SEG, 640, {0: "belly"}),
    "mouth": (Assets.MOUTH_SEG, 640, {0: "mouth"}),
    "underwear": (Assets.UNDERWEAR_SEG, 640, {0: "underwear"}),
    "socks": (Assets.SOCKS_SEG, 640, {0: "socks"}),
    "skin": (Assets.SKIN_SEG, 640, {0: "skin"}),
}
_seg_sessions: dict = {}
_seg_failed: set = set()
_seg_reg_lock = threading.Lock()


def seg_available(key: str) -> bool:
    import importlib.util

    spec = _SEG_REGISTRY.get(key)
    return bool(spec) and spec[0].is_file() and importlib.util.find_spec("onnxruntime") is not None


def _get_seg_model(key: str):
    if key in _seg_sessions:
        return _seg_sessions[key]
    if key in _seg_failed:
        return None
    with _seg_reg_lock:
        if key in _seg_sessions:
            return _seg_sessions[key]
        if key in _seg_failed:
            return None
        try:
            path = _SEG_REGISTRY[key][0]
            if not path.is_file():
                raise FileNotFoundError(key)
            import onnxruntime as ort

            _seg_sessions[key] = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            logging.info(f"censor: seg model '{key}' loaded")
        except Exception as e:
            _seg_failed.add(key)
            logging.warning(f"censor: seg model '{key}' unavailable ({e})")
            return None
    return _seg_sessions[key]


def detect_seg(key: str, image: Image.Image, with_masks: bool = False):
    """Run a registered single-class seg model. None when unavailable."""
    session = _get_seg_model(key)
    if session is None:
        return None
    _, size, idx_to_part = _SEG_REGISTRY[key]
    try:
        return _run_yolo_seg(session, image, size, idx_to_part, 0.3, 0.5, with_masks)
    except Exception as e:
        logging.warning(f"censor: seg '{key}' detection failed ({e})")
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
    # Higher intensity -> blockier. Keep at least ~8 blocks across so small
    # regions don't collapse to one giant pixel.
    factor = 4 + (intensity / 100) * 36
    sw = min(w, max(8, int(w / factor)))
    sh = min(h, max(8, int(h / factor)))
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


# Burned-caption fonts (all OFL / bundled). "random" picks one per popup.
CAPTION_FONTS = {
    "dejavu": Assets.CENSOR_FONT,
    "anton": Assets.FONT_ANTON,
    "bebas": Assets.FONT_BEBAS,
    "fredoka": Assets.FONT_FREDOKA,
    "pacifico": Assets.FONT_PACIFICO,
}
CAPTION_FONT_KEYS = ("dejavu", "anton", "bebas", "fredoka", "pacifico")


def resolve_font(key: Optional[str]):
    """Resolve a caption-font key to a file path. 'random' picks one per call."""
    if key == "random":
        key = random.choice(CAPTION_FONT_KEYS)
    return CAPTION_FONTS.get(key or "dejavu", Assets.CENSOR_FONT)


def _load_font(size: int, font_path=None) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(font_path or Assets.CENSOR_FONT), size)
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


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int, max_h: int, font_path=None) -> tuple[ImageFont.FreeTypeFont, int, list[str]]:
    """Largest font (>=8px) whose word-wrapped text fits inside max_w × max_h.
    Returns (font, size, wrapped_lines)."""
    size = _clamp(max_h, 8, 64)
    while size >= 8:
        font = _load_font(size, font_path)
        lines = _wrap(draw, text, font, max_w)
        line_h = size + max(2, size // 10) * 2 + 4
        widest = max((draw.textlength(ln, font=font) for ln in lines), default=0)
        if widest <= max_w and line_h * len(lines) <= max_h:
            return font, size, lines
        size -= 2
    font = _load_font(8, font_path)
    return font, 8, _wrap(draw, text, font, max_w)


def choose_caption(captions: list[str], box: Optional[Region], image_size: tuple[int, int]) -> Optional[str]:
    """Pick a caption sized to the censor area: smaller boxes prefer shorter
    phrases so the burned text stays legible instead of shrinking to nothing.
    `box` None (whole-image censor) allows any length."""
    if not captions:
        return None
    if not box:
        return random.choice(captions)
    iw = max(1, image_size[0])
    frac = box[2] / iw  # censor width as a fraction of the image
    budget = max(6, int(frac * 60))  # ~60 chars at full width, scaling down with the box
    pool = [c for c in captions if len(c) <= budget] or [min(captions, key=len)]
    return random.choice(pool)


def _burn_caption(image: Image.Image, caption: str, regions: Optional[list[Region]] = None, font_path=None) -> None:
    """Burn the caption into the pixels, white with a black outline (Beta-Caption
    look). With `regions`, draw it centred over each censored box; otherwise place
    it bottom-centre over the whole image."""
    draw = ImageDraw.Draw(image)
    w, h = image.size

    valid = [r for r in regions or [] if r[2] > 0 and r[3] > 0]
    if valid:
        # One caption, on the largest region — overlapping boxes would double it.
        x, y, bw, bh = max(valid, key=lambda r: r[2] * r[3])
        font, size, lines = _fit_font(draw, caption, int(bw * 0.92), int(bh * 0.9), font_path)
        _draw_lines(draw, lines, font, size, x + bw / 2, y + bh / 2)
        return

    size = _clamp(int(w / 14), 14, 72)
    font = _load_font(size, font_path)
    lines = _wrap(draw, caption, font, int(w * 0.92))
    stroke = max(2, size // 10)
    line_h = size + stroke * 2 + 4
    cy = h - (line_h * len(lines)) / 2 - int(h * 0.04)
    _draw_lines(draw, lines, font, size, w / 2, cy)


def _region_map(image: Image.Image, pairs, use_mask: bool):
    """Boolean HxW map of which pixels a set of (box, mask) pairs covers — the
    exact mask shape when use_mask and a mask exists, else the full box."""
    import numpy as np

    amap = np.zeros((image.height, image.width), dtype=bool)
    for (x, y, bw, bh), m in pairs:
        if use_mask and m is not None:
            mm = np.asarray(m, dtype=bool)
            hh, ww = min(mm.shape[0], image.height - y), min(mm.shape[1], image.width - x)
            if hh > 0 and ww > 0:
                amap[y:y + hh, x:x + ww] |= mm[:hh, :ww]
        else:
            amap[y:y + bh, x:x + bw] = True
    return amap


def _composite(base: Image.Image, work: Image.Image, amap) -> Image.Image:
    """Take `work` pixels where `amap` is true, `base` elsewhere."""
    import numpy as np

    b, w = np.array(base), np.array(work)
    b[amap] = w[amap]
    return Image.fromarray(b, "RGBA")


_GLOW_PRESETS = {
    "white": (255, 255, 255), "red": (255, 40, 40), "pink": (255, 80, 180),
    "cyan": (60, 220, 255), "green": (60, 255, 90), "gold": (255, 200, 40),
}


def dominant_color(image: Image.Image) -> tuple:
    """The image's boldest colour: the dominant hue weighted by vividness
    (saturation × value), returned fully saturated. Falls back to white for
    near-greyscale images."""
    import numpy as np

    hsv = np.asarray(image.convert("RGB").resize((64, 64)).convert("HSV"))
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    weight = (s.astype(np.float32) / 255.0) * (v.astype(np.float32) / 255.0)
    if float(weight.sum()) < 1.0:
        return (255, 255, 255)
    hue = int(np.bincount(h.ravel(), weights=weight.ravel(), minlength=256).argmax())
    import colorsys

    r, g, b = colorsys.hsv_to_rgb(hue / 255.0, 1.0, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def _resolve_glow_color(spec, image: Image.Image) -> tuple:
    """Resolve a glow-colour spec to RGB. 'auto' -> image's boldest colour;
    a preset name -> its colour; an (r,g,b) tuple -> itself."""
    if isinstance(spec, (tuple, list)) and len(spec) == 3:
        return tuple(int(c) for c in spec)
    if spec == "auto":
        return dominant_color(image)
    return _GLOW_PRESETS.get(spec or "white", (255, 255, 255))


def _draw_glow(image: Image.Image, pairs, use_mask: bool, color=(255, 255, 255), thickness: float = 1.0) -> None:
    """Composite a soft bright outline around each region — the mask contour when
    available (needs cv2), else the box rectangle. Stroke width scales with the
    IMAGE's short side (not the box) so it looks consistent across images/parts."""
    import numpy as np

    cv2 = None
    if use_mask:
        try:
            import cv2 as _cv2
            cv2 = _cv2
        except Exception:
            cv2 = None

    # Image-relative stroke: ~1.2% of the short side, scaled by the thickness setting.
    stroke = max(2, int(min(image.width, image.height) * 0.012 * max(0.05, thickness)))
    radius = max(1, stroke // 4)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rgba = (*color, 255)
    for (x, y, bw, bh), m in pairs:
        if use_mask and m is not None and cv2 is not None:
            full = np.zeros((image.height, image.width), dtype=np.uint8)
            mm = np.asarray(m, dtype=bool)
            hh, ww = min(mm.shape[0], image.height - y), min(mm.shape[1], image.width - x)
            full[y:y + hh, x:x + ww] = mm[:hh, :ww].astype(np.uint8) * 255
            contours, _ = cv2.findContours(full, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                pts = [(int(p[0][0]), int(p[0][1])) for p in c]
                if len(pts) >= 2:
                    draw.line(pts + [pts[0]], fill=rgba, width=stroke)
        else:
            draw.rectangle((x, y, x + bw, y + bh), outline=rgba, width=stroke)
    layer = layer.filter(ImageFilter.GaussianBlur(radius))  # tight glow, not a fog
    image.alpha_composite(layer)


# Display name burned on a region when "label body parts" is on.
_PART_DISPLAY = {
    "breasts": "breasts", "female_genitals": "pussy", "male_genitals": "cock",
    "buttocks": "ass", "anus": "anus", "belly": "belly", "armpits": "armpit",
    "feet": "feet", "face": "face", "body": "body", "mouth": "mouth",
    "underwear": "underwear", "socks": "socks", "skin": "skin",
}


def part_label(part: str) -> str:
    return _PART_DISPLAY.get(part, part)


def _draw_part_labels(image: Image.Image, pairs, labels, font_path) -> None:
    """Burn each region's body-part name in small text in the box's upper-left
    corner. Font size is image-relative so it's consistent across regions."""
    draw = ImageDraw.Draw(image)
    size = _clamp(int(min(image.width, image.height) * 0.035), 11, 26)
    font = _load_font(size, font_path)
    stroke = max(1, size // 8)
    for (x, y, bw, bh), _m in pairs:
        if not labels:
            break
        text = labels.pop(0)
        if not text or bw <= 0 or bh <= 0:
            continue
        font, size, lines = _fit_font(draw, text, int(bw * 0.9), int(bh * 0.5), font_path)
        _draw_lines(draw, lines, font, size, x + bw / 2, y + bh / 2)


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
    font: Optional[str] = None,
    masks: Optional[list] = None,
    mask_shape: bool = False,
    glow: bool = False,
    glow_color="auto",
    glow_thickness: float = 1.0,
    labels: Optional[list] = None,
    label_parts: bool = False,
) -> Image.Image:
    """Censor `image` and return a same-size RGBA image.

    style: "blur" | "pixelate" | "bars" | "mixed".
    intensity: 0..100 (mosaic blockiness / blur sigma).
    regions: explicit boxes; None censors the whole image (and, for "bars",
        synthesises redaction strips).
    caption: optional text burned into the pixels.
    invert: reverse mode — censor the WHOLE image except `regions` (the selected
        parts stay sharp). Needs `regions`; with none it just censors everything.
    masks: per-region box-local boolean masks (parallel to `regions`), or None.
    mask_shape: censor/keep the exact mask shape instead of the bounding box.
    glow: draw a soft bright outline around the regions (mask contour or box).
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    intensity = _clamp(int(intensity), 0, 100)
    w, h = image.size
    if style not in STYLES:
        style = "blur"
    font_path = resolve_font(font)  # resolved once so 'random' is stable for this popup
    # Derive the glow colour from the pristine image, before censoring alters it.
    glow_rgb = _resolve_glow_color(glow_color, image) if glow else None

    ms = masks or ([None] * len(regions) if regions else [])
    lbls = labels or ([None] * len(regions) if regions else [])
    triples = [(b, m, lb) for b, m, lb in zip(regions or [], ms, lbls) if b[2] > 0 and b[3] > 0]
    pairs = [(b, m) for b, m, _ in triples]
    pair_labels = [lb for _, _, lb in triples]

    if invert:
        sharp = image.copy()
        _apply_one(image, (0, 0, w, h), style, intensity)  # censor everything
        if pairs:  # restore the selected parts (mask shape or box)
            image = _composite(image, sharp, _region_map(sharp, pairs, mask_shape))
        if glow and pairs:
            _draw_glow(image, pairs, mask_shape, glow_rgb, glow_thickness)
        if label_parts and pairs:
            _draw_part_labels(image, pairs, list(pair_labels), font_path)
        if caption:
            _burn_caption(image, caption, [b for b, _ in pairs], font_path)
        return image

    detected = regions is not None  # AI regions restrict 'mixed' to pixelate/bars
    if regions is None:
        for box in (_synth_bars(w, h) if style == "bars" else [(0, 0, w, h)]):
            _apply_one(image, box, style, intensity, detected=detected)
    elif mask_shape and any(m is not None for _, m in pairs):
        work = image.copy()
        for box, _ in pairs:
            _apply_one(work, box, style, intensity, detected=detected)
        image = _composite(image, work, _region_map(image, pairs, True))
    else:
        for box, _ in pairs:
            _apply_one(image, box, style, intensity, detected=detected)

    if glow and pairs:
        _draw_glow(image, pairs, mask_shape, glow_rgb, glow_thickness)
    if label_parts and pairs:
        _draw_part_labels(image, pairs, list(pair_labels), font_path)
    if caption:
        _burn_caption(image, caption, [b for b, _ in pairs] if regions is not None else None, font_path)

    return image
