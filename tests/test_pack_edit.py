import json
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401

from pack.edit import (
    PackEditor,
    _slugify,
    _PACK_CONFIG_BLOCKLIST,
    create_pack,
)


def _make_pack(tmp: Path, index: dict | None = None, info: dict | None = None) -> Path:
    """Write a minimal pack directory and return its path."""
    pack = tmp / "test_pack"
    pack.mkdir()
    if index is not None:
        (pack / "index.json").write_text(json.dumps(index), encoding="utf-8")
    if info is not None:
        (pack / "info.json").write_text(json.dumps(info), encoding="utf-8")
    return pack


class SlugifyTest(unittest.TestCase):
    def test_alnum_passthrough(self):
        self.assertEqual(_slugify("MyPack123"), "MyPack123")

    def test_strips_spaces_and_symbols(self):
        self.assertEqual(_slugify("My Pack!"), "MyPack")

    def test_empty_falls_back(self):
        self.assertEqual(_slugify("!!! ???"), "pack")

    def test_fully_empty(self):
        self.assertEqual(_slugify(""), "pack")


class BlocklistTest(unittest.TestCase):
    """Secrets must never leave in a pack export."""
    REQUIRED = {"companionApiKey", "openaiKey", "opencodeKey",
                "ollamaUrl", "openaiUrl", "opencodeUrl"}

    def test_secrets_blocked(self):
        missing = self.REQUIRED - _PACK_CONFIG_BLOCKLIST
        self.assertEqual(missing, set(), f"Not in blocklist: {missing}")

    def test_endpoints_blocked(self):
        self.assertIn("migratedBackendsV2", _PACK_CONFIG_BLOCKLIST)


class PackEditorMoodsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        pack_dir = _make_pack(root, index={"default": {}, "moods": []})
        self.ed = PackEditor(pack_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_mood(self):
        err = self.ed.add_mood("shy")
        self.assertIsNone(err)
        self.assertIn("shy", self.ed.mood_names())

    def test_add_duplicate_mood_errors(self):
        self.ed.add_mood("shy")
        err = self.ed.add_mood("shy")
        self.assertIsNotNone(err)
        self.assertEqual(self.ed.mood_names().count("shy"), 1)

    def test_add_blank_mood_errors(self):
        err = self.ed.add_mood("   ")
        self.assertIsNotNone(err)

    def test_rename_mood(self):
        self.ed.add_mood("old")
        err = self.ed.rename_mood("old", "new")
        self.assertIsNone(err)
        self.assertIn("new", self.ed.mood_names())
        self.assertNotIn("old", self.ed.mood_names())

    def test_rename_to_existing_errors(self):
        self.ed.add_mood("a")
        self.ed.add_mood("b")
        err = self.ed.rename_mood("a", "b")
        self.assertIsNotNone(err)

    def test_rename_nonexistent_errors(self):
        err = self.ed.rename_mood("ghost", "x")
        self.assertIsNotNone(err)

    def test_remove_mood(self):
        self.ed.add_mood("shy")
        self.ed.remove_mood("shy")
        self.assertNotIn("shy", self.ed.mood_names())

    def test_remove_clears_media_assignments(self):
        self.ed.add_mood("shy")
        self.ed.set_media_assignment("file.png", "shy")
        self.ed.remove_mood("shy")
        self.assertIsNone(self.ed.get_media_assignment("file.png"))

    def test_move_mood_up(self):
        self.ed.add_mood("A")
        self.ed.add_mood("B")
        self.ed.add_mood("C")
        self.ed.move_mood("B", -1)
        self.assertEqual(self.ed.mood_names(), ["B", "A", "C"])

    def test_move_mood_down(self):
        self.ed.add_mood("A")
        self.ed.add_mood("B")
        self.ed.add_mood("C")
        self.ed.move_mood("B", +1)
        self.assertEqual(self.ed.mood_names(), ["A", "C", "B"])

    def test_move_mood_at_boundary_noop(self):
        self.ed.add_mood("A")
        self.ed.add_mood("B")
        self.ed.move_mood("A", -1)
        self.assertEqual(self.ed.mood_names(), ["A", "B"])
        self.ed.move_mood("B", +1)
        self.assertEqual(self.ed.mood_names(), ["A", "B"])


class PackEditorMediaAssignmentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        pack_dir = _make_pack(root, index={"default": {}, "moods": [{"mood": "A", "media": []}]})
        self.ed = PackEditor(pack_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_unassigned_by_default(self):
        self.assertIsNone(self.ed.get_media_assignment("x.png"))

    def test_assign_to_mood(self):
        self.ed.set_media_assignment("x.png", "A")
        self.assertEqual(self.ed.get_media_assignment("x.png"), "A")

    def test_reassign_moves_file(self):
        self.ed.add_mood("B")
        self.ed.set_media_assignment("x.png", "A")
        self.ed.set_media_assignment("x.png", "B")
        self.assertEqual(self.ed.get_media_assignment("x.png"), "B")
        # Must not appear in A's media list
        a_mood = self.ed._find_mood("A")
        self.assertNotIn("x.png", a_mood.get("media", []))

    def test_unassign(self):
        self.ed.set_media_assignment("x.png", "A")
        self.ed.set_media_assignment("x.png", None)
        self.assertIsNone(self.ed.get_media_assignment("x.png"))


class PackEditorIndexListsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        pack_dir = _make_pack(root, index={"default": {}})
        self.ed = PackEditor(pack_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_get_missing_list_empty(self):
        self.assertEqual(self.ed.get_list("captions"), [])

    def test_set_and_get_list(self):
        self.ed.set_list("captions", ["a", "b"])
        self.assertEqual(self.ed.get_list("captions"), ["a", "b"])

    def test_get_missing_string_default(self):
        # promptDelimiter has a default in DEFAULT_STRINGS
        val = self.ed.get_string("promptDelimiter")
        self.assertIsInstance(val, str)

    def test_set_and_get_int(self):
        self.ed.set_int("popupTimeout", 42)
        self.assertEqual(self.ed.get_int("popupTimeout"), 42)

    def test_get_int_bad_value_falls_back(self):
        self.ed._default()["popupTimeout"] = "nope"
        self.assertEqual(self.ed.get_int("popupTimeout", fallback=7), 7)


class PackEditorInfoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        pack_dir = _make_pack(root, info={"name": "Test", "id": "test",
                                          "creator": "Me", "version": "1.0"})
        self.ed = PackEditor(pack_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_get_info(self):
        self.assertEqual(self.ed.get_info("name"), "Test")

    def test_set_info(self):
        self.ed.set_info("name", "NewName")
        self.assertEqual(self.ed.get_info("name"), "NewName")

    def test_validate_info_ok(self):
        self.assertIsNone(self.ed.validate_info())

    def test_validate_info_missing_required(self):
        del self.ed.info["name"]
        del self.ed.info["id"]
        del self.ed.info["creator"]
        # _ensure_info_required should backfill; validate should then pass
        self.assertIsNone(self.ed.validate_info())

    def test_save_info_writes_file(self):
        self.ed.set_info("description", "hello")
        err = self.ed.save_info()
        self.assertIsNone(err)
        raw = json.loads(self.ed.info_path.read_text())
        self.assertEqual(raw["description"], "hello")


class PackEditorSaveIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        pack_dir = _make_pack(root, index={"default": {}, "moods": []})
        self.ed = PackEditor(pack_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_index_writes_file(self):
        self.ed.set_list("captions", ["hi"])
        err = self.ed.save_index()
        self.assertIsNone(err)
        raw = json.loads(self.ed.index_path.read_text())
        self.assertEqual(raw["default"]["captions"], ["hi"])

    def test_save_index_invalid_prompt_lengths(self):
        self.ed.set_int("promptMinLength", 10)
        self.ed.set_int("promptMaxLength", 1)
        err = self.ed.save_index()
        self.assertIsNotNone(err)


class CreatePackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_expected_structure(self):
        parent = Path(self.tmp.name)
        path, err = create_pack(parent, "MyPack")
        self.assertIsNone(err)
        self.assertIsNotNone(path)
        self.assertTrue((path / "index.json").is_file())
        self.assertTrue((path / "info.json").is_file())
        self.assertTrue((path / "img").is_dir())
        self.assertTrue((path / "vid").is_dir())
        self.assertTrue((path / "aud").is_dir())

    def test_info_contains_name_and_creator(self):
        parent = Path(self.tmp.name)
        path, _ = create_pack(parent, "CoolPack", creator="Tester")
        info = json.loads((path / "info.json").read_text())
        self.assertEqual(info["name"], "CoolPack")
        self.assertEqual(info["creator"], "Tester")

    def test_index_has_default_and_moods(self):
        parent = Path(self.tmp.name)
        path, _ = create_pack(parent, "X")
        idx = json.loads((path / "index.json").read_text())
        self.assertIn("default", idx)
        self.assertIn("moods", idx)


class PackEditorVerifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.pack_dir = _make_pack(root)
        self.ed = PackEditor(self.pack_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def _severities(self, issues):
        return [s for s, _, __ in issues]

    def test_clean_pack_no_issues(self):
        # Add a mood with a caption so the "empty pack" warning doesn't fire
        self.ed.add_mood("test")
        self.ed.set_mood_list("test", "captions", ["hello"])
        issues = self.ed.verify()
        self.assertEqual(issues, [])

    def test_invalid_info_json(self):
        (self.pack_dir / "info.json").write_text("{bad json", encoding="utf-8")
        issues = self.ed.verify()
        self.assertTrue(any(s == "error" and "info.json" in c for s, c, _ in issues))

    def test_missing_media_file(self):
        self.ed.add_mood("test")
        # Directly inject a media reference without creating the file
        self.ed._find_mood("test")["media"] = ["ghost.png"]
        issues = self.ed.verify()
        self.assertTrue(any(s == "error" and "media" in c for s, c, _ in issues))

    def test_missing_media_not_reported_when_file_exists(self):
        self.ed.add_mood("test")
        img_dir = self.pack_dir / "img"
        img_dir.mkdir(exist_ok=True)
        (img_dir / "real.png").write_bytes(b"")
        self.ed._find_mood("test")["media"] = ["real.png"]
        issues = self.ed.verify()
        self.assertFalse(any("real.png" in msg for _, __, msg in issues))

    def test_corruption_stale_mood_warning(self):
        import json
        (self.pack_dir / "corruption.json").write_text(
            json.dumps({"moods": {"1": {"add": ["ghost"], "remove": []}},
                        "wallpapers": {}, "config": {}, "names": {}}),
            encoding="utf-8")
        issues = self.ed.verify()
        self.assertTrue(any(s == "warning" and "corruption" in c for s, c, _ in issues))

    def test_empty_pack_warning(self):
        # Fresh pack from _make_pack has no moods and no captions
        issues = self.ed.verify()
        # _make_pack creates index with no moods and empty default → warning
        self.assertTrue(any(s == "warning" for s, _, __ in issues))


if __name__ == "__main__":
    unittest.main()
