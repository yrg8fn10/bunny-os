"""The linked game library (pre10 pillar 4), Steam-first and fully local."""
import unittest
from pathlib import Path
from unittest import mock

from bunbun import library as library_mod
from bunbun.library import LibraryManager
from bunbun.perception import steam as steam_mod


class Game:
    def __init__(self, name, app_id):
        self.name = name
        self.app_id = app_id
        self.install_dir = f"common/{name.replace(' ', '')}"
        self.library = Path("/tmp")


GAMES = [Game("Subnautica", "264710"), Game("Black Mesa", "362890"),
         Game("Hollow Knight", "367520")]


def fake_installed(roots=None):
    return list(GAMES)


class LibraryTests(unittest.TestCase):
    def test_link_counts(self):
        with mock.patch("bunbun.library.installed_games", fake_installed):
            library = LibraryManager()
            status = library.link()
        self.assertTrue(status["linked"])
        self.assertEqual(status["count"], 3)
        self.assertEqual(library.preview(2), ["Subnautica", "Black Mesa"])
        self.assertEqual(library.status()["platform"], "steam")

    def test_find_via_library(self):
        with mock.patch("bunbun.library.installed_games", fake_installed):
            library = LibraryManager()
            library.link()
            game, _ = library.find("black mesa")
        self.assertIsNotNone(game)
        self.assertEqual(game.app_id, "362890")

    def test_launch_asks_steam_by_url(self):
        seen = {}

        def fake_launcher(game):
            seen["url"] = f"steam://rungameid/{game.app_id}"
            return True

        with mock.patch("bunbun.library.installed_games", fake_installed):
            library = LibraryManager(launcher=fake_launcher)
            library.link()
            game, _ = library.find("subnautica")
            self.assertTrue(library.launch(game))
        self.assertEqual(seen["url"], "steam://rungameid/264710")

    def test_launch_without_xdg_open(self):
        with mock.patch.object(library_mod, "installed_games", fake_installed), \
             mock.patch.object(library_mod.shutil, "which", lambda name: None):
            library = LibraryManager()
            library.link()
            game, _ = library.find("subnautica")
            self.assertFalse(library.launch(game))


if __name__ == "__main__":
    unittest.main()
