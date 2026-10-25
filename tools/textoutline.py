#!/usr/bin/env python3
# SPDX-License-Identifier: EUPL-1.2
import argparse
import hashlib
import io
import os
import sys
import xml.etree.ElementTree as ET

import geometry

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
FAMILY = "Atkinson Hyperlegible Next"
WEIGHT = 800
FONT_SOURCE = "https://github.com/googlefonts/atkinson-hyperlegible-next"
FONT_SOURCE_COMMIT = "7925f50f649b3813257faf2f4c0b381011f434f1"
FONT_FILE = "AtkinsonHyperlegibleNext[wght].ttf"
FONT_SHA256 = "5a455d1cfa099b601ab70751bb9673e8fe1854dc4500c80e1a220d0d75e31745"


class OutlineError(Exception):
    pass


def tag(name):
    return "{%s}%s" % (SVG, name)


class Face:
    def __init__(self, font_path, expected_sha256):
        import uharfbuzz
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer

        with open(font_path, "rb") as handle:
            raw = handle.read()
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise OutlineError("font digest mismatch")
        font = TTFont(io.BytesIO(raw))
        name = font["name"].getDebugName(1)
        if name != FAMILY:
            raise OutlineError("unexpected family %r" % name)
        instance = instancer.instantiateVariableFont(font, {"wght": WEIGHT})
        buffer = io.BytesIO()
        instance.save(buffer)
        self.data = buffer.getvalue()
        self.font = TTFont(io.BytesIO(self.data))
        self.units = self.font["head"].unitsPerEm
        self.glyph_set = self.font.getGlyphSet()
        self.order = self.font.getGlyphOrder()
        self.hb = uharfbuzz
        self.hb_font = uharfbuzz.Font(uharfbuzz.Face(self.data))

    def shape(self, text):
        buf = self.hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        self.hb.shape(self.hb_font, buf, {"kern": True, "liga": True})
        return buf.glyph_infos, buf.glyph_positions

    def glyph_path(self, glyph_name, scale, dx, dy):
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.pens.transformPen import TransformPen

        pen = SVGPathPen(self.glyph_set, ntos=geometry.fmt)
        self.glyph_set[glyph_name].draw(TransformPen(pen, (scale, 0, 0, -scale, dx, dy)))
        return pen.getCommands()


def outline_element(face, element):
    if element.get("font-weight") != str(WEIGHT):
        raise OutlineError("unexpected weight")
    if FAMILY not in (element.get("font-family") or ""):
        raise OutlineError("unexpected family")
    if element.get("text-anchor") != "middle":
        raise OutlineError("unsupported anchor")
    text = "".join(element.itertext())
    size = float(element.get("font-size"))
    spacing = float(element.get("letter-spacing", "0"))
    x, y = float(element.get("x")), float(element.get("y"))
    infos, positions = face.shape(text)
    if any(info.codepoint == 0 for info in infos):
        raise OutlineError("glyph missing from font for %r" % text)
    scale = size / face.units
    advances = [p.x_advance * scale + spacing for p in positions]
    cursor = x - (sum(advances) - spacing) / 2.0
    commands = []
    for info, position, advance in zip(infos, positions, advances):
        name = face.order[info.codepoint]
        commands.append(face.glyph_path(name, scale, cursor + position.x_offset * scale, y - position.y_offset * scale))
        cursor += advance
    node = ET.Element(tag("path"))
    node.set("d", "".join(commands))
    node.set("fill", element.get("fill", "#000"))
    for key in ("opacity", "fill-opacity"):
        if element.get(key) is not None:
            node.set(key, element.get(key))
    return node


def outline_svg(face, source):
    root = ET.fromstring(source)
    replaced = 0
    for parent in list(root.iter()):
        for index, child in enumerate(list(parent)):
            if child.tag == tag("text"):
                parent[index] = outline_element(face, child)
                replaced += 1
    ET.indent(root, space="")
    return ET.tostring(root, encoding="utf-8"), replaced


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replace badge text with outlines in source SVGs")
    parser.add_argument("--font", required=True, help="path to %s from %s at %s" % (FONT_FILE, FONT_SOURCE, FONT_SOURCE_COMMIT))
    parser.add_argument("--sha256", default=FONT_SHA256, help="expected digest of the font file")
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    try:
        face = Face(args.font, args.sha256)
        total = rewrite_directory(face, args.directory)
    except (OutlineError, OSError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    print("outlined %d text element(s)" % total)
    return 0


def rewrite_directory(face, directory):
    pending = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".svg"):
            continue
        path = os.path.join(directory, name)
        with open(path, "rb") as handle:
            source = handle.read()
        if b"<text" not in source:
            continue
        result, count = outline_svg(face, source)
        pending.append((path, result.rstrip(b"\n") + b"\n", count))
    for path, data, _ in pending:
        temporary = path + ".tmp"
        with open(temporary, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    return sum(count for _, _, count in pending)


if __name__ == "__main__":
    sys.exit(main())
