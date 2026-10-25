# SPDX-License-Identifier: EUPL-1.2
import importlib.util
import os
import unittest

import support

HARFBUZZ = importlib.util.find_spec("uharfbuzz") is not None
FONT = os.environ.get("RESINA_FONT")

BADGE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><text x="64" y="98" text-anchor="middle" '
    'font-family="Atkinson Hyperlegible Next, Cantarell" font-weight="800" font-size="18" letter-spacing=".5" fill="#fff">%s</text></svg>'
)


@unittest.skipUnless(HARFBUZZ, "uharfbuzz is required (requirements-sources.txt)")
class FontPinTests(support.TempCase):
    def test_wrong_digest_is_refused(self):
        import textoutline

        path = self.path("font.ttf")
        with open(path, "wb") as handle:
            handle.write(b"not a font")
        with self.assertRaises(textoutline.OutlineError):
            textoutline.Face(path, textoutline.FONT_SHA256)

    def test_missing_font_is_reported_by_the_command_line(self):
        import textoutline

        self.assertEqual(textoutline.main(["--font", self.path("absent.ttf"), self.path("")]), 1)

    def test_pin_is_recorded(self):
        import textoutline

        self.assertEqual(len(textoutline.FONT_SHA256), 64)
        self.assertEqual(len(textoutline.FONT_SOURCE_COMMIT), 40)


@unittest.skipUnless(HARFBUZZ and FONT, "set RESINA_FONT to the pinned font file and install requirements-sources.txt")
class OutlineTests(support.TempCase):
    def setUp(self):
        super().setUp()
        import textoutline

        self.module = textoutline
        self.face = textoutline.Face(FONT, textoutline.FONT_SHA256)

    def test_badge_text_becomes_a_path(self):
        result, count = self.module.outline_svg(self.face, (BADGE % "PDF").encode())
        self.assertEqual(count, 1)
        self.assertNotIn(b"<text", result)
        self.assertIn(b"<path", result)

    def test_missing_glyph_fails(self):
        with self.assertRaises(self.module.OutlineError):
            self.module.outline_svg(self.face, (BADGE % "Σ").encode())

    def test_unexpected_weight_fails(self):
        with self.assertRaises(self.module.OutlineError):
            self.module.outline_svg(self.face, (BADGE % "PDF").replace('font-weight="800"', 'font-weight="400"').encode())

    def test_unexpected_family_fails(self):
        with self.assertRaises(self.module.OutlineError):
            self.module.outline_svg(self.face, (BADGE % "PDF").replace("Atkinson Hyperlegible Next", "Other").encode())

    def test_directory_rewrite_is_all_or_nothing(self):
        support.write(os.path.join(self.tmp, "a.svg"), BADGE % "PDF")
        support.write(os.path.join(self.tmp, "b.svg"), BADGE % "Σ")
        with self.assertRaises(self.module.OutlineError):
            self.module.rewrite_directory(self.face, self.tmp)
        with open(os.path.join(self.tmp, "a.svg"), encoding="utf-8") as handle:
            self.assertIn("<text", handle.read())

    def test_outlining_is_deterministic(self):
        first = self.module.outline_svg(self.face, (BADGE % "JSON").encode())
        second = self.module.outline_svg(self.face, (BADGE % "JSON").encode())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
