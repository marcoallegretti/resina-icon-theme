# SPDX-License-Identifier: EUPL-1.2
import os

import support
import themebuild
import validate


class BuildTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.path("repo")
        support.make_repo(self.repo)

    def build(self, name, profile="full"):
        out = self.path(name)
        themebuild.build(self.repo, out, profile)
        return out

    def listing(self, out, directory):
        return sorted(os.listdir(os.path.join(out, directory)))

    def test_full_profile_is_valid(self):
        self.assertEqual(validate.validate(self.build("Resina"), repo=self.repo), [])

    def test_builds_are_identical(self):
        self.assertEqual(support.tree_digest(self.build("one")), support.tree_digest(self.build("two")))

    def test_alias_points_at_target(self):
        link = os.path.join(self.build("Resina"), "scalable/apps/org.example.Beta.svg")
        self.assertEqual(os.readlink(link), "beta.svg")

    def test_application_id_case_preserved(self):
        apps = self.listing(self.build("Resina"), "scalable/apps")
        self.assertIn("org.example.Beta.svg", apps)
        self.assertNotIn("org.example.beta.svg", apps)

    def test_category_names_routed(self):
        self.assertTrue(os.path.isfile(os.path.join(self.build("Resina"), "scalable/categories/applications-games.svg")))

    def test_symbolic_suffix_and_context(self):
        out = self.build("Resina")
        self.assertTrue(os.path.isfile(os.path.join(out, "symbolic/actions/go-next-symbolic.svg")))
        self.assertTrue(os.path.islink(os.path.join(out, "symbolic/actions/pan-end-symbolic.svg")))
        self.assertTrue(os.path.isfile(os.path.join(out, "symbolic/emblems/emblem-ok-symbolic.svg")))

    def test_core_profile_excludes_thirdparty(self):
        out = self.build("core", "core")
        self.assertIn("alpha.svg", self.listing(out, "scalable/apps"))
        self.assertNotIn("beta.svg", self.listing(out, "scalable/apps"))
        self.assertNotIn("org.example.Beta.svg", self.listing(out, "scalable/apps"))
        self.assertEqual(self.listing(out, "scalable/places"), ["folder.svg", "game-folder.svg"])
        self.assertEqual(validate.validate(out, repo=self.repo), [])

    def test_thirdparty_overlay_has_only_thirdparty(self):
        out = self.build("tp", "thirdparty")
        self.assertEqual(self.listing(out, "scalable/apps"), ["beta.svg", "org.example.Beta.svg"])
        self.assertEqual(self.listing(out, "scalable/places"), ["folder-github.svg"])
        self.assertFalse(os.path.exists(os.path.join(out, "index.theme")))

    def test_symbolic_thirdparty_is_separated(self):
        core = self.build("core", "core")
        overlay = self.build("tp", "thirdparty")
        self.assertTrue(os.path.exists(os.path.join(core, "symbolic/emblems/emblem-ok-symbolic.svg")))
        self.assertFalse(os.path.exists(os.path.join(core, "symbolic/emblems/emblem-brand-symbolic.svg")))
        self.assertTrue(os.path.exists(os.path.join(overlay, "symbolic/emblems/emblem-brand-symbolic.svg")))

    def test_licence_texts_ship_with_the_theme(self):
        out = self.build("Resina")
        for name in ("NOTICE", "EUPL-1.2.txt", "OFL-1.1.txt"):
            self.assertTrue(os.path.isfile(os.path.join(out, name)), name)
        with open(os.path.join(out, "MANIFEST.core"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(" OFL-1.1.txt\n", text)

    def test_baked_output_is_free_of_unsupported_features(self):
        out = self.build("Resina")
        with open(os.path.join(out, "scalable/places/folder.svg"), encoding="utf-8") as handle:
            text = handle.read()
        for forbidden in ("feMorphology", "clip-path", "clipPath", 'filter="url(#rim)"'):
            self.assertNotIn(forbidden, text)

    def test_output_must_not_exist(self):
        os.makedirs(self.path("exists"))
        with self.assertRaises(themebuild.BuildError):
            themebuild.build(self.repo, self.path("exists"), "full")

    def test_alias_to_missing_target_fails(self):
        support.write(os.path.join(self.repo, "aliases/color.tsv"), "ghost\tapps/missing\n")
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_alias_collision_fails(self):
        support.write(os.path.join(self.repo, "aliases/color.tsv"), "alpha\tapps/beta\n")
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_duplicate_alias_fails(self):
        support.write(os.path.join(self.repo, "aliases/color.tsv"), "dup\tapps/beta\ndup\tapps/alpha\n")
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_unsafe_alias_names_fail_before_anything_is_written(self):
        for name in ("../escape", "a/b", ".hidden", "x.svg", "", "-dash"):
            support.write(os.path.join(self.repo, "aliases/color.tsv"), "%s\tapps/beta\n" % name)
            out = self.path("unsafe-" + str(abs(hash(name))))
            with self.assertRaises(themebuild.BuildError, msg=repr(name)):
                themebuild.build(self.repo, out, "full")
            self.assertFalse(os.path.lexists(out), repr(name))
        self.assertFalse(os.path.exists(self.path("escape.svg")))

    def test_unclassified_colour_icon_fails(self):
        support.write(os.path.join(self.repo, "names/color-classes.tsv"), "apps/alpha\tcore\n")
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_class_for_missing_icon_fails(self):
        with open(os.path.join(self.repo, "names/color-classes.tsv"), "a", encoding="utf-8") as handle:
            handle.write("apps/ghost\tcore\n")
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_duplicate_class_entry_fails(self):
        with open(os.path.join(self.repo, "names/color-classes.tsv"), "a", encoding="utf-8") as handle:
            handle.write("apps/alpha\tthirdparty\n")
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_invalid_class_value_fails(self):
        support.write(os.path.join(self.repo, "names/color-classes.tsv"), "".join("%s\tmaybe\n" % key for key in support.COLOR_ICONS))
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_symbolic_without_context_fails(self):
        support.write(os.path.join(self.repo, "names/symbolic-contexts.tsv"), "go-next\tActions\n")
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_symbolic_without_class_fails(self):
        support.write(os.path.join(self.repo, "names/symbolic-classes.tsv"), "go-next\tcore\nemblem-ok\tcore\n")
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_directory_only_in_thirdparty_fails(self):
        support.write(
            os.path.join(self.repo, "names/symbolic-classes.tsv"),
            "emblem-brand\tthirdparty\nemblem-ok\tthirdparty\ngo-next\tcore\n",
        )
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_unsupported_source_fails_with_the_icon_name(self):
        support.write(os.path.join(self.repo, "src/symbolic/go-next.svg"), support.SYMBOLIC_SVG.replace("<path", '<path style="x"'))
        with self.assertRaises(themebuild.BuildError) as raised:
            self.build("Resina")
        self.assertIn("go-next-symbolic", str(raised.exception))

    def test_thirdparty_overlay_ships_its_own_licence_texts(self):
        out = self.build("overlay", "thirdparty")
        for name in ("NOTICE.thirdparty", "EUPL-1.2.thirdparty.txt", "OFL-1.1.thirdparty.txt"):
            self.assertTrue(os.path.isfile(os.path.join(out, name)), name)
        self.assertFalse(os.path.exists(os.path.join(out, "NOTICE")))
        self.assertEqual(validate.validate(out, repo=self.repo, index=False), [])

    def test_alias_owner_column_moves_the_link_to_the_overlay(self):
        support.write(os.path.join(self.repo, "aliases/color.tsv"), "org.example.Beta" + chr(9) + "apps/alpha" + chr(9) + "thirdparty" + chr(10))
        core = self.build("core", "core")
        self.assertFalse(os.path.lexists(os.path.join(core, "scalable/apps/org.example.Beta.svg")))
        full = self.build("full")
        self.assertTrue(os.path.islink(os.path.join(full, "scalable/apps/org.example.Beta.svg")))

    def test_unknown_alias_owner_fails(self):
        support.write(os.path.join(self.repo, "aliases/color.tsv"), "ghost" + chr(9) + "apps/beta" + chr(9) + "other" + chr(10))
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_alias_of_a_category_name_is_copied_into_the_categories_directory(self):
        support.write(os.path.join(self.repo, "aliases/color.tsv"), "applications-office" + chr(9) + "apps/alpha" + chr(10))
        out = self.build("Resina")
        copy = os.path.join(out, "scalable/categories/applications-office.svg")
        self.assertTrue(os.path.isfile(copy) and not os.path.islink(copy))
        self.assertFalse(os.path.lexists(os.path.join(out, "scalable/apps/applications-office.svg")))
        self.assertEqual(support.sha256_file(copy), support.sha256_file(os.path.join(out, "scalable/apps/alpha.svg")))
        self.assertEqual(validate.validate(out, repo=self.repo), [])

    def test_symbolic_alias_is_placed_by_its_own_context(self):
        support.write(os.path.join(self.repo, "aliases/symbolic.tsv"), "pan-up" + chr(9) + "go-next" + chr(10))
        out = self.build("Resina")
        self.assertTrue(os.path.isfile(os.path.join(out, "symbolic/status/pan-up-symbolic.svg")))
        self.assertTrue(os.path.islink(os.path.join(out, "symbolic/status/pan-up.svg")))
        self.assertEqual(validate.validate(out, repo=self.repo), [])

    def test_stray_source_file_fails(self):
        support.write(os.path.join(self.repo, "src/color/apps/notes.txt"), "x")
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_stray_source_directory_fails(self):
        os.makedirs(os.path.join(self.repo, "src/color/extra"))
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_symlinked_source_fails(self):
        target = os.path.join(self.repo, "src/color/apps/alpha.svg")
        os.symlink(target, os.path.join(self.repo, "src/color/apps/gamma.svg"))
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_names_differing_only_in_case_fail(self):
        with open(os.path.join(self.repo, "src/color/apps/alpha.svg"), "rb") as handle:
            data = handle.read()
        with open(os.path.join(self.repo, "src/color/apps/Alpha.svg"), "wb") as handle:
            handle.write(data)
        with open(os.path.join(self.repo, "names/color-classes.tsv"), "a", encoding="utf-8", newline="") as handle:
            handle.write("apps/Alpha" + chr(9) + "core" + chr(10))
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_unknown_profile_fails(self):
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina", "nonsense")

    def test_animation_sheets_are_built_for_every_size(self):
        out = self.build("Resina")
        for size in themebuild.ANIMATION_SIZES:
            path = os.path.join(out, "animations/%d/process-working.svg" % size)
            text = open(path, encoding="utf-8").read()
            self.assertIn('viewBox="0 0 %d %d"' % (4 * size, 3 * size), text)
            self.assertEqual(text.count("<g "), 12)
        index = open(os.path.join(out, "index.theme"), encoding="utf-8").read()
        self.assertIn("[animations/22]" + chr(10) + "Context=Animations" + chr(10) + "Size=22" + chr(10) + "Type=Fixed", index)

    def test_mirrored_variant_sits_beside_the_symbolic_icon(self):
        out = self.build("Resina")
        plain = open(os.path.join(out, "symbolic/actions/go-next-symbolic.svg"), encoding="utf-8").read()
        mirrored = open(os.path.join(out, "symbolic/actions/go-next-symbolic-rtl.svg"), encoding="utf-8").read()
        self.assertNotIn("matrix(-1 0 0 1 24 0)", plain)
        self.assertIn("matrix(-1 0 0 1 24 0)", mirrored)

    def test_mirrored_variant_of_an_alias_uses_the_target_drawing(self):
        support.write(os.path.join(self.repo, "names/rtl-mirrors.txt"), "pan-end" + chr(10))
        out = self.build("Resina")
        self.assertTrue(os.path.isfile(os.path.join(out, "symbolic/actions/pan-end-symbolic-rtl.svg")))
        self.assertEqual(validate.validate(out, repo=self.repo), [])

    def test_mirrored_variant_needs_a_symbolic_icon(self):
        support.write(os.path.join(self.repo, "names/rtl-mirrors.txt"), "no-such-icon" + chr(10))
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_drawn_variant_replaces_the_mirror(self):
        support.write(os.path.join(self.repo, "names/rtl-mirrors.txt"), "")
        drawing = support.SYMBOLIC_SVG.replace("M9 6l6 6-6 6", "M15 6l-6 6 6 6")
        support.write(os.path.join(self.repo, "src/symbolic-rtl/go-next.svg"), drawing)
        out = self.build("Resina")
        self.assertIn("M15.707 6.707", open(os.path.join(out, "symbolic/actions/go-next-symbolic-rtl.svg"), encoding="utf-8").read())
        self.assertNotIn("matrix(-1 0 0 1 24 0)", open(os.path.join(out, "symbolic/actions/go-next-symbolic-rtl.svg"), encoding="utf-8").read())
        self.assertTrue(os.path.isfile(os.path.join(out, "symbolic/actions/pan-end-symbolic-rtl.svg")))

    def test_icon_cannot_be_both_mirrored_and_drawn(self):
        support.write(os.path.join(self.repo, "src/symbolic-rtl/go-next.svg"), support.SYMBOLIC_SVG)
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_drawn_variant_needs_a_symbolic_icon(self):
        support.write(os.path.join(self.repo, "src/symbolic-rtl/no-such-icon.svg"), support.SYMBOLIC_SVG)
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")

    def test_duplicate_mirror_entry_fails(self):
        support.write(os.path.join(self.repo, "names/rtl-mirrors.txt"), "go-next" + chr(10) + "go-next" + chr(10))
        with self.assertRaises(themebuild.BuildError):
            self.build("Resina")


if __name__ == "__main__":
    import unittest

    unittest.main()
