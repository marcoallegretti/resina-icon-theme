# SPDX-License-Identifier: EUPL-1.2
import math
import re

import pathops
from fontTools.svgLib.path import parse_path

CAPS = {
    "butt": pathops.LineCap.BUTT_CAP,
    "round": pathops.LineCap.ROUND_CAP,
    "square": pathops.LineCap.SQUARE_CAP,
}
JOINS = {
    "miter": pathops.LineJoin.MITER_JOIN,
    "round": pathops.LineJoin.ROUND_JOIN,
    "bevel": pathops.LineJoin.BEVEL_JOIN,
}
TRANSFORM = re.compile(r"\s*(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)\s*,?")
ARGUMENTS = {"matrix": (6,), "translate": (1, 2), "scale": (1, 2), "rotate": (1, 3), "skewX": (1,), "skewY": (1,)}
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
STROKE_SCALE = 16.0


class GeometryError(Exception):
    pass


def numbers(text):
    try:
        values = [float(v) for v in re.split(r"[\s,]+", text.strip()) if v]
    except ValueError as error:
        raise GeometryError("malformed number list %r" % text) from error
    if not all(math.isfinite(v) for v in values):
        raise GeometryError("non-finite number in %r" % text)
    return values


def points(element):
    values = numbers(element.get("points", ""))
    if len(values) < 4 or len(values) % 2:
        raise GeometryError("malformed points list")
    return list(zip(values[0::2], values[1::2]))


def shape_to_d(element):
    name = element.tag.rsplit("}", 1)[-1]
    if name == "path":
        return element.get("d")
    if name == "rect":
        x, y = float(element.get("x", 0)), float(element.get("y", 0))
        w, h = float(element.get("width")), float(element.get("height"))
        rx = element.get("rx")
        ry = element.get("ry")
        if rx is None and ry is None:
            return "M%g %gH%gV%gH%gZ" % (x, y, x + w, y + h, x)
        rx = float(rx if rx is not None else ry)
        ry = float(ry if ry is not None else rx)
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        return (
            "M%g %gH%gA%g %g 0 0 1 %g %gV%gA%g %g 0 0 1 %g %gH%gA%g %g 0 0 1 %g %gV%gA%g %g 0 0 1 %g %gZ"
            % (x + rx, y, x + w - rx, rx, ry, x + w, y + ry, y + h - ry, rx, ry, x + w - rx, y + h, x + rx,
               rx, ry, x, y + h - ry, y + ry, rx, ry, x + rx, y)
        )
    if name in ("circle", "ellipse"):
        cx, cy = float(element.get("cx", 0)), float(element.get("cy", 0))
        rx = float(element.get("r") if name == "circle" else element.get("rx"))
        ry = rx if name == "circle" else float(element.get("ry"))
        return "M%g %gA%g %g 0 1 1 %g %gA%g %g 0 1 1 %g %gZ" % (cx + rx, cy, rx, ry, cx - rx, cy, rx, ry, cx + rx, cy)
    if name == "line":
        x1, y1, x2, y2 = (float(element.get(k, 0)) for k in ("x1", "y1", "x2", "y2"))
        return "M%g %gL%g %g" % (x1, y1, x2, y2)
    if name in ("polyline", "polygon"):
        coords = points(element)
        d = "M%g %g" % coords[0] + "".join("L%g %g" % p for p in coords[1:])
        return d + ("Z" if name == "polygon" else "")
    raise GeometryError("unsupported shape " + name)


def parse_transform(text):
    result = IDENTITY
    if not text:
        return result
    consumed = 0
    for found in TRANSFORM.finditer(text):
        if found.start() != consumed:
            raise GeometryError("malformed transform %r" % text)
        consumed = found.end()
        kind, args = found.groups()
        v = numbers(args)
        if len(v) not in ARGUMENTS[kind]:
            raise GeometryError("wrong argument count in %r" % text)
        if kind == "matrix":
            m = tuple(v)
        elif kind == "translate":
            m = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif kind == "scale":
            m = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif kind == "rotate":
            c, s = math.cos(math.radians(v[0])), math.sin(math.radians(v[0]))
            m = (c, s, -s, c, 0, 0)
            if len(v) == 3:
                m = compose(compose((1, 0, 0, 1, v[1], v[2]), m), (1, 0, 0, 1, -v[1], -v[2]))
        elif kind == "skewX":
            m = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        else:
            m = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        result = compose(result, m)
    if text[consumed:].strip():
        raise GeometryError("malformed transform %r" % text)
    return result


def compose(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def to_path(d, close=False, even_odd=False):
    path = pathops.Path()
    pen = path.getPen()
    try:
        parse_path(d, pen)
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
        raise GeometryError("malformed path data %r" % d) from error
    if close:
        closed = pathops.Path()
        cpen = closed.getPen()
        for verb, args in path.segments:
            if verb == "endPath":
                cpen.closePath()
            else:
                getattr(cpen, verb)(*args)
        closed.fillType = pathops.FillType.EVEN_ODD if even_odd else closed.fillType
        return closed
    if even_odd:
        path.fillType = pathops.FillType.EVEN_ODD
    return path


def stroke_band(path, width, cap="butt", join="miter", miter_limit=4.0, dashes=None):
    if not math.isfinite(width) or width < 0:
        raise GeometryError("unusable stroke width %r" % width)
    band = path.transform(STROKE_SCALE, 0.0, 0.0, STROKE_SCALE, 0.0, 0.0)
    if dashes:
        band.stroke(width * STROKE_SCALE, CAPS[cap], JOINS[join], miter_limit, [d * STROKE_SCALE for d in dashes], 0.0)
    else:
        band.stroke(width * STROKE_SCALE, CAPS[cap], JOINS[join], miter_limit)
    band.convertConicsToQuads()
    return band.transform(1.0 / STROKE_SCALE, 0.0, 0.0, 1.0 / STROKE_SCALE, 0.0, 0.0)


def apply_transform(path, matrix):
    if matrix == IDENTITY:
        return path
    return path.transform(*matrix)


def intersect(subject, clip):
    return pathops.op(subject, clip, pathops.PathOp.INTERSECTION, fix_winding=True)


def union(first, second):
    return pathops.op(first, second, pathops.PathOp.UNION, fix_winding=True)


def fmt(value):
    text = ("%.3f" % value).rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def midpoint(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def pts(points):
    return " ".join("%s %s" % (fmt(x), fmt(y)) for x, y in points)


def path_to_d(path):
    path = pathops.Path(path)
    path.convertConicsToQuads()
    out = []
    for verb, points in path.segments:
        if verb == "moveTo":
            out.append("M" + pts(points))
        elif verb == "lineTo":
            out.append("L" + pts(points))
        elif verb == "curveTo":
            out.append("C" + pts(points))
        elif verb == "qCurveTo":
            offs, end = points[:-1], points[-1]
            if end is None:
                offs = points[:-1]
                end = midpoint(offs[-1], offs[0])
                out.append("M" + pts((end,)))
            for i, off in enumerate(offs):
                on = midpoint(off, offs[i + 1]) if i + 1 < len(offs) else end
                out.append("Q" + pts((off, on)))
        elif verb == "closePath":
            out.append("Z")
        elif verb == "endPath":
            continue
        else:
            raise GeometryError("unsupported verb " + verb)
    return "".join(out)
