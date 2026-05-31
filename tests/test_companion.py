import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import tests._path  # noqa: F401

from features.companion import resolve_avatar
from features.companion import actions
from features.companion.engine import _parse_facts, resolve_persona, _DEFAULT_PERSONA


class ParseTagsTest(unittest.TestCase):
    def test_no_tags(self):
        clean, acts = actions.parse_tags("just a line")
        self.assertEqual(clean, "just a line")
        self.assertEqual(acts, [])

    def test_extracts_and_cleans(self):
        clean, acts = actions.parse_tags("hi [do:popup] there [do:vibrate=50]")
        self.assertEqual(clean, "hi  there")
        self.assertEqual(acts, [("popup", ""), ("vibrate", "50")])

    def test_case_insensitive(self):
        _clean, acts = actions.parse_tags("[DO:Notify=hello]")
        self.assertEqual(acts, [("notify", "hello")])


class ParseFactsTest(unittest.TestCase):
    def test_strips_bullets_and_numbers(self):
        facts = _parse_facts("- likes cats\n2. dislikes mornings\n* name is Sam")
        self.assertEqual(facts, ["likes cats", "dislikes mornings", "name is Sam"])

    def test_none_is_empty(self):
        self.assertEqual(_parse_facts("none"), [])
        self.assertEqual(_parse_facts("N/A"), [])
        self.assertEqual(_parse_facts(""), [])

    def test_truncates_long_line(self):
        long = "x " * 100  # 200 chars
        (fact,) = _parse_facts(long)
        self.assertLessEqual(len(fact), 140)


class ResolvePersonaTest(unittest.TestCase):
    def test_blank_returns_base_default(self):
        pack = SimpleNamespace(companion=None)
        s = SimpleNamespace(companion_name="", companion_system_prompt="")
        p = resolve_persona(s, pack)
        self.assertIs(p, _DEFAULT_PERSONA)
        self.assertEqual(p.name, "Companion")

    def test_name_override(self):
        pack = SimpleNamespace(companion=None)
        s = SimpleNamespace(companion_name="Yuu", companion_system_prompt="")
        p = resolve_persona(s, pack)
        self.assertEqual(p.name, "Yuu")
        self.assertEqual(p.system_prompt, _DEFAULT_PERSONA.system_prompt)  # falls back

    def test_prompt_override(self):
        pack = SimpleNamespace(companion=None)
        s = SimpleNamespace(companion_name="", companion_system_prompt="be terse")
        p = resolve_persona(s, pack)
        self.assertEqual(p.system_prompt, "be terse")
        self.assertEqual(p.name, "Companion")


class ResolveAvatarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.user_img = self.root / "user.png"
        self.user_img.write_bytes(b"x")
        self.persona_img = self.root / "av.png"
        self.persona_img.write_bytes(b"x")
        self.icon = self.root / "icon.png"
        self.icon.write_bytes(b"x")
        self.pack = SimpleNamespace(icon=self.icon, paths=SimpleNamespace(root=self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def test_user_path_wins(self):
        s = SimpleNamespace(companion_avatar=str(self.user_img))
        persona = SimpleNamespace(avatar="av.png")
        self.assertEqual(resolve_avatar(s, self.pack, persona), self.user_img)

    def test_persona_avatar_when_user_blank(self):
        s = SimpleNamespace(companion_avatar="")
        persona = SimpleNamespace(avatar="av.png")
        self.assertEqual(resolve_avatar(s, self.pack, persona), self.persona_img)

    def test_pack_icon_fallback(self):
        s = SimpleNamespace(companion_avatar="   ")
        self.assertEqual(resolve_avatar(s, self.pack, None), self.icon)

    def test_bad_user_path_falls_through(self):
        s = SimpleNamespace(companion_avatar="/no/such/file.png")
        self.assertEqual(resolve_avatar(s, self.pack, None), self.icon)


if __name__ == "__main__":
    unittest.main()
