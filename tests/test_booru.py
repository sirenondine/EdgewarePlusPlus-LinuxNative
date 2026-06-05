import unittest

import tests._path  # noqa: F401

from features.booru import (
    build_query,
    media_category,
    post_url,
    thumb_url,
    url_ext,
    _sort_tag,
    _split,
)


class SplitTest(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(_split("a b c"), ["a", "b", "c"])

    def test_angle_bracket_separator(self):
        self.assertEqual(_split("a>b>c"), ["a", "b", "c"])

    def test_empty(self):
        self.assertEqual(_split(""), [])

    def test_none(self):
        self.assertEqual(_split(None), [])  # type: ignore[arg-type]


class BuildQueryTest(unittest.TestCase):
    def test_basic_tags(self):
        q = build_query("cat dog")
        self.assertIn("cat", q)
        self.assertIn("dog", q)

    def test_exclude_prefixed(self):
        q = build_query("cat", exclude="dog")
        self.assertIn("-dog", q)

    def test_rating_appended(self):
        q = build_query("cat", rating="safe")
        self.assertIn("rating:safe", q)

    def test_rating_any_not_appended(self):
        q = build_query("cat", rating="any")
        self.assertNotIn("rating:", q)

    def test_rating_empty_not_appended(self):
        q = build_query("cat", rating="")
        self.assertNotIn("rating:", q)

    def test_all_tag_stripped(self):
        q = build_query("all cat")
        self.assertNotIn("all", q.split())
        self.assertIn("cat", q)

    def test_empty_tags(self):
        self.assertEqual(build_query(""), "")

    def test_combine_all(self):
        q = build_query("cat", exclude="dog", rating="explicit")
        self.assertIn("cat", q)
        self.assertIn("-dog", q)
        self.assertIn("rating:explicit", q)


class SortTagTest(unittest.TestCase):
    def test_gelbooru_score(self):
        tag = _sort_tag("gelbooru", "score")
        self.assertTrue(tag.startswith("sort:"))

    def test_danbooru_score(self):
        tag = _sort_tag("danbooru", "score")
        self.assertTrue(tag.startswith("order:"))

    def test_unknown_engine_empty(self):
        self.assertEqual(_sort_tag("fakebooru", "score"), "")

    def test_unknown_sort_key_empty(self):
        self.assertEqual(_sort_tag("gelbooru", "unknownsort"), "")

    def test_gelbooru_random_tag(self):
        # gelbooru supports sort:random as an actual metatag
        self.assertEqual(_sort_tag("gelbooru", "random"), "sort:random")


class UrlExtTest(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(url_ext("http://example.com/file.jpg"), "jpg")

    def test_ignores_query(self):
        self.assertEqual(url_ext("http://example.com/file.mp4?foo=bar"), "mp4")

    def test_lowercase(self):
        self.assertEqual(url_ext("http://example.com/file.WEBM"), "webm")

    def test_empty(self):
        self.assertEqual(url_ext(""), "")


class MediaCategoryTest(unittest.TestCase):
    def test_jpg_is_image(self):
        self.assertEqual(media_category("http://x.com/pic.jpg"), "image")

    def test_mp4_is_video(self):
        self.assertEqual(media_category("http://x.com/clip.mp4"), "video")

    def test_webm_is_video(self):
        self.assertEqual(media_category("http://x.com/clip.webm"), "video")

    def test_gif_is_gif(self):
        self.assertEqual(media_category("http://x.com/anim.gif"), "gif")

    def test_png_is_image(self):
        self.assertEqual(media_category("http://x.com/img.png"), "image")


class ThumbUrlTest(unittest.TestCase):
    def test_prefers_preview(self):
        post = {"preview_url": "prev", "sample_url": "samp", "file_url": "full"}
        self.assertEqual(thumb_url(post), "prev")

    def test_falls_back_to_sample(self):
        post = {"sample_url": "samp", "file_url": "full"}
        self.assertEqual(thumb_url(post), "samp")

    def test_falls_back_to_file(self):
        post = {"file_url": "full"}
        self.assertEqual(thumb_url(post), "full")

    def test_empty_post(self):
        self.assertIsNone(thumb_url({}))


class PostUrlTest(unittest.TestCase):
    def test_known_site_returns_url(self):
        post = {"id": 42}
        url = post_url("gelbooru", post)
        self.assertIsNotNone(url)
        self.assertIn("42", url)

    def test_unknown_site_returns_none(self):
        self.assertIsNone(post_url("fakebooru", {"id": 1}))

    def test_missing_id_returns_none(self):
        self.assertIsNone(post_url("gelbooru", {}))

    def test_custom_site_no_url_returns_none(self):
        self.assertIsNone(post_url("custom", {"id": 1}, custom_url=""))

    def test_custom_site_with_url(self):
        url = post_url("custom", {"id": 7}, custom_url="https://my.booru.com", api_type="gelbooru")
        self.assertIsNotNone(url)
        self.assertIn("7", url)


if __name__ == "__main__":
    unittest.main()
