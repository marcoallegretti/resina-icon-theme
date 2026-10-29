# SPDX-License-Identifier: EUPL-1.2
import os
import subprocess
import unittest

import support
import install
import themebuild

BUILD = os.environ.get("RESINA_KDE_BUILD")
SKIP_REASON = "set RESINA_KDE_BUILD to a directory with the compiled KDE probe (cmake -S tests/kde -B <dir>); needs KDE Frameworks 6 IconThemes"


@unittest.skipUnless(BUILD, SKIP_REASON)
class KdeProbeTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.tree = self.path("tree")
        themebuild.build(support.ROOT, self.tree, "full")
        self.data = self.path("data")
        self.icons = os.path.join(self.data, "icons")
        os.makedirs(self.icons)
        self.config = self.path("config")
        os.makedirs(self.config)
        with open(os.path.join(self.config, "kdeglobals"), "w", encoding="utf-8") as handle:
            handle.write("[Icons]" + chr(10) + "Theme=Resina" + chr(10))

    def run_probe(self, *arguments):
        env = dict(
            os.environ,
            QT_QPA_PLATFORM="offscreen",
            XDG_DATA_HOME=self.data,
            XDG_DATA_DIRS=self.path("no-system-icons"),
            XDG_CONFIG_HOME=self.config,
            XDG_CACHE_HOME=self.path("cache"),
        )
        binary = os.path.join(BUILD, "kde_probe")
        if not os.path.exists(binary):
            self.skipTest("kde_probe was not built (KDE Frameworks 6 IconThemes missing?)")
        result = subprocess.run([binary, *arguments], capture_output=True, text=True, env=env, timeout=300)
        lines = [line.split("\t") for line in result.stdout.splitlines() if line]
        if lines and lines[0][0] == "BLOCKED":
            self.skipTest(lines[0][-1])
        return result.returncode, lines

    def install(self):
        install.install(self.tree, self.icons)

    def failed(self, lines):
        return {l[1] for l in lines if l[0] == "FAIL"}

    def test_symbolic_icons_follow_the_colour_scheme_and_colour_icons_do_not(self):
        self.install()
        code, lines = self.run_probe()
        self.assertEqual(self.failed(lines), set())
        self.assertEqual(code, 0)
        self.assertGreaterEqual(len([l for l in lines if l[0] == "PASS"]), 20)

    def test_folders_use_the_drawing_made_for_the_requested_size(self):
        self.install()
        expected = {
            ("folder-music", "16"): "places-small",
            ("folder-music", "22"): "places-small",
            ("folder-music", "24"): "places-small",
            ("folder-music", "32"): "places-medium",
            ("folder-music", "48"): "places-medium",
            ("folder-music", "64"): "places-medium",
            ("folder-music", "128"): "places",
            ("folder-downloads", "22"): "places-small",
            ("folder-arduino", "22"): "places-small",
            ("folder", "16"): "places-small",
            ("folder", "48"): "places-medium",
            ("folder", "128"): "places",
            ("inode-directory", "16"): "places-small",
            ("user-trash", "32"): "places-medium",
            ("folder-open", "16"): "places-small",
            ("folder-open", "48"): "places-medium",
            ("folder-open", "128"): "places",
        }
        for (name, size), directory in expected.items():
            code, lines = self.run_probe("--at", name, size)
            self.assertEqual(code, 0)
            path = os.path.realpath(lines[0][3])
            self.assertEqual(os.path.basename(os.path.dirname(path)), directory, "%s at %s px: %s" % (name, size, path))

    def test_kde_names_resolve_to_the_drawings_they_are_aliased_to(self):
        self.install()
        expected = {
            "application-menu": "symbolic/actions/open-menu-symbolic.svg",
            "view-list-icons": "symbolic/actions/view-grid-symbolic.svg",
            "arrow-up": "symbolic/actions/go-up-symbolic.svg",
            "configure": "symbolic/categories/applications-system-symbolic.svg",
            "battery-050": "symbolic/status/battery-level-50-symbolic.svg",
            "battery-050-charging": "symbolic/status/battery-level-50-charging-symbolic.svg",
            "network-wireless-80": "symbolic/status/network-wireless-signal-good-symbolic.svg",
            "network-wireless-60": "symbolic/status/network-wireless-signal-ok-symbolic.svg",
            "network-wireless-on": "symbolic/status/network-wireless-signal-excellent-symbolic.svg",
            "battery-profile-powersave-symbolic": "symbolic/status/battery-profile-powersave-symbolic.svg",
            "battery-profile-performance-symbolic": "symbolic/status/battery-profile-performance-symbolic.svg",
            "unknown": "symbolic/status/dialog-question-symbolic.svg",
            "expand": "symbolic/actions/pan-down-symbolic.svg",
            "window-pin": "symbolic/actions/view-pin-symbolic.svg",
            "folder-public": "scalable/places-small/folder-publicshare.svg",
            "preferences-desktop-mouse": "scalable/apps/preferences-desktop-mouse.svg",
            "preferences-system-users": "scalable/categories/preferences-desktop-personal.svg",
            "get-hot-new-stuff": "symbolic/actions/get-hot-new-stuff-symbolic.svg",
            "document-import": "symbolic/actions/document-import-symbolic.svg",
            "view-preview": "symbolic/actions/view-preview-symbolic.svg",
            "emblem-music-symbolic": "symbolic/emblems/emblem-music-symbolic.svg",
            "preferences-security": "scalable/apps/preferences-security.svg",
            "ktip": "scalable/apps/ktip.svg",
            "image-png": "scalable/mimetypes/image-png.svg",
            "start-here-kde": "scalable/apps/start-here-kde.svg",
            "plasmashell": "scalable/apps/start-here-kde.svg",
            "system-run": "scalable/apps/terminal.svg",
            "help-browser": "scalable/apps/help.svg",
            "help-contents": "symbolic/actions/help-contents-symbolic.svg",
            "bookmark-new": "symbolic/actions/bookmark-new-symbolic.svg",
            "kde": "symbolic/emblems/emblem-kde-symbolic.svg",
        }
        names = self.path("names.txt")
        with open(names, "w", encoding="utf-8") as handle:
            handle.write(chr(10).join(expected) + chr(10))
        code, lines = self.run_probe("--paths", names)
        self.assertEqual(code, 0)
        found = {l[1]: l[2] for l in lines if l[0] == "PATH"}
        theme = os.path.join(self.icons, "Resina")
        for name, relative in expected.items():
            self.assertTrue(found.get(name), name)
            with open(os.path.realpath(found[name]), "rb") as handle:
                resolved = handle.read()
            with open(os.path.join(theme, relative), "rb") as handle:
                self.assertEqual(resolved, handle.read(), name)

    def test_the_busy_animation_loads_as_a_pixmap_sequence_at_the_shipped_sizes(self):
        self.install()
        for size in themebuild.ANIMATION_SIZES:
            code, lines = self.run_probe("--sequence", "process-working", str(size))
            self.assertEqual(code, 0)
            self.assertEqual([l[1:] for l in lines if l[0] == "SEQUENCE"], [[str(size), "valid", "12", str(size)]])

    def test_without_the_stylesheet_the_icons_do_not_recolour(self):
        self.install()
        path = os.path.join(self.icons, "Resina/symbolic/actions/go-next-symbolic.svg")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace("current-color-scheme", "other"))
        code, lines = self.run_probe()
        self.assertEqual(code, 1)
        self.assertTrue(any(name.startswith("go-next dark") for name in self.failed(lines)))

    def test_without_the_theme_key_the_icons_do_not_recolour(self):
        self.install()
        path = os.path.join(self.icons, "Resina/index.theme")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace("FollowsColorScheme=true" + chr(10), ""))
        code, lines = self.run_probe()
        self.assertEqual(code, 1)
        self.assertTrue(any(name.startswith("edit-copy-symbolic dark") for name in self.failed(lines)))


if __name__ == "__main__":
    unittest.main()
