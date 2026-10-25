# SPDX-License-Identifier: EUPL-1.2
import codecs
import copy
import math
import re
import xml.etree.ElementTree as ET

import geometry

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)

SHAPES = frozenset("path rect circle ellipse polygon polyline line".split())
CLIPPABLE = SHAPES
UNSUPPORTED_TAGS = frozenset(
    "a animate animateColor animateMotion animateTransform foreignObject image marker mask pattern script set style switch symbol text use".split()
)
UNSUPPORTED_ATTRIBUTES = frozenset("class mask style marker marker-start marker-mid marker-end vector-effect".split())
UNSUPPORTED_SYMBOLIC_ATTRIBUTES = frozenset("clip-path filter stroke-dashoffset stroke-opacity".split())
INHERITED = ("fill", "fill-rule", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray")
STROKE_ATTRIBUTES = frozenset(
    "stroke stroke-width stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset stroke-opacity".split()
)
COLOUR_SCHEME_ID = "current-color-scheme"
COLOUR_SCHEME_CLASS = "ColorScheme-Text"
COLOUR_SCHEME_RULE = ".ColorScheme-Text{color:#868686;}"
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
SHEET_COLOUR = "#868686"
SHEET_COLUMNS = 4
SHEET_ROWS = 3


class BakeError(Exception):
    pass


def parse(source, extra_attributes=frozenset()):
    try:
        source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BakeError("the source is not UTF-8") from error
    if source.startswith(codecs.BOM_UTF8) or 0 in source:
        raise BakeError("the source has a byte-order mark or NUL bytes")
    if b"<!DOCTYPE" in source or b"<!ENTITY" in source:
        raise BakeError("document type declarations are not accepted")
    try:
        root = ET.fromstring(source)
    except (ET.ParseError, RecursionError) as error:
        raise BakeError("malformed XML: %s" % error) from error
    for element in root.iter():
        name = local(element)
        if name in UNSUPPORTED_TAGS:
            raise BakeError("unsupported element " + name)
        for key, value in element.attrib.items():
            if key in UNSUPPORTED_ATTRIBUTES or key in extra_attributes:
                raise BakeError("unsupported attribute %s on %s" % (key, name))
            if key == "transform":
                geometry.parse_transform(value)
            if key == "stroke-width" and not 0 <= float(value) < 1e4:
                raise BakeError("unusable stroke-width %r" % value)
        if name in SHAPES:
            geometry.shape_to_d(element)
    return root


def guarded(function):
    def wrapper(source):
        try:
            return function(source)
        except (geometry.GeometryError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
            raise BakeError(str(error)) from error

    wrapper.__name__ = function.__name__
    return wrapper


def tag(name):
    return "{%s}%s" % (SVG, name)


def local(element):
    return element.tag.rsplit("}", 1)[-1]


def clip_id(element):
    ref = element.get("clip-path")
    if ref is None:
        return None
    if not (ref.startswith("url(#") and ref.endswith(")")):
        raise BakeError("unsupported clip reference " + ref)
    return ref[5:-1]


def is_rim_id(value):
    return value == "rim" or (value is not None and value.startswith("rim-"))


def rim_filters(root):
    found = {el.get("id"): el for el in root.iter(tag("filter")) if is_rim_id(el.get("id"))}
    if not found:
        raise BakeError("rim filter not found")
    return found


def rim_colour(filter_element):
    flood = filter_element.find(tag("feFlood"))
    if flood is None or not flood.get("flood-color"):
        raise BakeError("rim flood colour not found")
    return flood.get("flood-color")


def rim_radius(filter_element):
    morph = filter_element.find(tag("feMorphology"))
    if morph is None or morph.get("operator") != "dilate":
        raise BakeError("rim dilation not found")
    radius = float(morph.get("radius"))
    if not 0 <= radius < 64:
        raise BakeError("unusable rim radius %r" % morph.get("radius"))
    return radius


def effective(element, inherited):
    state = dict(inherited)
    for key in INHERITED:
        if element.get(key) is not None:
            state[key] = element.get(key)
    return state


def hoist_clip_paths(root):
    defs = root.find(tag("defs"))
    if defs is None:
        defs = ET.Element(tag("defs"))
        root.insert(0, defs)
    for parent in list(root.iter()):
        if parent is defs:
            continue
        for child in list(parent):
            if local(child) == "clipPath":
                parent.remove(child)
                defs.append(child)


def clip_shapes(root):
    clips = {}
    for el in root.iter(tag("clipPath")):
        if el.get("clipPathUnits") not in (None, "userSpaceOnUse") or el.get("transform"):
            raise BakeError("unsupported clipPath attributes")
        merged = None
        for child in el:
            if local(child) not in CLIPPABLE or child.get("transform") or child.get("clip-path"):
                raise BakeError("unsupported clipPath child")
            part = geometry.to_path(geometry.shape_to_d(child), close=True, even_odd=child.get("clip-rule") == "evenodd")
            merged = part if merged is None else geometry.union(merged, part)
        clips[el.get("id")] = merged
    return clips


def paint_attributes(element):
    attrs = {}
    for key in ("opacity",):
        if element.get(key) is not None:
            attrs[key] = element.get(key)
    return attrs


def emit(path, paint, element, opacity_key=None):
    d = geometry.path_to_d(path)
    if not d:
        return None
    node = ET.Element(tag("path"))
    node.set("d", d)
    node.set("fill", paint)
    for key, value in paint_attributes(element).items():
        node.set(key, value)
    if opacity_key and element.get(opacity_key) is not None:
        node.set("fill-opacity", element.get(opacity_key))
    return node


def bake_leaf(element, state, matrix, clip, out, bands, inner_edge=False):
    name = local(element)
    if name not in CLIPPABLE:
        raise BakeError("cannot clip " + name)
    if element.get("filter") is not None:
        raise BakeError("a clipped shape cannot carry a filter")
    d = geometry.shape_to_d(element)
    own = geometry.parse_transform(element.get("transform"))
    full = geometry.compose(matrix, own)
    if inner_edge:
        clip = geometry.apply_transform(clip, own)
    fill = state.get("fill", "#000")
    stroke = state.get("stroke", "none")
    if fill != "none":
        shape = geometry.apply_transform(geometry.to_path(d, close=True, even_odd=state.get("fill-rule") == "evenodd"), full)
        node = emit(geometry.intersect(shape, clip), fill, element, "fill-opacity")
        if node is not None:
            out.append(node)
    if stroke != "none":
        band = geometry.stroke_band(
            geometry.to_path(d),
            float(state.get("stroke-width", "1")),
            state.get("stroke-linecap", "butt"),
            state.get("stroke-linejoin", "miter"),
            float(state.get("stroke-miterlimit", "4")),
            stroke_dashes(state),
        )
        band = geometry.apply_transform(band, full)
        node = emit(geometry.intersect(band, clip), stroke, element, "stroke-opacity")
        if node is not None:
            out.append(node)
            if inner_edge and fill == "none":
                bands.add(id(node))


def bake_group_clip(group, state, clip, matrix, out, bands):
    for child in group:
        name = local(child)
        if name == "g":
            if child.get("opacity") or child.get("filter") or child.get("clip-path"):
                raise BakeError("unsupported nested group inside clip")
            bake_group_clip(
                child,
                effective(child, state),
                clip,
                geometry.compose(matrix, geometry.parse_transform(child.get("transform"))),
                out,
                bands,
            )
        elif name in SHAPES:
            bake_leaf(child, effective(child, state), matrix, clip, out, bands)


def bake_clips(root, clips):
    bands = set()

    def walk(parent, inherited):
        state = effective(parent, inherited)
        for index, child in enumerate(list(parent)):
            name = local(child)
            if name == "defs":
                continue
            cid = clip_id(child)
            if cid is None:
                if name == "g":
                    walk(child, state)
                continue
            if cid not in clips:
                raise BakeError("unknown clip " + cid)
            out = []
            if name == "g":
                holder = ET.Element(tag("g"))
                for key, value in child.attrib.items():
                    if key not in ("clip-path", "transform"):
                        holder.set(key, value)
                bake_group_clip(child, effective(child, state), clips[cid], IDENTITY, out, bands)
                if child.get("transform"):
                    raise BakeError("unsupported transform on clipped group")
                for node in out:
                    holder.append(node)
                parent[index] = holder
            else:
                bake_leaf(child, effective(child, state), IDENTITY, clips[cid], out, bands, inner_edge=True)
                holder = ET.Element(tag("g"))
                for node in out:
                    holder.append(node)
                parent[index] = holder

    walk(root, {})
    return bands


def is_shadow(element):
    return element.get("filter") is not None and local(element) == "ellipse"


def dilate(element, state, colour, radius):
    fill = state.get("fill", "#000")
    stroke = state.get("stroke", "none")
    width = float(state.get("stroke-width", "1"))
    clone = ET.Element(element.tag)
    for key, value in element.attrib.items():
        if key in ("fill", "stroke", "stroke-width", "filter", "style", "class", "id"):
            continue
        clone.set(key, value)
    clone.set("fill", "none" if fill == "none" else colour)
    clone.set("stroke", colour)
    base = width if stroke != "none" else 0.0
    clone.set("stroke-width", format(base + 2 * radius, "g"))
    clone.set("stroke-linejoin", "round")
    if fill == "none" and base < 1.0:
        coverage = base * float(element.get("opacity", "1"))
        if coverage < 0.02:
            return None
        clone.set("opacity", format(coverage, "g"))
    clone.text = element.text
    for child in element:
        clone.append(copy.deepcopy(child))
    return clone


def shadow_halo(shadow, colour, radius):
    halo = ET.Element(shadow.tag)
    for key, value in shadow.attrib.items():
        if key not in ("fill", "rx", "ry"):
            halo.set(key, value)
    halo.set("rx", format(float(shadow.get("rx")) + radius, "g"))
    halo.set("ry", format(float(shadow.get("ry")) + radius, "g"))
    halo.set("fill", colour)
    return halo


def transform_scale(element):
    a, b, c, d, _, _ = geometry.parse_transform(element.get("transform"))
    return abs(a * d - b * c) ** 0.5 or 1.0


def silhouette(node, inherited, colour, radius, skip, scale=1.0):
    out = ET.Element(node.tag)
    for key, value in node.attrib.items():
        if key in ("filter", "id"):
            continue
        out.set(key, value)
    state = effective(node, inherited)
    for child in node:
        name = local(child)
        if name == "g":
            sub = silhouette(child, state, colour, radius, skip, scale * transform_scale(child))
            if len(sub):
                out.append(sub)
            continue
        if is_shadow(child):
            out.append(shadow_halo(child, colour, radius / (scale * transform_scale(child))))
            continue
        if name not in SHAPES or id(child) in skip:
            continue
        grown = dilate(child, effective(child, state), colour, radius / (scale * transform_scale(child)))
        if grown is not None:
            out.append(grown)
    return out


def stroke_dashes(state):
    text = state.get("stroke-dasharray", "none")
    if text == "none":
        return None
    values = [float(v) for v in text.replace(",", " ").split()]
    return values if len(values) % 2 == 0 else values * 2


def outline_stroke(child, state):
    band = geometry.stroke_band(
        geometry.to_path(geometry.shape_to_d(child)),
        float(state.get("stroke-width", "1")),
        state.get("stroke-linecap", "butt"),
        state.get("stroke-linejoin", "miter"),
        float(state.get("stroke-miterlimit", "4")),
        stroke_dashes(state),
    )
    node = ET.Element(tag("path"))
    node.set("d", geometry.path_to_d(band))
    node.set("fill", "currentColor")
    for key in ("opacity", "transform"):
        if child.get(key) is not None:
            node.set(key, child.get(key))
    return node


def outline_children(parent, inherited):
    rebuilt = []
    for child in list(parent):
        name = local(child)
        state = effective(child, inherited)
        if name == "g":
            for key in STROKE_ATTRIBUTES:
                child.attrib.pop(key, None)
            outline_children(child, state)
            rebuilt.append(child)
            continue
        if name not in CLIPPABLE:
            rebuilt.append(child)
            continue
        if state.get("fill", "#000") != "none":
            filled = ET.Element(child.tag)
            for key, value in child.attrib.items():
                if key not in STROKE_ATTRIBUTES:
                    filled.set(key, value)
            filled.set("fill", "currentColor")
            rebuilt.append(filled)
        if state.get("stroke", "none") != "none":
            rebuilt.append(outline_stroke(child, state))
    parent[:] = rebuilt


@guarded
def mirror_symbolic(source):
    root = parse(source, UNSUPPORTED_SYMBOLIC_ATTRIBUTES)
    width = float(root.get("viewBox").replace(",", " ").split()[2])
    wrapper = ET.Element(tag("g"))
    wrapper.set("transform", "matrix(-1 0 0 1 %s 0)" % format(width, "g"))
    wrapper.extend(list(root))
    root[:] = [wrapper]
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


@guarded
def bake_symbolic(source):
    root = parse(source, UNSUPPORTED_SYMBOLIC_ATTRIBUTES)
    state = effective(root, {})
    for key in STROKE_ATTRIBUTES | {"fill"}:
        root.attrib.pop(key, None)
    root.set("fill", "currentColor")
    outline_children(root, state)
    for element in root.iter():
        if local(element) in SHAPES:
            element.set("class", COLOUR_SCHEME_CLASS)
    defs = ET.Element(tag("defs"))
    style = ET.SubElement(defs, tag("style"))
    style.set("type", "text/css")
    style.set("id", COLOUR_SCHEME_ID)
    style.text = COLOUR_SCHEME_RULE
    root.insert(0, defs)
    ET.indent(root, space="")
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


def animation_sheet(source, size):
    try:
        root = parse(source, UNSUPPORTED_SYMBOLIC_ATTRIBUTES)
        shapes = [child for child in root if local(child) in SHAPES]
        if not shapes or not any(child.get("opacity") is None for child in shapes):
            raise BakeError("the source has no moving shape")
        frames = SHEET_COLUMNS * SHEET_ROWS
        width, height = SHEET_COLUMNS * size, SHEET_ROWS * size
        sheet = ET.Element(tag("svg"))
        for key, value in (
            ("width", str(width)),
            ("height", str(height)),
            ("viewBox", "0 0 %d %d" % (width, height)),
            ("fill", "none"),
            ("stroke", SHEET_COLOUR),
            ("stroke-width", "2"),
            ("stroke-linecap", "round"),
            ("stroke-linejoin", "round"),
        ):
            sheet.set(key, value)
        for index in range(frames):
            frame = ET.SubElement(sheet, tag("g"))
            frame.set(
                "transform",
                "translate(%d %d) scale(%s)" % (index % SHEET_COLUMNS * size, index // SHEET_COLUMNS * size, format(size / 24, ".6g")),
            )
            for shape in shapes:
                copied = copy.deepcopy(shape)
                if copied.get("opacity") is None:
                    copied.set("transform", "rotate(%s 12 12)" % format(360 * index / frames, ".6g"))
                frame.append(copied)
        ET.indent(sheet, space="")
        return ET.tostring(sheet, encoding="utf-8", xml_declaration=False)
    except (geometry.GeometryError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        raise BakeError(str(error)) from error


COMPACT_SCALE = 2.1
COMPACT_STROKE = 3.2
COMPACT_CONTRAST = 4.5
RELIEF_SCALE = 1.8
RELIEF_STROKE = 2.6
RELIEF_CONTRAST = 3.5
RELIEF_OFFSET = 1.4
GLYPH_GROUP = re.compile(
    r'<g transform="translate\(([-0-9.]+) ([-0-9.]+)\) scale\(1\.45\)" fill="none" stroke="(#[0-9a-f]{6})" stroke-width="2"([^>]*)>(.*?)</g>', re.S
)
BODY_FILL = re.compile(r'<path d="(?P<outline>[^"]+)" fill="(?P<fill>#[0-9a-f]{6})"></path><path d="(?P=outline)" fill="url[(]#shade[)]"></path>')


def relative_luminance(colour):
    linear = []
    for index in (1, 3, 5):
        channel = int(colour[index:index + 2], 16) / 255
        linear.append(channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first, second):
    high, low = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def legible_colour(colour, body, contrast=COMPACT_CONTRAST):
    for step in range(50):
        factor = 1.0 - step * 0.02
        shade = "#" + "".join("%02x" % round(int(colour[i:i + 2], 16) * factor) for i in (1, 3, 5))
        if contrast_ratio(shade, body) >= contrast:
            return shade
    return "#000000"


def compactable(source):
    text = source.decode("utf-8")
    return len(GLYPH_GROUP.findall(text)) == 2 and BODY_FILL.search(text) is not None


def restyle_folder(source, scale, stroke, contrast, relief):
    text = source.decode("utf-8")
    glyphs = GLYPH_GROUP.findall(text)
    body = BODY_FILL.search(text)
    if len(glyphs) != 2 or body is None:
        raise BakeError("folder symbol not found")
    centre_x = float(glyphs[0][0]) + 12 * 1.45
    centre_y = float(glyphs[0][1]) + 12 * 1.45
    colour = legible_colour(glyphs[1][2], body.group("fill"), contrast)
    seen = []

    def replace(match):
        seen.append(match)
        lifted = len(seen) == 2
        if len(seen) == 1 and not relief:
            return ""
        return '<g transform="translate(%s %s) scale(%s)" fill="none" stroke="%s" stroke-width="%s"%s>%s</g>' % (
            format(centre_x - 12 * scale, ".4g"),
            format(centre_y - 12 * scale - (RELIEF_OFFSET if lifted and relief else 0), ".4g"),
            scale,
            colour if lifted else match.group(3),
            stroke,
            match.group(4),
            match.group(5),
        )

    return GLYPH_GROUP.sub(replace, text).encode("utf-8")


@guarded
def compact_folder(source):
    return restyle_folder(source, COMPACT_SCALE, COMPACT_STROKE, COMPACT_CONTRAST, False)


@guarded
def relief_folder(source):
    return restyle_folder(source, RELIEF_SCALE, RELIEF_STROKE, RELIEF_CONTRAST, True)


SHADOW_LAYERS = 12


def blur_deviation(root, ref):
    if not ref or not ref.startswith("url(#") or not ref.endswith(")"):
        return None
    for flt in root.iter(tag("filter")):
        if flt.get("id") == ref[5:-1]:
            blurs = [c for c in flt if local(c) == "feGaussianBlur"]
            if len(flt) == 1 and len(blurs) == 1 and blurs[0].get("stdDeviation"):
                sigma = float(blurs[0].get("stdDeviation").split()[0])
                if not 0 < sigma < 32:
                    raise BakeError("unusable blur deviation")
                return sigma
    return None


def soft_layers(rx, ry, sigma, opacity):
    reach = sigma * math.sqrt(2.0)

    def profile(y):
        return 0.5 * (math.erf((y + ry) / reach) - math.erf((y - ry) / reach))

    top = ry + 2 * sigma
    heights = [top - i * (top - 0.8) / (SHADOW_LAYERS - 1) for i in range(SHADOW_LAYERS)]
    layers, covered = [], 0.0
    for i, height in enumerate(heights):
        inner = heights[i + 1] if i + 1 < len(heights) else 0.0
        target = min(opacity * profile((height + inner) / 2), 0.999)
        alpha = 1.0 - (1.0 - target) / (1.0 - covered) if target > covered else 0.0
        covered = max(covered, target)
        if alpha > 0.0005 and rx + height - ry > 0:
            layers.append((rx + height - ry, height, alpha))
    return layers


def soften_shadows(root):
    unused = set()
    for parent in list(root.iter()):
        for index, child in enumerate(list(parent)):
            if local(child) != "ellipse":
                continue
            sigma = blur_deviation(root, child.get("filter"))
            if sigma is None:
                continue
            unused.add(child.get("filter")[5:-1])
            rx, ry = float(child.get("rx")), float(child.get("ry"))
            opacity = float(child.get("opacity", "1"))
            position = list(parent).index(child)
            parent.remove(child)
            for offset, (layer_rx, layer_ry, alpha) in enumerate(soft_layers(rx, ry, sigma, opacity)):
                layer = ET.Element(child.tag)
                for key, value in child.attrib.items():
                    if key not in ("filter", "rx", "ry", "opacity"):
                        layer.set(key, value)
                layer.set("rx", format(layer_rx, ".3f").rstrip("0").rstrip("."))
                layer.set("ry", format(layer_ry, ".3f").rstrip("0").rstrip("."))
                layer.set("opacity", format(alpha, ".4f").rstrip("0").rstrip("."))
                parent.insert(position + offset, layer)
    for flt in list(root.iter(tag("filter"))):
        if flt.get("id") in unused and not any(el.get("filter") == "url(#%s)" % flt.get("id") for el in root.iter()):
            for holder in root.iter():
                if flt in list(holder):
                    holder.remove(flt)


@guarded
def bake_rim(source):
    root = parse(source)
    hoist_clip_paths(root)
    filters = rim_filters(root)
    clips = clip_shapes(root)
    bands = bake_clips(root, clips)
    targets = [el for el in root if el.get("filter", "")[5:-1] in filters and el.get("filter", "").startswith("url(#")]
    if not targets:
        raise BakeError("expected at least one rim group")
    for number, group in enumerate(targets):
        flt = filters[group.get("filter")[5:-1]]
        rim_group = silhouette(group, {}, rim_colour(flt), rim_radius(flt), bands)
        rim_group.set("id", "rim" if number == 0 else "rim-%d" % (number + 1))
        root.insert(list(root).index(group), rim_group)
        del group.attrib["filter"]
    soften_shadows(root)
    for defs in root.findall(tag("defs")):
        for el in list(defs):
            if is_rim_id(el.get("id")) or local(el) == "clipPath":
                defs.remove(el)
    ET.indent(root, space="")
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)
