"""Tests for the Valve KeyValues parser and Steam library discovery."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bunbun.perception.acf import ParseError, parse
from bunbun.perception.steam import installed_games

MANIFEST = '''
"AppState"
{
\t"appid"\t\t"480"
\t"name"\t\t"Bunny Test Game"
\t"installdir"\t"BunnyTest"
\t"StateFlags"\t"4"
\t"SizeOnDisk"\t"2048"
\t"UserConfig"
\t{
\t\t"language"\t"english"
\t}
}
'''


class KeyValuesTests(unittest.TestCase):
    def test_nested_and_types(self):
        data = parse(MANIFEST)
        app = data["AppState"]
        self.assertEqual(app["appid"], "480")
        self.assertEqual(app["UserConfig"]["language"], "english")

    def test_comments_and_escapes(self):
        data = parse('// a comment\n"root" { "a" "b\\"c" } // trailing\n')
        self.assertEqual(data["root"]["a"], 'b"c')

    def test_unquoted_tokens(self):
        data = parse("root { a b }")
        self.assertEqual(data["root"]["a"], "b")

    def test_unterminated_string(self):
        with self.assertRaises(ParseError):
            parse('"root" { "a" "oops }')


class SteamLibraryTests(unittest.TestCase):
    def test_installed_games_from_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            steamapps = root / "steamapps"
            steamapps.mkdir()
            (steamapps / "appmanifest_480.acf").write_text(MANIFEST, "utf-8")
            games = installed_games([root])
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0].name, "Bunny Test Game")
            self.assertEqual(games[0].app_id, "480")
            self.assertEqual(games[0].as_dict()["game_id"], "steam:480")

    def test_incomplete_install_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            steamapps = root / "steamapps"
            steamapps.mkdir()
            (steamapps / "appmanifest_1.acf").write_text(
                '"AppState" { "appid" "1" "name" "Half" "installdir" "Half" '
                '"StateFlags" "2" }', "utf-8")
            self.assertEqual(installed_games([root]), [])

    def test_absolute_install_path_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            steamapps = root / "steamapps"
            steamapps.mkdir()
            (steamapps / "appmanifest_2.acf").write_text(
                '"AppState" { "appid" "2" "name" "Epic Thing" '
                '"installdir" "/games/epic-thing" "StateFlags" "4" }', "utf-8")
            games = installed_games([root])
            self.assertEqual(games[0].path, Path("/games/epic-thing"))


if __name__ == "__main__":
    unittest.main()
