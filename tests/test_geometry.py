# SPDX-License-Identifier: EUPL-1.2
import codecs
import math
import unittest
import xml.etree.ElementTree as ET

import support
import geometry
import svgbake

NS = "http://www.w3.org/2000/svg"


def element(markup):
    return ET.fromstring('<svg xmlns="%s">%s</svg>' % (NS, markup))[0]


def svg(body, defs=""):
    return (
        '<svg xmlns="%s" width="128" height="128" viewBox="0 0 128 128"><defs><filter id="rim">'
        '<feMorphology in="SourceAlpha" operator="dilate" radius="2" result="d"/><feFlood flood-color="#a6622e"/>'
        '<feComposite in2="d" operator="in"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>%s</defs>'
        '<g filter="url(#rim)">%s</g></svg>' % (NS, defs, body)
    ).encode()


def area(node):
    return abs(geometry.to_path(node.get("d"), close=True).area)


def shape_area(markup):
    return abs(geometry.to_path(geometry.shape_to_d(element(markup)), close=True).area)


class ShapeTests(unittest.TestCase):
    def bounds(self, markup):
        return geometry.to_path(geometry.shape_to_d(element(markup)), close=True).bounds

    def test_line(self):
        self.assertEqual(geometry.shape_to_d(element('<line x1="1" y1="2" x2="3" y2="4"/>')), "M1 2L3 4")

    def test_polyline_is_open_and_polygon_is_closed(self):
        self.assertEqual(geometry.shape_to_d(element('<polyline points="0,0 4,0 4,4"/>')), "M0 0L4 0L4 4")
        self.assertEqual(geometry.shape_to_d(element('<polygon points="0,0 4,0 4,4"/>')), "M0 0L4 0L4 4Z")

    def test_points_must_be_pairs(self):
        for markup in ('<polygon points="0,0 4"/>', '<polygon points="0,0"/>', '<polygon points="a b c d"/>'):
            with self.assertRaises(geometry.GeometryError):
                geometry.shape_to_d(element(markup))

    def test_rect_rounding_defaults_and_clamps(self):
        self.assertEqual(self.bounds('<rect x="1" y="2" width="10" height="6" rx="2"/>'), (1, 2, 11, 8))
        self.assertEqual(self.bounds('<rect x="0" y="0" width="10" height="6" ry="2"/>'), (0, 0, 10, 6))
        self.assertEqual(self.bounds('<rect x="0" y="0" width="10" height="6" rx="50"/>'), (0, 0, 10, 6))
        self.assertAlmostEqual(shape_area('<rect width="10" height="10" rx="5"/>'), math.pi * 25, delta=0.5)
        self.assertAlmostEqual(shape_area('<rect width="20" height="10" rx="2" ry="4"/>'), 200 - (4 - math.pi) * 2 * 4, delta=0.5)

    def test_circle_and_ellipse_areas(self):
        self.assertAlmostEqual(shape_area('<circle cx="5" cy="5" r="3"/>'), math.pi * 9, delta=0.2)
        self.assertAlmostEqual(shape_area('<ellipse cx="0" cy="0" rx="4" ry="2"/>'), math.pi * 8, delta=0.2)

    def test_unsupported_shape(self):
        with self.assertRaises(geometry.GeometryError):
            geometry.shape_to_d(element("<text/>"))


class TransformTests(unittest.TestCase):
    def test_translate_and_scale_defaults(self):
        self.assertEqual(geometry.parse_transform("translate(3)"), (1, 0, 0, 1, 3, 0))
        self.assertEqual(geometry.parse_transform("translate(3 4)"), (1, 0, 0, 1, 3, 4))
        self.assertEqual(geometry.parse_transform("scale(2)"), (2, 0, 0, 2, 0, 0))
        self.assertEqual(geometry.parse_transform("scale(2 3)"), (2, 0, 0, 3, 0, 0))

    def test_skews(self):
        _, b, c, _, _, _ = geometry.parse_transform("skewX(45)")
        self.assertAlmostEqual(c, 1.0)
        self.assertEqual(b, 0)
        _, b, c, _, _, _ = geometry.parse_transform("skewY(45)")
        self.assertAlmostEqual(b, 1.0)
        self.assertEqual(c, 0)

    def test_lists_apply_left_to_right(self):
        a, b, c, d, e, f = geometry.parse_transform("translate(10 0) scale(2)")
        self.assertEqual((a, d, e, f), (2, 2, 10, 0))
        a, b, c, d, e, f = geometry.parse_transform("scale(2) translate(10 0)")
        self.assertEqual((a, d, e, f), (2, 2, 20, 0))

    def test_rotate_about_a_point(self):
        a, b, c, d, e, f = geometry.parse_transform("rotate(90 10 10)")
        self.assertAlmostEqual(a * 20 + c * 10 + e, 10)
        self.assertAlmostEqual(b * 20 + d * 10 + f, 20)

    def test_malformed_transforms(self):
        for text in ("translate()", "translate(1 2 3)", "scale(1 2 3)", "matrix(1 2 3)", "rotate(1 2)", "skewX(1 2)", "wobble(1)", "translate(1) junk"):
            with self.assertRaises(geometry.GeometryError, msg=text):
                geometry.parse_transform(text)


class StrokeTests(unittest.TestCase):
    def test_stroke_area_follows_the_exact_geometry(self):
        circle = geometry.to_path(geometry.shape_to_d(element('<circle cx="12" cy="12" r="8"/>')), close=True)
        band = geometry.stroke_band(circle, 2.0, "butt", "miter")
        self.assertAlmostEqual(abs(band.area), math.pi * (9 ** 2 - 7 ** 2), delta=0.06)

    def test_thin_stroke_area_follows_the_exact_geometry(self):
        line = geometry.to_path("M2 12H22")
        band = geometry.stroke_band(line, 1.5, "butt", "miter")
        self.assertAlmostEqual(abs(band.area), 20 * 1.5, delta=0.01)


class RejectionTests(unittest.TestCase):
    def rejected(self, body, defs=""):
        with self.assertRaises(svgbake.BakeError, msg=body):
            svgbake.bake_rim(svg(body, defs))

    def test_unsupported_elements(self):
        for markup in (
            '<a href="#x"><path d="M0 0H1V1Z"/></a>',
            '<mask id="m"><path d="M0 0H1V1Z"/></mask>',
            '<marker id="k"/>',
            '<image href="x.png"/>',
            "<script>1</script>",
            '<pattern id="p"/>',
            "<switch/>",
            '<symbol id="s"/>',
            '<set attributeName="x"/>',
            '<animate attributeName="x"/>',
            "<foreignObject/>",
        ):
            self.rejected(markup)

    def test_unsupported_attributes(self):
        for attribute in ('mask="url(#m)"', 'marker-start="url(#k)"', 'marker-mid="url(#k)"', 'marker-end="url(#k)"', 'class="a"', 'style="fill:red"'):
            self.rejected('<path d="M0 0H1V1Z" %s/>' % attribute)

    def test_doctype_and_entities(self):
        for head in (b"<!DOCTYPE svg>", b'<!ENTITY x "y">'):
            with self.assertRaises(svgbake.BakeError):
                svgbake.bake_rim(head + b'<svg xmlns="' + NS.encode() + b'"/>')

    def test_sources_in_other_encodings_are_rejected(self):
        body = '<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>'
        for data in (body.encode("utf-16"), codecs.BOM_UTF8 + body.encode("utf-8")):
            with self.assertRaises(svgbake.BakeError):
                svgbake.bake_rim(data)
            with self.assertRaises(svgbake.BakeError):
                svgbake.bake_symbolic(data)

    def test_nested_group_inside_clip_must_be_plain(self):
        clip = '<clipPath id="c1"><rect width="50" height="50"/></clipPath>'
        for attribute in ('opacity="0.5"', 'filter="url(#rim)"', 'clip-path="url(#c1)"'):
            self.rejected('<g clip-path="url(#c1)"><g %s><path d="M0 0H9V9Z" fill="#fff"/></g></g>' % attribute, clip)

    def test_clip_path_attributes_and_children(self):
        for clip in (
            '<clipPath id="c1" clipPathUnits="objectBoundingBox"><rect width="1" height="1"/></clipPath>',
            '<clipPath id="c1" transform="scale(2)"><rect width="5" height="5"/></clipPath>',
            '<clipPath id="c1"><rect width="5" height="5" transform="scale(2)"/></clipPath>',
            '<clipPath id="c1"><text/></clipPath>',
        ):
            self.rejected('<path d="M0 0H9V9Z" fill="#fff" clip-path="url(#c1)"/>', clip)

    def test_multi_child_clip_is_the_union(self):
        clip = '<clipPath id="c1"><rect x="0" y="0" width="10" height="10"/><rect x="20" y="0" width="10" height="10"/></clipPath>'
        baked = ET.fromstring(svgbake.bake_rim(svg('<path d="M0 0H40V10H0Z" fill="#fff" clip-path="url(#c1)"/>', clip)))
        paths = list(list(baked)[2].iter("{%s}path" % NS))
        self.assertAlmostEqual(sum(area(p) for p in paths), 200, delta=1)

    def test_missing_geometry_attributes_stop_the_build_with_a_bake_error(self):
        for body in (
            '<rect height="4" fill="none" stroke="#fff" stroke-width="1"/>',
            '<circle cx="4" cy="4" fill="none" stroke="#fff" stroke-width="1"/>',
            '<path d="M0 0H9V9Z" fill="#fff" stroke="#000" stroke-width="inf"/>',
            '<path d="M0 0H9V9Z" fill="#fff" stroke="#000" stroke-width="-2"/>',
            '<path d="M0 0H9V9Z" fill="#fff" transform="scale(nan)"/>',
            '<path d="M0 0H9V9Z" fill="#fff" vector-effect="non-scaling-stroke"/>',
            '<animateMotion/>',
            '<animateColor/>',
        ):
            self.rejected(body)
        self.rejected('<path d="M0 0H9V9Z" fill="#fff" clip-path="url(#c1)"/>', '<clipPath id="c1"><rect width="5"/></clipPath>')

    def test_clipped_shape_cannot_carry_a_filter(self):
        clip = '<clipPath id="c1"><rect width="50" height="50"/></clipPath>'
        self.rejected('<path d="M0 0H9V9Z" fill="#fff" filter="url(#rim)" clip-path="url(#c1)"/>', clip)

    def test_rim_filter_without_a_radius_is_rejected(self):
        broken = svg("<path d=" + chr(34) + "M0 0H9V9Z" + chr(34) + " fill=" + chr(34) + "#fff" + chr(34) + "/>").replace(b' radius="2"', b"")
        with self.assertRaises(svgbake.BakeError):
            svgbake.bake_rim(broken)

    def test_reference_to_an_absent_clip_is_rejected(self):
        self.rejected('<path d="M0 0H9V9Z" fill="#fff" clip-path="url(#absent)"/>')


if __name__ == "__main__":
    unittest.main()
