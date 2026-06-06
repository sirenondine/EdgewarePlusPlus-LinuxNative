import unittest

import tests._path  # noqa: F401

from PIL import Image

from features import censor


def solid(size=(120, 120), color=(40, 80, 160, 255)) -> Image.Image:
    return Image.new("RGBA", size, color)


class ApplyCensorShapeTest(unittest.TestCase):
    def test_each_style_same_size_rgba(self):
        for style in censor.STYLES:
            out = censor.apply_censor(solid(), style, 60)
            self.assertEqual(out.size, (120, 120))
            self.assertEqual(out.mode, "RGBA")

    def test_unknown_style_falls_back_to_blur(self):
        out = censor.apply_censor(solid(), "nonsense", 60)
        self.assertEqual(out.size, (120, 120))

    def test_intensity_out_of_range_does_not_crash(self):
        for intensity in (-50, 0, 100, 9999):
            out = censor.apply_censor(solid(), "pixelate", intensity)
            self.assertEqual(out.size, (120, 120))

    def test_converts_non_rgba_input(self):
        rgb = Image.new("RGB", (64, 64), (10, 20, 30))
        out = censor.apply_censor(rgb, "blur", 50)
        self.assertEqual(out.mode, "RGBA")


class RegionsTest(unittest.TestCase):
    def test_bars_censors_only_given_region(self):
        img = solid(color=(200, 100, 50, 255))
        out = censor.apply_censor(img, "bars", 50, regions=[(20, 20, 40, 40)])
        # Inside the box -> black; outside -> untouched.
        self.assertEqual(out.getpixel((40, 40)), (0, 0, 0, 255))
        self.assertEqual(out.getpixel((0, 0)), (200, 100, 50, 255))
        self.assertEqual(out.getpixel((119, 119)), (200, 100, 50, 255))

    def test_empty_regions_leaves_image_untouched(self):
        img = solid(color=(12, 34, 56, 255))
        out = censor.apply_censor(img, "bars", 50, regions=[])
        self.assertEqual(out.getpixel((60, 60)), (12, 34, 56, 255))

    def test_zero_size_region_ignored(self):
        img = solid(color=(12, 34, 56, 255))
        out = censor.apply_censor(img, "pixelate", 50, regions=[(10, 10, 0, 0)])
        self.assertEqual(out.getpixel((60, 60)), (12, 34, 56, 255))


class ChooseCaptionTest(unittest.TestCase):
    CAPS = ["no", "good beta~", "this is a much longer denial caption indeed"]

    def test_small_box_picks_short(self):
        # ~10% width -> budget 6 chars -> only "no" qualifies.
        self.assertEqual(censor.choose_caption(self.CAPS, (0, 0, 100, 100), (1000, 1000)), "no")

    def test_large_box_allows_long(self):
        picks = {censor.choose_caption(self.CAPS, (0, 0, 1000, 800), (1000, 1000)) for _ in range(40)}
        self.assertIn(self.CAPS[2], picks)  # long caption reachable on a big box

    def test_no_box_any_length(self):
        picks = {censor.choose_caption(self.CAPS, None, (1000, 1000)) for _ in range(40)}
        self.assertEqual(picks, set(self.CAPS))

    def test_empty_returns_none(self):
        self.assertIsNone(censor.choose_caption([], (0, 0, 50, 50), (100, 100)))

    def test_falls_back_to_shortest_when_none_fit(self):
        self.assertEqual(censor.choose_caption(["abcdefghij", "abcdefgh"], (0, 0, 10, 10), (1000, 1000)), "abcdefgh")


class CaptionFontTest(unittest.TestCase):
    def test_resolve_known_keys(self):
        from paths import Assets
        self.assertEqual(censor.resolve_font("anton"), Assets.FONT_ANTON)
        self.assertEqual(censor.resolve_font("pacifico"), Assets.FONT_PACIFICO)

    def test_resolve_unknown_and_none_fall_back_to_dejavu(self):
        from paths import Assets
        self.assertEqual(censor.resolve_font("nope"), Assets.CENSOR_FONT)
        self.assertEqual(censor.resolve_font(None), Assets.CENSOR_FONT)

    def test_random_returns_a_bundled_font(self):
        picks = {censor.resolve_font("random") for _ in range(40)}
        valid = {censor.CAPTION_FONTS[k] for k in censor.CAPTION_FONT_KEYS}
        self.assertTrue(picks.issubset(valid))

    def test_every_bundled_font_loads(self):
        for key in censor.CAPTION_FONT_KEYS:
            font = censor._load_font(24, censor.CAPTION_FONTS[key])
            self.assertIsNotNone(font)

    def test_apply_censor_with_font_key_burns(self):
        img = solid(size=(240, 240), color=(0, 0, 0, 255))
        out = censor.apply_censor(img, "blur", 0, caption="GOOD BETA", font="anton")
        changed = any(out.getpixel((x, y)) != (0, 0, 0, 255)
                      for y in range(150, 240) for x in range(0, 240, 4))
        self.assertTrue(changed)


class CaptionTest(unittest.TestCase):
    def test_caption_changes_pixels(self):
        img = solid(size=(240, 240), color=(0, 0, 0, 255))
        out = censor.apply_censor(img, "blur", 0, caption="GOOD BETA")
        # Some non-black pixels (the white text/outline) now exist near the bottom.
        changed = any(
            out.getpixel((x, y)) != (0, 0, 0, 255)
            for y in range(180, 240)
            for x in range(0, 240, 4)
        )
        self.assertTrue(changed)

    def test_caption_drawn_over_region_not_bottom(self):
        img = solid(size=(240, 240), color=(120, 120, 120, 255))
        box = (40, 40, 160, 120)
        out = censor.apply_censor(img, "bars", 50, regions=[box], caption="HI")
        # White text pixels appear inside the censored box…
        in_box = any(
            out.getpixel((x, y))[0] > 200
            for y in range(45, 155, 3)
            for x in range(45, 195, 3)
        )
        self.assertTrue(in_box)
        # …and the bottom strip stays untouched grey (no caption dumped there).
        bottom_clean = all(
            out.getpixel((x, 235)) == (120, 120, 120, 255) for x in range(0, 240, 8)
        )
        self.assertTrue(bottom_clean)

    def test_no_caption_keeps_solid(self):
        img = solid(size=(240, 240), color=(0, 0, 0, 255))
        out = censor.apply_censor(img, "bars", 50, regions=[], caption=None)
        changed = any(
            out.getpixel((x, y)) != (0, 0, 0, 255)
            for y in range(180, 240)
            for x in range(0, 240, 4)
        )
        self.assertFalse(changed)


class MixedPoolTest(unittest.TestCase):
    def test_detected_excludes_blur(self):
        self.assertEqual(set(censor._mixed_pool(True)), {"pixelate", "bars"})

    def test_whole_image_includes_blur(self):
        self.assertIn("blur", censor._mixed_pool(False))


class ReverseTest(unittest.TestCase):
    def test_invert_keeps_region_sharp_censors_rest(self):
        img = solid(size=(120, 120), color=(200, 120, 60, 255))
        keep = (40, 40, 40, 40)
        out = censor.apply_censor(img, "bars", 50, regions=[keep], invert=True)
        # Kept region stays original; everything else is blacked out.
        self.assertEqual(out.getpixel((60, 60)), (200, 120, 60, 255))
        self.assertEqual(out.getpixel((5, 5)), (0, 0, 0, 255))
        self.assertEqual(out.getpixel((110, 110)), (0, 0, 0, 255))

    def test_invert_no_regions_censors_everything(self):
        img = solid(size=(80, 80), color=(10, 20, 30, 255))
        out = censor.apply_censor(img, "bars", 50, regions=[], invert=True)
        self.assertEqual(out.getpixel((40, 40)), (0, 0, 0, 255))


class MergeTest(unittest.TestCase):
    def test_overlaps(self):
        self.assertTrue(censor._overlaps((0, 0, 10, 10), (5, 5, 10, 10)))
        self.assertFalse(censor._overlaps((0, 0, 10, 10), (20, 20, 5, 5)))

    def test_union_bounding_box(self):
        self.assertEqual(censor._union((0, 0, 10, 10), (5, 5, 10, 10)), (0, 0, 15, 15))

    def test_merge_same_part_unions_overlap(self):
        out = censor._merge_same_part([
            ((0, 0, 10, 10), "breasts", False),
            ((5, 5, 10, 10), "breasts", True),
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], (0, 0, 15, 15))
        self.assertFalse(out[0][2])  # covered only if ALL merged boxes were covered

    def test_merge_keeps_different_parts_separate(self):
        out = censor._merge_same_part([
            ((0, 0, 10, 10), "breasts", False),
            ((2, 2, 10, 10), "buttocks", False),
        ])
        self.assertEqual(len(out), 2)


class UnionTest(unittest.TestCase):
    def test_union_merges_overlapping_same_part(self):
        a = [((0, 0, 20, 20), "breasts", False)]
        b = [((5, 5, 20, 20), "breasts", False)]
        out = censor.union_detections(a, b)
        self.assertEqual(len(out), 1)

    def test_union_keeps_distinct(self):
        a = [((0, 0, 10, 10), "breasts", False)]
        b = [((80, 80, 10, 10), "anus", False)]
        self.assertEqual(len(censor.union_detections(a, b)), 2)

    def test_union_handles_none(self):
        a = [((0, 0, 10, 10), "breasts", False)]
        self.assertEqual(len(censor.union_detections(None, a)), 1)
        self.assertEqual(len(censor.union_detections(a, None)), 1)
        self.assertEqual(censor.union_detections(None, None), [])


class _FakeAnime:
    """Fake YOLOv8-seg session: one nipple detection at a fixed letterbox box."""
    def get_inputs(self):
        import types
        return [types.SimpleNamespace(name="images")]

    def run(self, _outputs, _feed):
        import numpy as np
        out = np.zeros((1, 43, 1), dtype=np.float32)
        # 100x100 image -> letterbox r=12.8, pad 0; orig box (10,10,20,20) -> centre (256,256), 256x256
        out[0, 0, 0], out[0, 1, 0], out[0, 2, 0], out[0, 3, 0] = 256, 256, 256, 256
        out[0, 4 + 1, 0] = 0.9  # class 1 = nipple
        return [out]


class AnimeDetectTest(unittest.TestCase):
    def test_nms_suppresses_overlap(self):
        import numpy as np
        boxes = np.array([[0, 0, 10, 10], [1, 1, 10, 10], [50, 50, 60, 60]], dtype=np.float32)
        scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)
        keep = censor._nms(boxes, scores, 0.5)
        self.assertEqual(set(keep), {0, 2})  # the 0.8 box overlaps the 0.9 one -> dropped

    def test_class_mapping(self):
        self.assertEqual(censor._ANIME_TO_PART["nipple"], "breasts")
        self.assertEqual(censor._ANIME_TO_PART["vagina"], "female_genitals")
        self.assertEqual(censor._ANIME_TO_PART["penis"], "male_genitals")
        self.assertEqual(censor._ANIME_TO_PART["female face"], "face")

    def test_decode_maps_nipple_to_breasts_box(self):
        saved, savedf = censor._anime, censor._anime_failed
        censor._anime, censor._anime_failed = _FakeAnime(), False
        try:
            out = censor.detect_anime_regions(solid(size=(100, 100)))
        finally:
            censor._anime, censor._anime_failed = saved, savedf
        self.assertEqual(len(out), 1)
        box, part, covered = out[0]
        self.assertEqual(part, "breasts")
        self.assertFalse(covered)
        # Box decoded back near (10,10,20,20), then dilated -> contains that region.
        x, y, w, h = box
        self.assertLessEqual(x, 10)
        self.assertGreaterEqual(x + w, 30)

    def test_returns_none_when_unavailable(self):
        saved, savedf = censor._anime, censor._anime_failed
        censor._anime, censor._anime_failed = None, True
        try:
            self.assertIsNone(censor.detect_anime_regions(solid()))
        finally:
            censor._anime, censor._anime_failed = saved, savedf


class EyeBarTest(unittest.TestCase):
    def test_landmarks_none_when_model_unavailable(self):
        saved_s, saved_f = censor._landmarks, censor._landmarks_failed
        censor._landmarks, censor._landmarks_failed = None, True
        try:
            self.assertIsNone(censor.face_landmarks(solid(), (0, 0, 50, 50)))
        finally:
            censor._landmarks, censor._landmarks_failed = saved_s, saved_f

    def test_eye_strip_height_scales(self):
        base = censor.eye_strip((0, 0, 100, 200))
        tall = censor.eye_strip((0, 0, 100, 200), 2.0)
        short = censor.eye_strip((0, 0, 100, 200), 0.5)
        self.assertGreater(tall[3], base[3])
        self.assertLess(short[3], base[3])

    def test_draw_eye_bar_fallback_strip_when_no_landmarks(self):
        saved_s, saved_f = censor._landmarks, censor._landmarks_failed
        censor._landmarks, censor._landmarks_failed = None, True
        try:
            img = solid(size=(120, 120), color=(200, 100, 50, 255))
            face = (20, 20, 80, 80)
            censor.draw_eye_bar(img, face)
            # Fallback draws a black strip in the eye band; corners stay original.
            sx, sy, sw, sh = censor.eye_strip(face)
            self.assertEqual(img.getpixel((sx + sw // 2, sy + sh // 2)), (0, 0, 0, 255))
            self.assertEqual(img.getpixel((0, 0)), (200, 100, 50, 255))
        finally:
            censor._landmarks, censor._landmarks_failed = saved_s, saved_f


class PartMappingTest(unittest.TestCase):
    def test_known_classes_map_to_parts(self):
        self.assertEqual(censor.part_for_class("FEMALE_BREAST_EXPOSED"), "breasts")
        self.assertEqual(censor.part_for_class("FEMALE_BREAST_COVERED"), "breasts")
        self.assertEqual(censor.part_for_class("BUTTOCKS_COVERED"), "buttocks")
        self.assertEqual(censor.part_for_class("MALE_GENITALIA_EXPOSED"), "male_genitals")
        self.assertEqual(censor.part_for_class("FEMALE_GENITALIA_COVERED"), "female_genitals")
        self.assertEqual(censor.part_for_class("ARMPITS_EXPOSED"), "armpits")

    def test_face_classes_map_to_face(self):
        self.assertEqual(censor.part_for_class("FACE_FEMALE"), "face")
        self.assertEqual(censor.part_for_class("FACE_MALE"), "face")

    def test_non_censorable_classes_return_none(self):
        self.assertIsNone(censor.part_for_class("UNKNOWN_CLASS"))
        self.assertIsNone(censor.part_for_class(""))

    def test_eye_strip_is_upper_band_full_width(self):
        x, y, w, h = censor.eye_strip((10, 100, 80, 200))
        self.assertEqual(x, 10)
        self.assertEqual(w, 80)               # full face width
        self.assertGreater(y, 100)            # below the top of the face
        self.assertLess(h, 200)               # shorter than the face

    def test_every_part_key_has_classes(self):
        for key in censor.PART_KEYS:
            self.assertIn(key, censor.PART_CLASSES)
            self.assertTrue(censor.PART_CLASSES[key])


class _FakeDetector:
    def __init__(self, results, once=False):
        self._results = results
        self._once = once  # detection runs original + mirror; once=True answers only the first
        self._calls = 0

    def detect(self, _path):
        self._calls += 1
        if self._once and self._calls > 1:
            return []
        return self._results


class DetectRegionsTest(unittest.TestCase):
    def _run(self, results, size=(100, 100), once=True):
        saved_d, saved_f = censor._detector, censor._detector_failed
        censor._detector, censor._detector_failed = _FakeDetector(results, once=once), False
        try:
            return censor.detect_regions(solid(size=size))
        finally:
            censor._detector, censor._detector_failed = saved_d, saved_f

    def test_flip_pass_unions_mirrored_detection(self):
        # A centred box maps onto itself under horizontal mirror, so the two passes
        # union into a single region (proves the flip pass + merge run).
        out = self._run(
            [{"class": "FEMALE_BREAST_EXPOSED", "score": 0.9, "box": [40, 10, 20, 30]}],
            once=False,
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][1], "breasts")

    def test_filters_threshold_and_non_parts_and_tags_part(self):
        out = self._run([
            {"class": "FEMALE_BREAST_EXPOSED", "score": 0.9, "box": [10, 10, 20, 20]},
            {"class": "UNKNOWN_CLASS", "score": 0.9, "box": [0, 0, 5, 5]},        # not a part
            {"class": "BUTTOCKS_COVERED", "score": 0.1, "box": [30, 30, 10, 10]},  # below threshold
        ])
        self.assertEqual(len(out), 1)
        box, part, covered = out[0]
        self.assertEqual(part, "breasts")
        self.assertFalse(covered)
        # box dilated by 18% (3px each side) and clamped to the image.
        self.assertEqual(box, (7, 7, 26, 26))

    def test_covered_flag_set_for_clothed_classes(self):
        out = self._run([{"class": "FEMALE_GENITALIA_COVERED", "score": 0.9, "box": [10, 10, 20, 20]}])
        _box, part, covered = out[0]
        self.assertEqual(part, "female_genitals")
        self.assertTrue(covered)

    def test_dilation_clamps_to_image_bounds(self):
        out = self._run([{"class": "MALE_GENITALIA_EXPOSED", "score": 0.9, "box": [0, 0, 100, 100]}])
        box, part, _covered = out[0]
        self.assertEqual(part, "male_genitals")
        self.assertEqual(box, (0, 0, 100, 100))

    def test_detect_returns_none_when_detector_unavailable(self):
        saved_detector, saved_failed = censor._detector, censor._detector_failed
        censor._detector, censor._detector_failed = None, True  # simulate missing dep
        try:
            self.assertIsNone(censor.detect_regions(solid()))
        finally:
            censor._detector, censor._detector_failed = saved_detector, saved_failed


if __name__ == "__main__":
    unittest.main()
