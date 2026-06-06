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


class PartLabelTest(unittest.TestCase):
    def test_part_label_map(self):
        self.assertEqual(censor.part_label("female_genitals"), "pussy")
        self.assertEqual(censor.part_label("breasts"), "breasts")
        self.assertEqual(censor.part_label("unknown"), "unknown")

    def test_labels_burned_on_region(self):
        img = solid(size=(200, 200), color=(0, 0, 0, 255))
        box = (40, 40, 120, 120)
        out = censor.apply_censor(img, "blur", 0, regions=[box], masks=[None],
                                  labels=["pussy"], label_parts=True)
        # White label text appears inside the region.
        found = any(out.getpixel((x, y))[0] > 150
                    for y in range(45, 155, 3) for x in range(45, 155, 3))
        self.assertTrue(found)


class GlowThicknessTest(unittest.TestCase):
    def test_thicker_glow_covers_more(self):
        box = (40, 40, 30, 30)
        def glow_pixels(thick):
            img = solid(size=(300, 300), color=(0, 0, 0, 255))
            out = censor.apply_censor(img, "bars", 50, regions=[box], masks=[None],
                                      glow=True, glow_color="white", glow_thickness=thick)
            return sum(1 for y in range(0, 300, 2) for x in range(0, 300, 2)
                       if out.getpixel((x, y)) != (0, 0, 0, 255))
        self.assertGreater(glow_pixels(3.0), glow_pixels(0.5))


class GlowColorTest(unittest.TestCase):
    def test_dominant_color_of_red_image(self):
        img = solid(size=(64, 64), color=(220, 20, 20, 255))
        r, g, b = censor.dominant_color(img)
        self.assertGreater(r, 180)
        self.assertLess(g, 80)
        self.assertLess(b, 80)

    def test_dominant_color_greyscale_falls_back_white(self):
        self.assertEqual(censor.dominant_color(solid(color=(128, 128, 128, 255))), (255, 255, 255))

    def test_resolve_presets_and_tuple_and_auto(self):
        from PIL import Image
        self.assertEqual(censor._resolve_glow_color("red", solid()), (255, 40, 40))
        self.assertEqual(censor._resolve_glow_color((1, 2, 3), solid()), (1, 2, 3))
        self.assertEqual(censor._resolve_glow_color("bogus", solid()), (255, 255, 255))
        auto = censor._resolve_glow_color("auto", solid(color=(10, 200, 10, 255)))
        self.assertGreater(auto[1], auto[0])  # green channel dominant

    def test_glow_uses_color(self):
        img = solid(size=(100, 100), color=(0, 0, 0, 255))
        box = (30, 30, 40, 40)
        red = censor.apply_censor(img.copy(), "bars", 50, regions=[box], masks=[None], glow=True, glow_color="red")
        # A red glow tints pixels red (r noticeably above b); white glow would not.
        found = any((px := red.getpixel((x, y)))[0] > px[2] + 5
                    for y in range(0, 100, 2) for x in range(0, 100, 2))
        self.assertTrue(found)


class PreferMaskedTest(unittest.TestCase):
    def test_box_dropped_when_masked_same_part_overlaps(self):
        import numpy as np
        m = np.ones((20, 20), dtype=bool)
        items = [
            ((0, 0, 20, 20), "breasts", False, None),   # box-only (NudeNet)
            ((2, 2, 20, 20), "breasts", False, m),       # masked (seg) overlapping
        ]
        out = censor.prefer_masked(items)
        self.assertEqual(len(out), 1)
        self.assertIsNotNone(out[0][3])  # the masked one survives

    def test_box_kept_when_no_overlapping_mask(self):
        items = [((0, 0, 10, 10), "breasts", False, None),
                 ((80, 80, 10, 10), "anus", False, None)]
        self.assertEqual(len(censor.prefer_masked(items)), 2)

    def test_box_kept_when_mask_is_different_part(self):
        import numpy as np
        items = [((0, 0, 20, 20), "breasts", False, None),
                 ((2, 2, 20, 20), "female_genitals", False, np.ones((20, 20), bool))]
        self.assertEqual(len(censor.prefer_masked(items)), 2)


class MaskShapeTest(unittest.TestCase):
    def _mask(self, h, w, fill):
        import numpy as np
        m = np.zeros((h, w), dtype=bool)
        m[:fill, :fill] = True
        return m

    def test_mask_shape_censors_only_mask_pixels(self):
        img = solid(size=(100, 100), color=(200, 100, 50, 255))
        box = (20, 20, 60, 60)
        mask = self._mask(60, 60, 30)  # only top-left 30x30 of the box
        out = censor.apply_censor(img, "bars", 50, regions=[box], masks=[mask], mask_shape=True)
        self.assertEqual(out.getpixel((25, 25)), (0, 0, 0, 255))          # inside mask -> censored
        self.assertEqual(out.getpixel((70, 70)), (200, 100, 50, 255))     # in box, outside mask -> kept
        self.assertEqual(out.getpixel((5, 5)), (200, 100, 50, 255))       # outside box -> kept

    def test_mask_none_falls_back_to_box(self):
        img = solid(size=(100, 100), color=(200, 100, 50, 255))
        box = (20, 20, 60, 60)
        out = censor.apply_censor(img, "bars", 50, regions=[box], masks=[None], mask_shape=True)
        self.assertEqual(out.getpixel((70, 70)), (0, 0, 0, 255))          # whole box censored

    def test_glow_changes_pixels_outside_box(self):
        img = solid(size=(100, 100), color=(20, 20, 20, 255))
        box = (30, 30, 40, 40)
        plain = censor.apply_censor(img.copy(), "bars", 50, regions=[box], masks=[None], glow=False)
        glowed = censor.apply_censor(img.copy(), "bars", 50, regions=[box], masks=[None], glow=True)
        diff = any(plain.getpixel((x, y)) != glowed.getpixel((x, y))
                   for y in range(0, 100, 2) for x in range(0, 100, 2))
        self.assertTrue(diff)


class _FakeAnimeSeg:
    """Fake YOLOv8-seg session returning one nipple detection plus mask protos
    crafted so the assembled mask is all-True."""
    def get_inputs(self):
        import types
        return [types.SimpleNamespace(name="images")]

    def run(self, _outputs, _feed):
        import numpy as np
        out0 = np.zeros((1, 43, 1), dtype=np.float32)
        out0[0, 0, 0], out0[0, 1, 0], out0[0, 2, 0], out0[0, 3, 0] = 256, 256, 256, 256
        out0[0, 4 + 1, 0] = 0.9      # class 1 = nipple
        out0[0, 11:43, 0] = 1.0      # mask coefficients
        protos = np.ones((1, 32, 8, 8), dtype=np.float32)  # -> sigmoid(32) ~ 1 everywhere
        return [out0, protos]


class AnimeMaskTest(unittest.TestCase):
    def test_with_masks_returns_mask_array(self):
        saved, savedf = censor._anime, censor._anime_failed
        censor._anime, censor._anime_failed = _FakeAnimeSeg(), False
        try:
            out = censor.detect_anime_regions(solid(size=(100, 100)), with_masks=True)
        finally:
            censor._anime, censor._anime_failed = saved, savedf
        self.assertEqual(len(out), 1)
        box, part, covered, mask = out[0]
        self.assertEqual(part, "breasts")
        self.assertIsNotNone(mask)
        self.assertTrue(bool(mask.any()))


class BreastSegTest(unittest.TestCase):
    def test_model_is_bundled_and_available(self):
        from paths import Assets
        self.assertTrue(Assets.BREASTS_MODEL.is_file())
        self.assertTrue(censor.breasts_available())

    def test_detect_runs_on_blank_image(self):
        # Real bundled model: loads + infers without error; blank image -> [].
        out = censor.detect_breast_regions(solid(size=(256, 256)))
        self.assertIsInstance(out, list)

    def test_single_class_seg_maps_to_breasts(self):
        # Generic decoder derives ncls from the tensor; class 0 -> 'breasts'.
        import numpy as np

        class _FakeBreast:
            def get_inputs(self):
                import types
                return [types.SimpleNamespace(name="images")]

            def run(self, _o, _f):
                out0 = np.zeros((1, 37, 1), dtype=np.float32)  # 4 + 1 cls + 32
                out0[0, 0, 0], out0[0, 1, 0], out0[0, 2, 0], out0[0, 3, 0] = 512, 512, 512, 512
                out0[0, 4, 0] = 0.9  # class 0 score
                return [out0]

        out = censor._run_yolo_seg(_FakeBreast(), solid(size=(100, 100)), 1024,
                                   censor._BREASTS_IDX_TO_PART, 0.3, 0.5, False)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][1], "breasts")


class SegRegistryTest(unittest.TestCase):
    def test_all_registered_models_bundled_and_run(self):
        from paths import Assets
        for key in ("armpits", "belly", "mouth", "underwear", "socks", "skin"):
            self.assertIn(key, censor._SEG_REGISTRY)
            path = censor._SEG_REGISTRY[key][0]
            self.assertTrue(path.is_file(), f"{key} model missing")
            self.assertTrue(censor.seg_available(key))
            self.assertIsInstance(censor.detect_seg(key, solid(size=(256, 256))), list)

    def test_unknown_key_not_available(self):
        self.assertFalse(censor.seg_available("nonexistent"))


class FaceBodySegTest(unittest.TestCase):
    def test_face_seg_bundled_and_runs(self):
        from paths import Assets
        self.assertTrue(Assets.FACE_SEG.is_file())
        self.assertTrue(censor.face_seg_available())
        self.assertIsInstance(censor.detect_face_regions(solid(size=(256, 256))), list)

    def test_body_unavailable_returns_none_cleanly(self):
        saved, savedf = censor._body, censor._body_failed
        censor._body, censor._body_failed = None, True  # simulate model absent
        try:
            self.assertIsNone(censor.detect_body_regions(solid()))
        finally:
            censor._body, censor._body_failed = saved, savedf

    def test_body_idx_maps_to_body(self):
        self.assertEqual(censor._BODY_IDX_TO_PART[0], "body")
        self.assertEqual(censor._FACE_IDX_TO_PART[0], "face")


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


class _FakeDetectSession:
    """Fake YOLOv8-detect ONNX session. dets: (cls_idx, cx, cy, w, h, score) in
    320-space; image is fed at 320x320 so coords map 1:1 (r=1, no pad)."""
    def __init__(self, dets):
        self.dets = dets

    def get_inputs(self):
        import types
        return [types.SimpleNamespace(name="images")]

    def run(self, _outputs, _feed):
        import numpy as np
        n = max(1, len(self.dets))
        out = np.zeros((1, 4 + 18, n), dtype=np.float32)  # 4 box + 18 classes
        for i, (c, cx, cy, w, h, s) in enumerate(self.dets):
            out[0, 0, i], out[0, 1, i], out[0, 2, i], out[0, 3, i] = cx, cy, w, h
            out[0, 4 + c, i] = s
        return [out]


class DetectRegionsTest(unittest.TestCase):
    def _run(self, dets):
        saved = censor._detector, censor._detector_failed
        censor._detector, censor._detector_failed = _FakeDetectSession(dets), False
        try:
            return censor.detect_regions(solid(size=(320, 320)))
        finally:
            censor._detector, censor._detector_failed = saved

    def test_class_maps_to_part_with_covered(self):
        # class 0 = FEMALE_GENITALIA_COVERED -> female_genitals, covered True.
        out = self._run([(0, 160, 160, 40, 40, 0.9)])
        self.assertTrue(out)
        self.assertTrue(all(p == "female_genitals" and cov for _, p, cov in out))

    def test_centred_box_unions_across_flip(self):
        # Centred box maps onto itself under mirror -> the two passes merge to one.
        out = self._run([(3, 160, 160, 40, 40, 0.9)])  # 3 = FEMALE_BREAST_EXPOSED
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][1], "breasts")

    def test_below_threshold_dropped(self):
        self.assertEqual(self._run([(3, 160, 160, 40, 40, 0.05)]), [])

    def test_none_when_unavailable(self):
        saved = censor._detector, censor._detector_failed
        censor._detector, censor._detector_failed = None, True
        try:
            self.assertIsNone(censor.detect_regions(solid()))
        finally:
            censor._detector, censor._detector_failed = saved


if __name__ == "__main__":
    unittest.main()
