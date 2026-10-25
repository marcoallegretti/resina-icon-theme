# SPDX-License-Identifier: EUPL-1.2
import os
import shutil
import unittest

import support
import install
import themebuild
import validate


class ValidatorRuleTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.path("repo")
        support.make_repo(self.repo)
        self.theme = self.path("Resina")
        themebuild.build(self.repo, self.theme, "full")
        self.target = os.path.join(self.theme, "scalable/places/folder.svg")
        with open(self.target, encoding="utf-8") as handle:
            self.original = handle.read()

    def codes(self, text):
        with open(self.target, "w", encoding="utf-8") as handle:
            handle.write(text)
        return {f.code for f in validate.validate(self.theme, manifests=False)}

    def test_every_forbidden_element_is_reported(self):
        for name in sorted(validate.FORBIDDEN):
            codes = self.codes(self.original.replace("</svg>", "<%s/></svg>" % name))
            self.assertTrue(codes & {"svg-forbidden-element", "svg-foreign-element"}, name)

    def test_every_forbidden_attribute_is_reported(self):
        for name in sorted(validate.FORBIDDEN_ATTRIBUTES):
            codes = self.codes(self.original.replace("<path", '<path %s="x"' % name, 1))
            self.assertIn("svg-forbidden-attribute", codes, name)

    def test_event_and_external_references_are_reported(self):
        self.assertIn("svg-event-attribute", self.codes(self.original.replace("<path", '<path onclick="x"', 1)))
        self.assertIn("svg-external-reference", self.codes(self.original.replace("</svg>", '<rect width="1" height="1" fill="url(http://example.org/a)"/></svg>')))

    def test_unknown_data_attribute_is_reported_and_known_ones_are_not(self):
        self.assertIn("svg-data-attribute", self.codes(self.original.replace("<path", '<path data-x="1"', 1)))
        for name in sorted(validate.ALLOWED_DATA_ATTRIBUTES):
            self.assertNotIn("svg-data-attribute", self.codes(self.original.replace("<path", '<path %s="1"' % name, 1)))

    def test_wrong_viewbox_is_reported(self):
        self.assertIn("svg-viewbox", self.codes(self.original.replace('viewBox="0 0 128 128"', 'viewBox="0 0 64 64"')))

    def test_empty_icon_is_reported(self):
        self.assertIn("svg-empty", self.codes('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"></svg>'))

    def test_dangling_reference_is_reported(self):
        self.assertIn("svg-dangling-reference", self.codes(self.original.replace("</svg>", '<rect width="1" height="1" fill="url(#nowhere)"/></svg>')))

    def test_references_are_matched_without_regard_to_case(self):
        self.assertIn("svg-external-reference", self.codes(self.original.replace("</svg>", '<rect width="1" height="1" fill="URL(https://example.org/a)"/></svg>')))

    def test_icons_nested_deeper_than_a_context_directory_are_reported(self):
        deep = os.path.join(self.theme, "scalable/places/deeper")
        os.makedirs(deep)
        with open(os.path.join(deep, "x.svg"), "w", encoding="utf-8") as handle:
            handle.write(self.original)
        self.assertIn("unexpected-file", {f.code for f in validate.validate(self.theme, manifests=False)})

    def manifest_codes(self):
        return {f.code for f in validate.validate(self.theme)}

    def test_duplicate_manifest_lines_are_reported(self):
        path = os.path.join(self.theme, "MANIFEST.core")
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(chr(10).join(lines + [lines[0]]) + chr(10))
        self.assertIn("manifest-malformed", self.manifest_codes())

    def test_a_path_listed_by_two_manifests_is_reported(self):
        with open(os.path.join(self.theme, "MANIFEST.core"), encoding="utf-8") as handle:
            first = handle.read().splitlines()[0]
        with open(os.path.join(self.theme, "MANIFEST.thirdparty"), "a", encoding="utf-8") as handle:
            handle.write(first + chr(10))
        self.assertIn("manifest-duplicate", self.manifest_codes())

    def test_unsafe_manifest_component_names_are_reported(self):
        shutil.copyfile(os.path.join(self.theme, "MANIFEST.core"), os.path.join(self.theme, "MANIFEST.Core_1"))
        self.assertIn("manifest-component", self.manifest_codes())

    def symbolic_path(self):
        return os.path.join(self.theme, "symbolic/actions/go-next-symbolic.svg")

    def with_symbolic(self, transform):
        with open(self.symbolic_path(), encoding="utf-8") as handle:
            text = handle.read()
        with open(self.symbolic_path(), "w", encoding="utf-8") as handle:
            handle.write(transform(text))
        return {f.code for f in validate.validate(self.theme, manifests=False)}

    def test_the_colour_scheme_style_block_is_accepted_only_in_its_exact_form(self):
        self.assertEqual(self.with_symbolic(lambda t: t), set())
        self.assertIn("svg-forbidden-element", self.with_symbolic(lambda t: t.replace("{color:#868686;}", "{color:#868686;fill:red}")))

    def test_other_style_blocks_and_classes_are_still_reported(self):
        self.assertIn("svg-forbidden-element", self.with_symbolic(lambda t: t.replace('id="current-color-scheme"', 'id="other"')))
        self.assertIn("svg-forbidden-attribute", self.with_symbolic(lambda t: t.replace('class="ColorScheme-Text"', 'class="x"')))

    def test_the_colour_scheme_style_block_is_not_accepted_in_colour_icons(self):
        block = '<defs><style type="text/css" id="current-color-scheme">.ColorScheme-Text{color:#868686;}</style></defs>'
        self.assertIn("svg-forbidden-element", self.codes(self.original.replace("</svg>", block + "</svg>")))

    def test_validator_constants_match_the_baker(self):
        import svgbake

        self.assertEqual(
            (validate.COLOUR_SCHEME_ID, validate.COLOUR_SCHEME_CLASS, validate.COLOUR_SCHEME_RULE),
            (svgbake.COLOUR_SCHEME_ID, svgbake.COLOUR_SCHEME_CLASS, svgbake.COLOUR_SCHEME_RULE),
        )

    def test_css_escapes_in_attribute_values_are_reported(self):
        escaped = self.original.replace("</svg>", '<rect width="1" height="1" fill="' + chr(92) + '75 rl(b.svg#g)"/></svg>')
        self.assertIn("svg-escape", self.codes(escaped))

    def test_an_icon_theme_cache_at_the_root_is_accepted(self):
        with open(os.path.join(self.theme, "icon-theme.cache"), "wb") as handle:
            handle.write(b"cache")
        self.assertEqual(validate.validate(self.theme, repo=self.repo), [])

    def test_wrong_root_is_reported(self):
        self.assertIn("svg-root", self.codes('<html xmlns="http://www.w3.org/2000/svg"/>'))


class InstallerNameRuleTests(unittest.TestCase):
    def test_unsafe_paths_are_refused(self):
        for rel in ("/abs", "a//b", "a/../b", "./a", "a/./b", "a/", ".resina-install-1-x", "MANIFEST.core", "PENDING.core", "a/" + "x" * 201, "a/b\x01c"):
            with self.assertRaises(install.InstallError, msg=repr(rel)):
                install.safe(rel)

    def test_ordinary_paths_are_accepted(self):
        for rel in ("index.theme", "scalable/apps/org.example.App.svg", "symbolic/actions/go-next-symbolic.svg"):
            install.safe(rel)

    def test_manifest_entries_need_a_valid_digest_and_decimal_size(self):
        good = "F " + "a" * 64 + " 5 scalable/apps/x.svg"
        self.assertIn("scalable/apps/x.svg", install.parse_manifest(good + "\n", "t"))
        for line in (
            "F " + "A" * 64 + " 5 x.svg",
            "F " + "a" * 63 + " 5 x.svg",
            "F " + "a" * 64 + " five x.svg",
            "F " + "a" * 64 + " ٥ x.svg",
            "X " + "a" * 64 + " 5 x.svg",
            "L x.svg",
        ):
            with self.assertRaises(install.InstallError, msg=line):
                install.parse_manifest(line + "\n", "t")


if __name__ == "__main__":
    unittest.main()
