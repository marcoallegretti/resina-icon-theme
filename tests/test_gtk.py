# SPDX-License-Identifier: EUPL-1.2
import os
import subprocess
import unittest

import support
import themebuild

BUILD = os.environ.get("RESINA_GTK_BUILD")
SKIP_REASON = "set RESINA_GTK_BUILD to a directory with the compiled GTK probes (cmake -S tests/gtk -B <dir>)"


def has_display():
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


@unittest.skipUnless(BUILD, SKIP_REASON)
class GtkProbeTests(support.TempCase):
    PROBES = ("gtk3_probe", "gtk4_probe")

    def setUp(self):
        super().setUp()
        if not has_display():
            self.skipTest("no display server: provide DISPLAY or WAYLAND_DISPLAY")
        self.root = self.path("root")
        themebuild.build(support.ROOT, os.path.join(self.root, "Resina"), "full")

    def run_probe(self, name):
        binary = os.path.join(BUILD, name)
        if not os.path.exists(binary):
            self.skipTest("%s was not built (GTK development files missing?)" % name)
        env = dict(os.environ, GSK_RENDERER="cairo")
        result = subprocess.run([binary, self.root], capture_output=True, text=True, env=env, timeout=300)
        lines = [line.split("\t") for line in result.stdout.splitlines() if line]
        return result.returncode, lines

    def test_probes_pass_on_the_built_theme(self):
        for name in self.PROBES:
            code, lines = self.run_probe(name)
            if lines and lines[0][0] == "BLOCKED":
                self.skipTest("%s: %s" % (name, lines[0][2]))
            self.assertEqual([l for l in lines if l[0] == "FAIL"], [], name)
            self.assertEqual(code, 0, name)
            checks = {l[1] for l in lines if l[0] == "PASS"}
            for expected in ("folder", "go-next-symbolic", "colour-preserved", "symbolic-detected", "untinted-control", "plain-name-reaches-the-symbolic-file-unrecoloured"):
                self.assertIn(expected, checks, name)

    def test_stroked_symbolic_icon_fails_the_gtk3_recolour_check(self):
        path = os.path.join(self.root, "Resina/symbolic/actions/go-next-symbolic.svg")
        support.write(path, support.SYMBOLIC_SVG)
        code, lines = self.run_probe("gtk3_probe")
        if lines and lines[0][0] == "BLOCKED":
            self.skipTest("gtk3_probe: %s" % lines[0][2])
        self.assertEqual(code, 1)
        failed = {l[1] for l in lines if l[0] == "FAIL"}
        self.assertIn("symbolic-recolour #c62828", failed)

    def test_missing_icon_fails_the_ownership_check(self):
        os.remove(os.path.join(self.root, "Resina/scalable/places-medium/folder.svg"))
        for name in self.PROBES:
            code, lines = self.run_probe(name)
            if lines and lines[0][0] == "BLOCKED":
                self.skipTest("%s: %s" % (name, lines[0][2]))
            self.assertEqual(code, 1, name)
            self.assertIn("folder", {l[1] for l in lines if l[0] == "FAIL"}, name)

    def test_tampered_file_fails_the_manifest_check(self):
        with open(os.path.join(self.root, "Resina/scalable/places-medium/folder.svg"), "a", encoding="utf-8") as handle:
            handle.write(chr(10))
        for name in self.PROBES:
            code, lines = self.run_probe(name)
            if lines and lines[0][0] == "BLOCKED":
                self.skipTest("%s: %s" % (name, lines[0][2]))
            self.assertEqual(code, 1, name)
            failed = [l for l in lines if l[0] == "FAIL" and l[1] == "folder"]
            self.assertEqual(len(failed), 1, name)
            self.assertIn("differs from the manifest", failed[0][2], name)

    def test_wrong_artwork_fails_the_colour_check(self):
        base = os.path.join(self.root, "Resina/scalable")
        with open(os.path.join(base, "places-medium/folder.svg"), "w", encoding="utf-8") as handle:
            handle.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><circle cx="64" cy="64" r="40" fill="#3366cc"/></svg>')
        for name in self.PROBES:
            code, lines = self.run_probe(name)
            if lines and lines[0][0] == "BLOCKED":
                self.skipTest("%s: %s" % (name, lines[0][2]))
            self.assertEqual(code, 1, name)
            self.assertIn("colour-preserved", {l[1] for l in lines if l[0] == "FAIL"}, name)


if __name__ == "__main__":
    unittest.main()
