# SPDX-License-Identifier: EUPL-1.2
import unittest
import xml.etree.ElementTree as ET

import support
import geometry
import svgbake

NS = "{http://www.w3.org/2000/svg}"


def colour_svg(body, clips=""):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">'
        '<defs><filter id="rim"><feMorphology in="SourceAlpha" operator="dilate" radius="2" result="d"/>'
        '<feFlood flood-color="#a6622e"/><feComposite in2="d" operator="in"/>'
        '<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>%s</defs>'
        '<g filter="url(#rim)">%s</g></svg>' % (clips, body)
    ).encode()


def bounds_of(node):
    return geometry.to_path(node.get("d"), close=True).bounds


class RimBakeTests(unittest.TestCase):
    def setUp(self):
        self.baked = svgbake.bake_rim(support.COLOR_SVG.encode())
        self.root = ET.fromstring(self.baked)

    def names(self):
        return [e.tag.rsplit("}", 1)[-1] for e in self.root.iter()]

    def test_rim_filter_removed(self):
        self.assertNotIn("feMorphology", self.names())
        self.assertEqual([e for e in self.root.iter() if e.get("filter") == "url(#rim)"], [])
        self.assertEqual([e for e in self.root.iter(NS + "filter") if e.get("id") == "rim"], [])

    def test_clip_removed(self):
        self.assertNotIn("clipPath", self.names())
        self.assertEqual([e for e in self.root.iter() if e.get("clip-path")], [])

    def test_rim_group_precedes_content(self):
        kids = list(self.root)
        self.assertEqual(kids[1].get("id"), "rim")
        self.assertIsNone(kids[2].get("id"))

    def test_rim_uses_filter_colour(self):
        rim = list(self.root)[1]
        self.assertTrue(all("#a6622e" in (p.get("stroke"), p.get("fill")) for p in rim))

    def test_shadow_halo_is_enlarged_and_softened_without_a_filter(self):
        halos = [e for e in list(self.root)[1] if e.tag == NS + "ellipse"]
        self.assertGreaterEqual(len(halos), 5)
        self.assertEqual((halos[0].get("rx"), halos[0].get("ry")), ("48", "12"))
        self.assertTrue(all(h.get("filter") is None and h.get("fill") == "#a6622e" for h in halos))

    def test_inner_edge_band_area(self):
        band = geometry.stroke_band(geometry.to_path("M20 20H108V100H20Z"), 4)
        clip = geometry.to_path("M20 20H108V100H20Z", close=True)
        inner = geometry.intersect(band, clip)
        expected = 88 * 80 - 84 * 76
        self.assertAlmostEqual(inner.area, expected, delta=expected * 0.02)

    def test_inner_edge_band_stays_inside_clip(self):
        node = [p for p in self.root.iter(NS + "path") if p.get("fill") == "#fff"][0]
        left, top, right, bottom = bounds_of(node)
        self.assertGreaterEqual(left, 19.99)
        self.assertGreaterEqual(top, 19.99)
        self.assertLessEqual(right, 108.01)
        self.assertLessEqual(bottom, 100.01)

    def test_bake_is_deterministic(self):
        self.assertEqual(self.baked, svgbake.bake_rim(support.COLOR_SVG.encode()))

    def test_groups_with_different_rim_colours_each_get_their_own_rim(self):
        source = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><defs>'
            '<filter id="rim-red"><feMorphology in="SourceAlpha" operator="dilate" radius="2" result="d"/><feFlood flood-color="#aa0000"/></filter>'
            '<filter id="rim-blue"><feMorphology in="SourceAlpha" operator="dilate" radius="3" result="d"/><feFlood flood-color="#0000aa"/></filter></defs>'
            '<g filter="url(#rim-red)"><path d="M10 10H50V50H10Z" fill="#f00"/></g>'
            '<g filter="url(#rim-blue)"><path d="M70 70H110V110H70Z" fill="#00f"/></g></svg>'
        ).encode()
        root = ET.fromstring(svgbake.bake_rim(source))
        kids = list(root)
        self.assertEqual([k.get("id") for k in kids if k.get("id")], ["rim", "rim-2"])
        self.assertEqual({p.get("fill") for p in kids[1]}, {"#aa0000"})
        self.assertEqual({p.get("fill") for p in kids[3]}, {"#0000aa"})
        self.assertEqual([e for e in root.iter() if e.get("filter")], [])
        self.assertEqual(list(root.iter(NS + "filter")), [])

    def test_missing_rim_fails(self):
        with self.assertRaises(svgbake.BakeError):
            svgbake.bake_rim(support.COLOR_SVG.replace('id="rim"', 'id="other"').encode())

    def test_unknown_clip_reference_fails(self):
        with self.assertRaises(svgbake.BakeError):
            svgbake.bake_rim(support.COLOR_SVG.replace('url(#c1)"/></g>', 'url(#nope)"/></g>').encode())

    def test_clip_path_outside_defs_is_hoisted(self):
        root = ET.fromstring(support.COLOR_SVG.encode())
        svgbake.hoist_clip_paths(root)
        defs = root.find(NS + "defs")
        self.assertIn("clipPath", [c.tag.rsplit("}", 1)[-1] for c in defs])

    def test_hairline_stroke_adds_no_rim(self):
        baked = svgbake.bake_rim(colour_svg('<path d="M10 10H100" fill="none" stroke="#fff" stroke-width="0.01"/>'))
        self.assertEqual(len(list(list(ET.fromstring(baked))[1])), 0)

    def test_thin_stroke_rim_is_translucent(self):
        baked = svgbake.bake_rim(colour_svg('<path d="M10 10H100" fill="none" stroke="#fff" stroke-width="0.5"/>'))
        node = list(list(ET.fromstring(baked))[1])[0]
        self.assertEqual(node.get("opacity"), "0.5")
        self.assertEqual(node.get("stroke-width"), "4.5")


class ClipSpaceTests(unittest.TestCase):
    CLIP = '<clipPath id="c1"><path d="M0 0H40V40H0Z"/></clipPath>'

    def baked_paths(self, body):
        root = ET.fromstring(svgbake.bake_rim(colour_svg(body, self.CLIP)))
        content = list(root)[2]
        return [p for p in content.iter(NS + "path")]

    def test_leaf_clip_follows_the_element_transform(self):
        body = '<path d="M0 0H40V40H0Z" fill="#fff" transform="translate(50 10)" clip-path="url(#c1)"/>'
        left, top, right, bottom = bounds_of(self.baked_paths(body)[0])
        self.assertAlmostEqual(left, 50, delta=0.01)
        self.assertAlmostEqual(top, 10, delta=0.01)
        self.assertAlmostEqual(right, 90, delta=0.01)
        self.assertAlmostEqual(bottom, 50, delta=0.01)

    def test_even_odd_hole_survives_the_clip(self):
        body = '<path d="M0 0H40V40H0Z M10 10H30V30H10Z" fill="#fff" fill-rule="evenodd" clip-path="url(#c1)"/>'
        shape = geometry.to_path(self.baked_paths(body)[0].get("d"), close=True)
        self.assertAlmostEqual(abs(shape.area), 1200, delta=1)

    def test_dashes_survive_the_clip(self):
        body = '<path d="M0 5H40" fill="none" stroke="#fff" stroke-width="2" stroke-dasharray="5 5" clip-path="url(#c1)"/>'
        self.assertGreater(self.baked_paths(body)[0].get("d").count("M"), 2)

    def test_group_clip_keeps_child_transforms(self):
        body = '<g clip-path="url(#c1)"><path d="M0 0H40V10H0Z" fill="#fff" transform="rotate(90 20 20)"/></g>'
        left, top, right, bottom = bounds_of(self.baked_paths(body)[0])
        self.assertAlmostEqual(left, 30, delta=0.01)
        self.assertAlmostEqual(right, 40, delta=0.01)
        self.assertAlmostEqual(top, 0, delta=0.01)
        self.assertAlmostEqual(bottom, 40, delta=0.01)

    def test_apply_transform_returns_the_moved_path(self):
        path = geometry.to_path("M0 0H10V10H0Z", close=True)
        moved = geometry.apply_transform(path, (1.0, 0.0, 0.0, 1.0, 100.0, 5.0))
        self.assertEqual(moved.bounds, (100.0, 5.0, 110.0, 15.0))
        self.assertEqual(path.bounds, (0.0, 0.0, 10.0, 10.0))


class UnsupportedInputTests(unittest.TestCase):
    def bake_color(self, body):
        return svgbake.bake_rim(colour_svg(body))

    def test_use_is_rejected(self):
        with self.assertRaises(svgbake.BakeError):
            self.bake_color('<use href="#a"/>')

    def test_text_is_rejected(self):
        with self.assertRaises(svgbake.BakeError):
            self.bake_color('<text x="1" y="1">A</text>')

    def test_style_attribute_is_rejected(self):
        with self.assertRaises(svgbake.BakeError):
            self.bake_color('<path d="M0 0H1V1Z" style="fill:red"/>')

    def test_class_attribute_is_rejected(self):
        with self.assertRaises(svgbake.BakeError):
            self.bake_color('<path d="M0 0H1V1Z" class="a"/>')

    def test_marker_attribute_is_rejected(self):
        with self.assertRaises(svgbake.BakeError):
            self.bake_color('<path d="M0 0H1V1Z" marker-end="url(#m)"/>')

    def test_rim_width_is_constant_on_screen_under_a_scaled_group(self):
        body = '<g transform="scale(0.5)"><path d="M0 0H40V40H0Z" fill="#fff"/></g><path d="M60 0H100V40H60Z" fill="#fff"/>'
        root = ET.fromstring(svgbake.bake_rim(colour_svg(body)))
        widths = sorted(float(p.get("stroke-width")) for p in root.iter(NS + "path") if p.get("stroke-width"))
        self.assertEqual(widths, [4.0, 8.0])

    def test_blurred_shadow_becomes_stacked_ellipses_without_a_filter(self):
        import math

        shadow = '<ellipse cx="64" cy="118" rx="46" ry="4.5" fill="#000" opacity=".32" filter="url(#sh)"/>'
        defs = '<filter id="sh"><feGaussianBlur stdDeviation="3"/></filter>'
        root = ET.fromstring(svgbake.bake_rim(colour_svg(shadow + '<path d="M0 0H9V9Z" fill="#fff"/>', defs)))
        self.assertEqual([e for e in root.iter() if e.get("filter")], [])
        self.assertEqual(list(root.iter(NS + "filter")), [])
        layers = [e for e in root.iter(NS + "ellipse") if e.get("fill") == "#000"]
        self.assertGreaterEqual(len(layers), 5)
        remaining = 1.0
        for layer in layers:
            remaining *= 1.0 - float(layer.get("opacity"))
        peak = 0.32 * math.erf(4.5 / (3 * math.sqrt(2)))
        self.assertAlmostEqual(1.0 - remaining, peak, delta=0.02)

    def test_malformed_transform_is_rejected(self):
        with self.assertRaises(svgbake.BakeError):
            self.bake_color('<path d="M0 0H1V1Z" fill="#fff" transform="rotate(10-5)"/>')

    def test_malformed_path_is_rejected(self):
        clip = '<clipPath id="c1"><path d="M0 0H40V40H0Z"/></clipPath>'
        body = '<path d="M0 0 Q" fill="none" stroke="#fff" clip-path="url(#c1)"/>'
        with self.assertRaises(svgbake.BakeError):
            svgbake.bake_rim(colour_svg(body, clip))

    def test_doctype_is_rejected(self):
        with self.assertRaises(svgbake.BakeError):
            svgbake.bake_symbolic(b'<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>')

    def test_broken_xml_is_rejected(self):
        with self.assertRaises(svgbake.BakeError):
            svgbake.bake_symbolic(b"<svg")

    def test_deep_nesting_is_rejected(self):
        source = b'<svg xmlns="http://www.w3.org/2000/svg">' + b"<g>" * 5000 + b"</g>" * 5000 + b"</svg>"
        with self.assertRaises(svgbake.BakeError):
            svgbake.bake_symbolic(source)

    def test_symbolic_stroke_opacity_is_rejected(self):
        with self.assertRaises(svgbake.BakeError):
            svgbake.bake_symbolic(support.SYMBOLIC_SVG.replace("<path ", '<path stroke-opacity=".5" ').encode())

    def test_transform_parser_rejects_garbage(self):
        for text in ("rotate(10-5)", "translate()", "scale(1 2 3)", "foo(1)", "translate(1) junk"):
            with self.assertRaises(geometry.GeometryError, msg=text):
                geometry.parse_transform(text)

    def test_transform_parser_accepts_lists(self):
        self.assertEqual(geometry.parse_transform("translate(1 2) translate(3,4)"), (1, 0, 0, 1, 4, 6))


class SymbolicBakeTests(unittest.TestCase):
    def bake(self, body, root_attrs=None):
        attrs = root_attrs or 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
        source = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" %s>%s</svg>' % (attrs, body)
        return ET.fromstring(svgbake.bake_symbolic(source.encode()))

    def paths(self, root):
        return list(root.iter(NS + "path"))

    def total_area(self, root):
        return sum(abs(geometry.to_path(node.get("d"), close=True).area) for node in self.paths(root))

    def test_no_stroke_attributes_remain(self):
        root = self.bake('<path d="M9 6l6 6-6 6"/><circle cx="12" cy="12" r="3"/>')
        for element in root.iter():
            for key in element.attrib:
                self.assertFalse(key.startswith("stroke"), key)
        self.assertEqual(root.get("fill"), "currentColor")

    def test_stroked_line_area_matches_width_times_length(self):
        root = self.bake('<path d="M4 12H20"/>', 'fill="none" stroke="currentColor" stroke-width="2"')
        self.assertAlmostEqual(self.total_area(root), 16 * 2, delta=0.5)

    def test_round_caps_extend_the_line(self):
        self.assertAlmostEqual(self.total_area(self.bake('<path d="M4 12H20"/>')), 16 * 2 + 3.14159, delta=0.3)

    def test_line_polyline_and_polygon_are_outlined(self):
        root = self.bake('<line x1="4" y1="12" x2="20" y2="12"/><polyline points="2 2 10 2 10 10"/><polygon points="14 14 20 14 20 20"/>')
        self.assertEqual(len(self.paths(root)), 3)
        self.assertEqual(root.findall(NS + "line"), [])

    def test_filled_element_is_kept_without_stroke(self):
        root = self.bake('<circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/>')
        circles = list(root.iter(NS + "circle"))
        self.assertEqual(len(circles), 1)
        self.assertIsNone(circles[0].get("stroke"))

    def test_fill_rule_is_preserved(self):
        root = self.bake('<path d="M0 0H10V10H0ZM2 2H8V8H2Z" fill="currentColor" fill-rule="evenodd" stroke="none"/>')
        self.assertEqual(self.paths(root)[0].get("fill-rule"), "evenodd")

    def test_opacity_is_preserved(self):
        self.assertEqual(self.paths(self.bake('<path d="M4 12H20" opacity=".35"/>'))[0].get("opacity"), ".35")

    def test_dashed_stroke_is_split(self):
        solid = self.bake('<circle cx="12" cy="12" r="8"/>')
        dashed = self.bake('<circle cx="12" cy="12" r="8" stroke-dasharray="2.4 3.25"/>')
        self.assertLess(self.total_area(dashed), self.total_area(solid))

    def test_transform_is_kept(self):
        self.assertEqual(self.paths(self.bake('<path d="M4 12H20" transform="translate(1 2)"/>'))[0].get("transform"), "translate(1 2)")

    def test_group_opacity_is_kept(self):
        root = self.bake('<g opacity=".35"><path d="M4 12H20"/></g>')
        group = root.find(NS + "g")
        self.assertEqual(group.get("opacity"), ".35")
        self.assertEqual(len(self.paths(group)), 1)

    def test_bake_is_deterministic(self):
        body = '<path d="M9 6l6 6-6 6"/>'
        self.assertEqual(ET.tostring(self.bake(body)), ET.tostring(self.bake(body)))


class CompactFolderTests(unittest.TestCase):
    BODY = "M20 40H108A10 10 0 0 1 118 50V94A10 10 0 0 1 108 104H20A10 10 0 0 1 10 94V50A10 10 0 0 1 20 40Z"

    def folder(self, body="#f5b33b", glyph="#a4730c"):
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><g>'
            '<path d="%s" fill="%s"></path><path d="%s" fill="url(#shade)"></path>'
            '<g transform="translate(46.6 57) scale(1.45)" fill="none" stroke="#ffd377" stroke-width="2" stroke-linecap="round" opacity="1"><path d="M3 3H9"></path></g>'
            '<g transform="translate(46.6 55.6) scale(1.45)" fill="none" stroke="%s" stroke-width="2" stroke-linecap="round" opacity="1"><path d="M3 3H9"></path></g>'
            "</g></svg>" % (self.BODY, body, self.BODY, glyph)
        ).encode()

    def test_the_symbol_is_enlarged_thickened_and_darkened_to_a_legible_contrast(self):
        root = ET.fromstring(svgbake.compact_folder(self.folder()))
        groups = [g for g in root.iter(NS + "g") if g.get("stroke-width")]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].get("stroke-width"), "3.2")
        self.assertEqual(groups[0].get("transform").split("scale")[1], "(2.1)")
        self.assertGreaterEqual(svgbake.contrast_ratio(groups[0].get("stroke"), "#f5b33b"), svgbake.COMPACT_CONTRAST)

    def test_the_symbol_stays_centred_where_it_was(self):
        root = ET.fromstring(svgbake.compact_folder(self.folder()))
        group = [g for g in root.iter(NS + "g") if g.get("stroke-width")][0]
        x, y = (float(v) for v in group.get("transform").split("translate(")[1].split(")")[0].split())
        self.assertAlmostEqual(x + 12 * svgbake.COMPACT_SCALE, 46.6 + 12 * 1.45, places=1)
        self.assertAlmostEqual(y + 12 * svgbake.COMPACT_SCALE, 57 + 12 * 1.45, places=1)

    def test_relief_keeps_both_copies_with_the_dark_one_lifted_and_a_moderate_contrast(self):
        root = ET.fromstring(svgbake.relief_folder(self.folder()))
        groups = [g for g in root.iter(NS + "g") if g.get("stroke-width")]
        self.assertEqual([g.get("stroke-width") for g in groups], ["2.6", "2.6"])
        self.assertEqual(groups[0].get("stroke"), "#ffd377")
        offsets = [float(g.get("transform").split("translate(")[1].split(")")[0].split()[1]) for g in groups]
        self.assertAlmostEqual(offsets[0] - offsets[1], svgbake.RELIEF_OFFSET, places=1)
        contrast = svgbake.contrast_ratio(groups[1].get("stroke"), "#f5b33b")
        self.assertGreaterEqual(contrast, svgbake.RELIEF_CONTRAST)
        self.assertLess(contrast, svgbake.COMPACT_CONTRAST)

    def test_a_folder_without_the_standard_symbol_is_not_compactable(self):
        plain = self.folder().replace(b'scale(1.45)', b'scale(2)')
        self.assertFalse(svgbake.compactable(plain))
        with self.assertRaises(svgbake.BakeError):
            svgbake.compact_folder(plain)

    def test_a_symbol_that_is_already_dark_enough_keeps_its_colour(self):
        self.assertEqual(svgbake.legible_colour("#000000", "#f5b33b"), "#000000")


if __name__ == "__main__":
    unittest.main()
