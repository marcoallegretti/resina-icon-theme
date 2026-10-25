# SPDX-License-Identifier: EUPL-1.2
import os
import re
import shutil
import subprocess
import unittest

import support
import geometry
import svgbake
import themebuild
import validate

DATA = os.path.join(support.HERE, "data")
GOLDEN = os.path.join(support.HERE, "golden", "manifests.sha256")
ROOT_SRC = os.path.join(support.ROOT, "src", "color")


def count_svgs(directory):
    return sum(1 for dirpath, _, files in os.walk(directory) for f in files if f.endswith(".svg"))


def count_lines(path):
    with open(path, encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


class RealTreeTests(support.TempCase):
    trees = {}

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls.root = tempfile.mkdtemp(prefix="resina-real-")
        for profile in themebuild.PROFILES:
            cls.trees[profile] = os.path.join(cls.root, profile, "Resina")
            themebuild.build(support.ROOT, cls.trees[profile], profile)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        cls.trees = {}

    def names(self, profile):
        found = []
        for dirpath, dirs, files in os.walk(self.trees[profile]):
            for name in files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]:
                if name.endswith(".svg"):
                    found.append(name[:-4])
        return found

    def test_every_profile_validates_against_the_sources(self):
        self.assertEqual(validate.validate(self.trees["full"], repo=support.ROOT), [])
        self.assertEqual(validate.validate(self.trees["core"], repo=support.ROOT), [])
        self.assertEqual(validate.validate(self.trees["thirdparty"], repo=support.ROOT, index=False), [])

    def test_colour_icons_follow_the_context_of_the_naming_specification(self):
        full = self.trees["full"]
        for name in ("preferences-desktop-peripherals", "preferences-desktop-personal", "applications-science"):
            self.assertTrue(os.path.isfile(os.path.join(full, "scalable/categories", name + ".svg")), name)
            self.assertFalse(os.path.exists(os.path.join(full, "scalable/apps", name + ".svg")), name)

    def test_icon_and_alias_counts_match_the_data(self):
        full = self.trees["full"]
        icons = count_svgs(os.path.join(support.ROOT, "src"))
        aliases = count_lines(os.path.join(support.ROOT, "aliases", "color.tsv")) + count_lines(
            os.path.join(support.ROOT, "aliases", "symbolic.tsv")
        )
        files = sum(1 for p, _, fs in os.walk(full) for f in fs if f.endswith(".svg") and not os.path.islink(os.path.join(p, f)))
        alias_links, plain_links = 0, 0
        for p, _, fs in os.walk(full):
            for f in fs:
                path = os.path.join(p, f)
                if not os.path.islink(path):
                    continue
                target = os.readlink(path)
                if f.endswith("-symbolic.svg") or not target.endswith("-symbolic.svg"):
                    alias_links += 1
                else:
                    plain_links += 1
                    self.assertTrue(os.path.isfile(os.path.join(p, target)), path)
                    self.assertEqual(os.path.basename(p) in ("actions", "apps", "status", "devices", "emblems", "categories"), True, path)
        plan = themebuild.Plan(support.ROOT)
        plan.collect()
        copies = len(plan.copies)
        self.assertGreater(copies, 20)
        rtl = sum(1 for p, _, fs in os.walk(full) for f in fs if f.endswith("-symbolic-rtl.svg"))
        compact_files, compact_links = 0, 0
        for tier in ("places-small", "places-medium"):
            tier_dir = os.path.join(full, "scalable", tier)
            names = os.listdir(tier_dir)
            compact_links += sum(1 for f in names if os.path.islink(os.path.join(tier_dir, f)))
            compact_files += sum(1 for f in names if not os.path.islink(os.path.join(tier_dir, f)))
        designed = sum(count_svgs(os.path.join(support.ROOT, "src", "color", tier)) for tier in ("places-small", "places-medium"))
        self.assertEqual(
            files,
            icons - designed - len(plan.drawn) + copies + rtl + len(themebuild.ANIMATION_SIZES) * len(themebuild.ANIMATED_ICONS) + compact_files,
        )
        self.assertEqual((len(plan.mirrors), len(plan.drawn), rtl), (49, 7, 59))
        self.assertEqual(alias_links - compact_links, aliases - copies)
        self.assertGreater(plain_links, 500)

    def test_folder_tiers_exist_for_every_folder_with_a_symbol_and_the_index_keeps_the_ranges_apart(self):
        full = self.trees["full"]
        large = os.path.join(full, "scalable/places")
        for tier in ("places-small", "places-medium"):
            directory = os.path.join(full, "scalable", tier)
            missing = [name for name in sorted(os.listdir(large)) if not os.path.exists(os.path.join(directory, name))]
            self.assertEqual(missing, [], tier)
        for tier in ("places-small", "places-medium"):
            for name in os.listdir(os.path.join(ROOT_SRC, tier)):
                path = os.path.join(full, "scalable", tier, name)
                self.assertTrue(os.path.isfile(path) and not os.path.islink(path), name)
        with open(os.path.join(full, "index.theme"), encoding="utf-8") as handle:
            index = handle.read()
        self.assertIn("[scalable/places]\nContext=Places\nSize=128\nMinSize=65\nMaxSize=512\n", index)
        self.assertIn("[scalable/places-small]\nContext=Places\nSize=22\nMinSize=16\nMaxSize=24\n", index)
        self.assertIn("[scalable/places-medium]\nContext=Places\nSize=48\nMinSize=25\nMaxSize=64\n", index)

    def test_aliases_sit_in_the_directory_of_their_naming_specification_context(self):
        plan = themebuild.Plan(support.ROOT)
        plan.collect()
        placed = [rel for rel, _ in plan.links] + list(plan.copies)
        directories = dict(themebuild.COLOR_SPEC_DIRECTORIES)
        mismatches = []
        for rel in placed:
            family, directory, filename = rel.split("/")
            name = filename[:-4]
            if family == "symbolic" and name.endswith("-symbolic"):
                name = name[:-9]
            context = plan.spec.get(name)
            if not context:
                continue
            wanted = themebuild.SYMBOLIC_DIRS.get(context) if family == "symbolic" else directories.get(context)
            if wanted and wanted != directory:
                mismatches.append(rel)
        self.assertEqual(mismatches, [])

    def test_naming_specification_table_uses_known_contexts(self):
        plan = themebuild.Plan(support.ROOT)
        self.assertTrue(set(plan.spec.values()) <= set(themebuild.SYMBOLIC_DIRS))
        self.assertGreater(len(plan.spec), 250)

    def test_launcher_icon_names_of_the_major_desktops_resolve_to_colour_icons(self):
        with open(os.path.join(DATA, "launcher-icons.txt"), encoding="utf-8") as handle:
            names = [line.strip() for line in handle if line.strip()]
        self.assertGreater(len(names), 60)
        missing = []
        for name in names:
            found = [
                os.path.join(self.trees["full"], "scalable", group, name + ".svg")
                for group in os.listdir(os.path.join(self.trees["full"], "scalable"))
            ]
            if not any(os.path.lexists(path) for path in found):
                missing.append(name)
        self.assertEqual(missing, [])

    def test_core_and_thirdparty_partition_the_full_set(self):
        core, thirdparty, full = set(self.names("core")), set(self.names("thirdparty")), set(self.names("full"))
        self.assertEqual(core & thirdparty, set())
        self.assertEqual(core | thirdparty, full)

    def test_core_contains_no_brand_named_icon(self):
        with open(os.path.join(DATA, "brand-keywords.txt"), encoding="utf-8") as handle:
            keywords = [line.strip().lower() for line in handle if line.strip()]
        with open(os.path.join(DATA, "brand-allowlist.txt"), encoding="utf-8") as handle:
            allowed = {line.strip() for line in handle if line.strip()}
        offenders = sorted(
            name
            for name in self.names("core")
            if name not in allowed and any(token in keywords for token in re.split(r"[-._+]", name.lower()))
        )
        self.assertEqual(offenders, [])

    def test_allowlisted_names_exist(self):
        with open(os.path.join(DATA, "brand-allowlist.txt"), encoding="utf-8") as handle:
            allowed = {line.strip() for line in handle if line.strip()}
        self.assertEqual(sorted(allowed - set(self.names("core"))), [])

    def test_thirdparty_contains_icons_of_every_kind(self):
        found = set()
        for dirpath, _, files in os.walk(self.trees["thirdparty"]):
            if files and any(f.endswith(".svg") for f in files):
                found.add(os.path.relpath(dirpath, self.trees["thirdparty"]))
        for expected in ("scalable/apps", "scalable/places", "scalable/mimetypes", "symbolic/emblems"):
            self.assertIn(expected, found)

    def test_manifest_digests_match_the_golden_record(self):
        with open(GOLDEN, encoding="utf-8") as handle:
            recorded = dict(line.split()[::-1] for line in handle if line.strip())
        for profile, name in (("full", "MANIFEST.core"), ("full", "MANIFEST.thirdparty")):
            self.assertEqual(support.sha256_file(os.path.join(self.trees[profile], name)), recorded[name], name)

    def test_alias_targets_exist_and_share_a_directory(self):
        for dirpath, dirs, files in os.walk(self.trees["full"]):
            for name in files:
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    target = os.readlink(full)
                    self.assertNotIn("/", target)
                    self.assertTrue(os.path.isfile(os.path.join(dirpath, target)), full)

    def test_application_ids_keep_their_case(self):
        apps = os.listdir(os.path.join(self.trees["full"], "scalable/apps"))
        for name in ("org.inkscape.Inkscape.svg", "com.obsproject.Studio.svg", "io.github.quodlibet.QuodLibet.svg"):
            self.assertIn(name, apps)
        self.assertNotIn("org.inkscape.inkscape.svg", apps)

    def test_no_symbolic_icon_has_a_stroke_or_a_fixed_colour(self):
        for dirpath, _, files in os.walk(os.path.join(self.trees["full"], "symbolic")):
            for name in files:
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    continue
                with open(full, encoding="utf-8") as handle:
                    text = handle.read()
                self.assertNotIn("stroke=", text, name)
                self.assertNotIn("#", text.replace("url(#", "").replace(validate.COLOUR_SCHEME_RULE, ""), name)
                self.assertIn(validate.COLOUR_SCHEME_RULE, text, name)


@unittest.skipUnless(shutil.which("rsvg-convert") and shutil.which("compare"), "rsvg-convert and ImageMagick compare are required")
class SourceFidelityTests(support.TempCase):
    LIMIT = 0.09
    SAMPLES = ("places/folder", "apps/firefox", "apps/shelly", "apps/wireshark", "apps/hu.irl.cameractrls", "mimetypes/application-pdf", "devices/computer")

    def render(self, svg, png):
        subprocess.run(["rsvg-convert", "-w", "128", "-h", "128", "-b", "#ECE8DF", svg, "-o", png], check=True)

    def test_built_icons_resemble_their_sources(self):
        out = self.path("Resina")
        themebuild.build(support.ROOT, out, "full")
        plan = themebuild.Plan(support.ROOT)
        plan.collect()
        for key in self.SAMPLES:
            built = os.path.join(out, plan.color_dest[key])
            source = os.path.join(support.ROOT, "src", "color", key + ".svg")
            self.render(source, self.path("a.png"))
            self.render(built, self.path("b.png"))
            result = subprocess.run(["compare", "-metric", "RMSE", self.path("a.png"), self.path("b.png"), "null:"], capture_output=True, text=True)
            value = float(re.search(r"\(([0-9.e-]+)\)", result.stderr).group(1))
            self.assertLess(value, self.LIMIT, key)

    def differing_pixels(self, first, second):
        result = subprocess.run(["compare", "-metric", "AE", "-fuzz", "10%", first, second, "null:"], capture_output=True, text=True)
        return float(result.stderr.split()[0])

    def test_a_dropped_transform_would_be_detected(self):
        source = os.path.join(support.ROOT, "src/color/apps/shelly.svg")
        with open(source, "rb") as handle:
            data = handle.read()
        good = self.path("good.svg")
        with open(good, "wb") as handle:
            handle.write(svgbake.bake_rim(data))
        original = geometry.apply_transform
        geometry.apply_transform = lambda path, matrix: path
        try:
            broken = self.path("broken.svg")
            with open(broken, "wb") as handle:
                handle.write(svgbake.bake_rim(data))
        finally:
            geometry.apply_transform = original
        self.render(source, self.path("a.png"))
        self.render(good, self.path("b.png"))
        self.render(broken, self.path("c.png"))
        self.assertGreater(self.differing_pixels(self.path("a.png"), self.path("c.png")), 2 * self.differing_pixels(self.path("a.png"), self.path("b.png")))


if __name__ == "__main__":
    unittest.main()
