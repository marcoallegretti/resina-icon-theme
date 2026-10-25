# SPDX-License-Identifier: EUPL-1.2
import os
import shutil
import subprocess
import unittest

import support
import install
import themebuild

BUILD = os.environ.get("RESINA_QT_BUILD")
QT = os.path.join(support.HERE, "qt")
SKIP_REASON = "set RESINA_QT_BUILD to a directory with the compiled probes (cmake -S tests/qt -B <dir>)"

LOOKUP_NEGATIVES = (
    ("decoy-hicolor-only", "not present in theme tree"),
    ("resina-absent-icon", "not present in theme tree"),
    ("inode-directory", "alias does not resolve to computer"),
    ("folder", "unexpected icon supplied"),
    ("folder", "alias does not resolve to folder"),
    ("folder-resina-absent", "generic fallback not resolved"),
)
QUICK_NEGATIVES = {
    "n-tinted-as-original": "metric",
    "n-symbolic-wrong-colour": "metric",
    "n-blank-for-present": "blank metric",
    "n-original-for-missing": "no theme file for reference",
    "n-not-original-for-original": "distance from original",
    "n-invisible-tint": "invisible against the background",
    "n-near-tint": "metric",
}


def concatenate(target, *sources):
    with open(target, "w", encoding="utf-8") as out:
        for source in sources:
            with open(os.path.join(QT, source), encoding="utf-8") as handle:
                out.write(handle.read())


def rows(path):
    with open(path, encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def display_platform():
    chosen = os.environ.get("RESINA_QT_PLATFORM")
    if chosen:
        return chosen
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "xcb"
    return None


@unittest.skipUnless(BUILD, SKIP_REASON)
class QtProbeTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.full = self.path("full")
        self.core = self.path("core")
        themebuild.build(support.ROOT, os.path.join(self.full, "Resina"), "full")
        themebuild.build(support.ROOT, os.path.join(self.core, "Resina"), "core")
        self.env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")

    def probe(self, name, *args, scale=None, env=None):
        merged = dict(env or self.env)
        if scale:
            merged["QT_SCALE_FACTOR"] = str(scale)
        result = subprocess.run([os.path.join(BUILD, name), *args], capture_output=True, text=True, env=merged, timeout=600)
        lines = [line.split("\t") for line in result.stdout.splitlines() if line]
        return result.returncode, lines

    def lookup(self, root, table, env=None, *extra):
        return self.probe("lookup_probe", "--root", root, "--decoy", os.path.join(QT, "fixtures"), "--expect", table, *extra, env=env)

    def assert_clean(self, code, lines, expected_rows):
        self.assertEqual([l for l in lines if l[0] == "FAIL"], [])
        summary = [l for l in lines if l[0] == "SUMMARY"]
        self.assertEqual(len(summary), 1)
        self.assertEqual((int(summary[0][1]), int(summary[0][2])), (expected_rows, 0))
        self.assertEqual(len([l for l in lines if l[0] == "PASS"]), expected_rows)
        self.assertEqual(code, 0)

    def test_full_lookup(self):
        table = self.path("full.tsv")
        concatenate(table, "expectations.tsv", "expectations-thirdparty.tsv")
        code, lines = self.lookup(self.full, table)
        self.assert_clean(code, lines, rows(table))

    def test_core_lookup(self):
        table = self.path("core.tsv")
        concatenate(table, "expectations.tsv", "expectations-core-misses.tsv")
        code, lines = self.lookup(self.core, table)
        self.assert_clean(code, lines, rows(table))

    def test_lookup_negative_controls_fail_for_the_stated_reason(self):
        with open(os.path.join(QT, "negative-lookup.tsv"), encoding="utf-8") as handle:
            table = [line.rstrip("\n") for line in handle if line.strip()]
        self.assertEqual(len(table), len(LOOKUP_NEGATIVES))
        for line, (name, reason) in zip(table, LOOKUP_NEGATIVES):
            single = self.path("single.tsv")
            with open(single, "w", encoding="utf-8") as handle:
                handle.write(line + "\n")
            code, lines = self.lookup(self.full, single)
            self.assertEqual(code, 1, line)
            failures = [l for l in lines if l[0] == "FAIL"]
            self.assertEqual(len(failures), 1, line)
            self.assertEqual(failures[0][1], name)
            self.assertIn(reason, failures[0][3], line)

    def run_single(self, root, line):
        table = self.path("one.tsv")
        with open(table, "w", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return self.lookup(root, table)

    def test_tampered_file_is_detected(self):
        path = os.path.join(self.full, "Resina/scalable/places/folder.svg")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n")
        code, lines = self.run_single(self.full, "folder\town\t")
        self.assertEqual(code, 1)
        self.assertIn("differs from the manifest", [l for l in lines if l[0] == "FAIL"][0][3])

    def test_swapped_artwork_is_detected(self):
        base = os.path.join(self.full, "Resina/scalable")
        shutil.copyfile(os.path.join(base, "devices/computer.svg"), os.path.join(base, "places/folder.svg"))
        code, lines = self.run_single(self.full, "folder\town\t")
        self.assertEqual(code, 1)
        self.assertIn("differs from the manifest", [l for l in lines if l[0] == "FAIL"][0][3])

    def test_same_name_decoy_does_not_stand_in_for_a_missing_own_icon(self):
        os.remove(os.path.join(self.full, "Resina/scalable/devices/computer.svg"))
        code, lines = self.run_single(self.full, "computer" + chr(9) + "own" + chr(9))
        self.assertEqual(code, 1)
        failures = [l for l in lines if l[0] == "FAIL"]
        self.assertEqual(len(failures), 1)
        self.assertIn("not present in theme tree", failures[0][3])

    def test_unlisted_file_is_detected(self):
        manifest = os.path.join(self.full, "Resina/MANIFEST.core")
        with open(manifest, encoding="utf-8") as handle:
            kept = [l for l in handle.read().splitlines() if not l.endswith(" scalable/places/folder.svg")]
        with open(manifest, "w", encoding="utf-8") as handle:
            handle.write("\n".join(kept) + "\n")
        code, lines = self.run_single(self.full, "folder\town\t")
        self.assertEqual(code, 1)
        self.assertIn("not listed in the manifest", [l for l in lines if l[0] == "FAIL"][0][3])

    def test_installed_lookup_through_the_default_search_paths(self):
        platform = display_platform()
        if not platform:
            self.skipTest("no display server: set RESINA_QT_PLATFORM or provide DISPLAY or WAYLAND_DISPLAY")
        data = self.path("data")
        icons = os.path.join(data, "icons")
        os.makedirs(icons)
        env = dict(self.env, QT_QPA_PLATFORM=platform, XDG_DATA_HOME=data, XDG_DATA_DIRS=self.path("no-system-icons"))
        present = self.path("present.tsv")
        gone = self.path("gone.tsv")
        concatenate(present, "expectations.tsv", "expectations-thirdparty.tsv")
        with open(present, encoding="utf-8") as handle:
            parsed = [l.rstrip("\n").split("\t") for l in handle if l.strip()]
        wanted = [row for row in parsed if row[1] != "fallback"]
        decoys = {f[:-4] for f in os.listdir(os.path.join(QT, "fixtures/hicolor/scalable/apps"))}
        with open(present, "w", encoding="utf-8") as handle:
            handle.write("".join("\t".join(w) + "\n" for w in wanted))
        with open(gone, "w", encoding="utf-8") as handle:
            handle.write("".join("%s\tmiss\t\n" % w[0] for w in wanted if w[0] not in decoys))
        install.install(self.full + "/Resina", icons)
        code, lines = self.lookup(data, present, env, "--default-paths")
        self.assert_clean(code, lines, len(wanted))
        install.uninstall(icons)
        code, lines = self.lookup(data, gone, env, "--default-paths")
        self.assert_clean(code, lines, len([w for w in wanted if w[0] not in decoys]))

    def quick(self, cells, root, scale=None):
        return self.probe("quickprobe", "--root", root, "--qml", os.path.join(QT, "quick_cells.qml"), "--cells", cells, scale=scale)

    def test_quick_controls_at_scales(self):
        table = self.path("cells.tsv")
        concatenate(table, "quick_cells.tsv", "quick_cells_thirdparty.tsv")
        for scale in (1, 2, 1.5):
            code, lines = self.quick(table, self.full, scale)
            self.assertEqual([l for l in lines if l[0] == "FAIL"], [], "scale %s" % scale)
            summary = [l for l in lines if l[0] == "SUMMARY"][0]
            self.assertEqual((int(summary[1]), int(summary[2])), (rows(table), 0), "scale %s" % scale)
            self.assertEqual(code, 0)

    def test_quick_negative_controls_fail_for_the_stated_reason(self):
        code, lines = self.quick(os.path.join(QT, "quick_cells_negative.tsv"), self.full)
        self.assertEqual(code, 1)
        failures = {l[1]: l[-1] for l in lines if l[0] == "FAIL"}
        self.assertEqual(sorted(failures), sorted(QUICK_NEGATIVES))
        for cell, reason in QUICK_NEGATIVES.items():
            self.assertIn(reason, failures[cell], cell)
        self.assertEqual([l for l in lines if l[0] == "PASS"], [])

    def test_a_tampered_theme_file_fails_the_quick_probe(self):
        path = os.path.join(self.full, "Resina/scalable/places/folder.svg")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n")
        table = self.path("one.tsv")
        with open(table, "w", encoding="utf-8") as handle:
            handle.write("c48\tfolder\t48\ttransparent\t#ECE8DF\t1\toriginal\n")
        code, lines = self.quick(table, self.full)
        self.assertEqual(code, 1)
        self.assertIn("differs from the manifest", [l for l in lines if l[0] == "FAIL"][0][-1])

    def test_malformed_cell_rows_abort_the_probe(self):
        table = self.path("bad.tsv")
        with open(table, "w", encoding="utf-8") as handle:
            handle.write("only\ttwo\n")
        code, _ = self.quick(table, self.full)
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
