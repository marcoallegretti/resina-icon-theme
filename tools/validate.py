#!/usr/bin/env python3
# SPDX-License-Identifier: EUPL-1.2
import argparse
import codecs
import hashlib
import os
import re
import stat
import sys
import xml.etree.ElementTree as ET

SVG = "{http://www.w3.org/2000/svg}"
CONTEXTS = frozenset("Actions Animations Applications Categories Devices Emblems Emotes FileSystems International MimeTypes Places Status".split())
GROUP_CONTEXTS = {
    "scalable/apps": "Applications",
    "scalable/categories": "Categories",
    "scalable/devices": "Devices",
    "scalable/mimetypes": "MimeTypes",
    "scalable/places": "Places",
    "scalable/places-small": "Places",
    "scalable/places-medium": "Places",
    "scalable/status": "Status",
    "symbolic/actions": "Actions",
    "symbolic/animations": "Animations",
    "symbolic/apps": "Applications",
    "symbolic/categories": "Categories",
    "symbolic/devices": "Devices",
    "symbolic/emblems": "Emblems",
    "symbolic/intl": "International",
    "symbolic/mimetypes": "MimeTypes",
    "symbolic/places": "Places",
    "symbolic/status": "Status",
}
GROUP_SIZES = {"scalable": (128, 16, 512), "symbolic": (16, 8, 512)}
FOLDER_RANGES = {"scalable/places-small": (22, 16, 24), "scalable/places-medium": (48, 25, 64)}
LARGE_FOLDER_MIN = 65
ANIMATION_SIZES = (16, 22, 24, 32)
SHEET_COLOUR = "#868686"
SHEET_COLUMNS = 4
SHEET_ROWS = 3
FORBIDDEN = frozenset(
    "script foreignObject image text style animate animateColor animateMotion set animateTransform switch metadata title desc use a mask pattern".split()
)
FORBIDDEN_PRIMITIVES = frozenset(["feMorphology"])
SHAPES = frozenset("path rect circle ellipse polygon polyline line".split())
EXPECTED_VIEWBOX = {"scalable": "0 0 128 128", "symbolic": "0 0 24 24"}
COLOUR_SCHEME_ID = "current-color-scheme"
COLOUR_SCHEME_CLASS = "ColorScheme-Text"
COLOUR_SCHEME_RULE = ".ColorScheme-Text{color:#868686;}"
ALLOWED_DATA_ATTRIBUTES = frozenset(["data-dynamic", "data-box", "data-pivot"])
FORBIDDEN_ATTRIBUTES = frozenset(["style", "class", "mask"])
ROOT_FILES = frozenset(
    ["index.theme", "icon-theme.cache", "NOTICE", "EUPL-1.2.txt", "OFL-1.1.txt", "NOTICE.thirdparty", "EUPL-1.2.thirdparty.txt", "OFL-1.1.thirdparty.txt"]
)
REQUIRED_KEYS = ("Name", "Comment", "Directories", "Inherits")
SECTION = re.compile(r"^\[(.+)\]$")
REFERENCE = re.compile(r"url\(#([^)]+)\)")
MAX_SVG_BYTES = 1 << 20


class Finding:
    def __init__(self, code, path, detail=""):
        self.code = code
        self.path = path
        self.detail = detail

    def __str__(self):
        return "%s %s %s" % (self.code, self.path, self.detail)

    def __eq__(self, other):
        return isinstance(other, Finding) and (self.code, self.path) == (other.code, other.path)

    def __hash__(self):
        return hash((self.code, self.path))


def parse_index(path):
    groups = {}
    current = None
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            match = SECTION.match(line)
            if match:
                if match.group(1) in groups:
                    raise ValueError("duplicate section %r" % match.group(1))
                current = groups.setdefault(match.group(1), {})
                continue
            if current is None or "=" not in line:
                raise ValueError("malformed line: %r" % line)
            key, _, value = line.partition("=")
            if key in current:
                raise ValueError("duplicate key %r" % key)
            current[key] = value
    return groups


def check_header(header, findings):
    for key in REQUIRED_KEYS:
        if key not in header:
            findings.append(Finding("index-key", "index.theme", key))
    if header.get("Name") != "Resina":
        findings.append(Finding("index-name", "index.theme", header.get("Name", "")))
    if header.get("Inherits") != "hicolor":
        findings.append(Finding("index-inherits", "index.theme", header.get("Inherits", "")))
    if header.get("Example") != "folder":
        findings.append(Finding("index-example", "index.theme", header.get("Example", "")))


def check_section(root, directory, section, findings, listed=()):
    for key in ("Size", "Context", "Type"):
        if key not in section:
            findings.append(Finding("index-key", directory, key))
    context = section.get("Context")
    if context not in CONTEXTS:
        findings.append(Finding("index-context", directory, context or ""))
    elif directory in GROUP_CONTEXTS and GROUP_CONTEXTS[directory] != context:
        findings.append(Finding("index-context-mismatch", directory, context))
    if directory.startswith("animations/"):
        try:
            size = int(directory.partition("/")[2])
        except ValueError:
            size = 0
        if size not in ANIMATION_SIZES or section.get("Size") != str(size) or section.get("Type") != "Fixed" or context != "Animations":
            findings.append(Finding("index-animation", directory))
        if not os.path.isdir(os.path.join(root, directory)):
            findings.append(Finding("index-directory-missing", directory))
        return
    if section.get("Type") != "Scalable":
        findings.append(Finding("index-type", directory, section.get("Type", "")))
    try:
        size, low, high = (int(section[k]) for k in ("Size", "MinSize", "MaxSize"))
    except (KeyError, ValueError):
        findings.append(Finding("index-range", directory))
    else:
        expected = GROUP_SIZES.get(directory.partition("/")[0])
        if directory in FOLDER_RANGES:
            expected = FOLDER_RANGES[directory]
        elif directory == "scalable/places" and any(name in listed for name in FOLDER_RANGES):
            expected = (expected[0], LARGE_FOLDER_MIN, expected[2])
        if not (low <= size <= high) or (expected and (size, low, high) != expected):
            findings.append(Finding("index-range", directory))
    if not os.path.isdir(os.path.join(root, directory)):
        findings.append(Finding("index-directory-missing", directory))


def check_index(root, findings):
    path = os.path.join(root, "index.theme")
    if not os.path.isfile(path):
        findings.append(Finding("index-missing", "index.theme"))
        return None
    try:
        groups = parse_index(path)
    except (ValueError, UnicodeDecodeError) as error:
        findings.append(Finding("index-malformed", "index.theme", str(error)))
        return None
    header = groups.get("Icon Theme")
    if header is None:
        findings.append(Finding("index-header", "index.theme"))
        return None
    check_header(header, findings)
    listed = [d for d in header.get("Directories", "").split(",") if d]
    if len(set(listed)) != len(listed):
        findings.append(Finding("index-duplicate-directory", "index.theme"))
    for directory in listed:
        if directory not in groups:
            findings.append(Finding("index-section-missing", directory))
        else:
            check_section(root, directory, groups[directory], findings, listed)
    for name in groups:
        if name != "Icon Theme" and name not in listed:
            findings.append(Finding("index-section-unlisted", name))
    return listed


def is_colour_scheme_style(element):
    return (
        element.attrib == {"type": "text/css", "id": COLOUR_SCHEME_ID}
        and (element.text or "").strip() == COLOUR_SCHEME_RULE
        and len(element) == 0
    )


def check_attributes(element, name, rel, group, findings):
    for key, value in element.attrib.items():
        if key.startswith("{"):
            findings.append(Finding("svg-namespaced-attribute", rel, key))
        elif key == "class" and group == "symbolic" and value == COLOUR_SCHEME_CLASS and name in SHAPES:
            pass
        elif key in FORBIDDEN_ATTRIBUTES:
            findings.append(Finding("svg-forbidden-attribute", rel, key))
        elif key.startswith("on"):
            findings.append(Finding("svg-event-attribute", rel, key))
        elif key.startswith("data-") and key not in ALLOWED_DATA_ATTRIBUTES:
            findings.append(Finding("svg-data-attribute", rel, key))
        if chr(92) in value:
            findings.append(Finding("svg-escape", rel, key))
        if key == "href" and not value.startswith("#"):
            findings.append(Finding("svg-external-reference", rel, value))
        if "url(" in value.lower() and not re.fullmatch(r"url\(#[^)]+\)", value.strip()):
            findings.append(Finding("svg-external-reference", rel, value))
        if group == "symbolic" and key in ("color", "stop-color", "flood-color", "lighting-color") and value != "currentColor":
            findings.append(Finding("svg-fixed-colour", rel, value))
        if group == "animations" and key in ("stroke", "fill", "color", "stop-color", "flood-color", "lighting-color"):
            if value not in (SHEET_COLOUR, "none"):
                findings.append(Finding("svg-fixed-colour", rel, value))
        if group == "symbolic" and key in ("stroke", "fill"):
            if value not in ("currentColor", "none") or (key == "stroke" and value != "none"):
                findings.append(Finding("svg-stroke-in-symbolic" if key == "stroke" else "svg-fixed-colour", rel, value))


def svg_findings(path, rel, group, findings):
    if os.path.getsize(path) > MAX_SVG_BYTES:
        findings.append(Finding("svg-too-large", rel))
        return
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        findings.append(Finding("svg-encoding", rel))
        return
    if raw.startswith(codecs.BOM_UTF8) or 0 in raw:
        findings.append(Finding("svg-encoding", rel))
        return
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw or b"<!--" in raw or b"<?" in raw:
        findings.append(Finding("svg-doctype", rel))
        return
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, RecursionError) as error:
        findings.append(Finding("svg-parse", rel, str(error)))
        return
    if root.tag != SVG + "svg":
        findings.append(Finding("svg-root", rel))
        return
    expected = EXPECTED_VIEWBOX.get(group)
    if group == "animations":
        size = int(rel.split("/")[1])
        width, height = SHEET_COLUMNS * size, SHEET_ROWS * size
        expected = "0 0 %d %d" % (width, height)
        if root.get("width") != str(width) or root.get("height") != str(height):
            findings.append(Finding("svg-sheet-size", rel))
    if expected and root.get("viewBox") != expected:
        findings.append(Finding("svg-viewbox", rel, str(root.get("viewBox"))))
    defs_children = set()
    for defs in root.iter(SVG + "defs"):
        defs_children.update(id(c) for c in defs)
    ids = {e.get("id") for e in root.iter() if e.get("id")}
    shapes = 0
    for element in root.iter():
        if not element.tag.startswith(SVG):
            findings.append(Finding("svg-foreign-element", rel, element.tag))
            continue
        name = element.tag[len(SVG):]
        if name == "style" and group == "symbolic" and is_colour_scheme_style(element):
            pass
        elif name in FORBIDDEN:
            findings.append(Finding("svg-forbidden-element", rel, name))
        if name in FORBIDDEN_PRIMITIVES:
            findings.append(Finding("svg-forbidden-primitive", rel, name))
        if name == "clipPath" and id(element) not in defs_children:
            findings.append(Finding("svg-clippath-outside-defs", rel))
        if name == "clipPath" or element.get("clip-path"):
            findings.append(Finding("svg-clip", rel))
        if name in SHAPES:
            shapes += 1
        check_attributes(element, name, rel, group, findings)
        for value in element.attrib.values():
            for target in REFERENCE.findall(value):
                if target not in ids:
                    findings.append(Finding("svg-dangling-reference", rel, target))
    if shapes == 0:
        findings.append(Finding("svg-empty", rel))


def check_link(full, rel, dirpath, findings):
    target = os.readlink(full)
    if os.path.isabs(target) or "/" in target or target in (".", ".."):
        findings.append(Finding("link-unsafe", rel, target))
        return
    resolved = os.path.join(dirpath, target)
    info = os.lstat(resolved) if os.path.lexists(resolved) else None
    if info is None:
        findings.append(Finding("link-dangling", rel, target))
    elif stat.S_ISLNK(info.st_mode):
        findings.append(Finding("link-chain", rel, target))
    elif not stat.S_ISREG(info.st_mode) or not target.endswith(".svg"):
        findings.append(Finding("link-target-kind", rel, target))


def check_tree(root, findings):
    for dirpath, dirs, files in os.walk(root):
        dirs.sort()
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        group = rel_dir.split("/")[0] if rel_dir != "." else ""
        lowered = {}
        for name in sorted(files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]):
            rel = name if rel_dir == "." else "%s/%s" % (rel_dir, name)
            full = os.path.join(dirpath, name)
            if rel_dir == ".":
                if os.path.islink(full) or not os.path.isfile(full):
                    findings.append(Finding("root-not-regular", rel))
                elif name not in ROOT_FILES and not name.startswith("MANIFEST."):
                    findings.append(Finding("unexpected-file", rel))
                continue
            folded = name.lower()
            if folded in lowered and lowered[folded] != name:
                findings.append(Finding("case-collision", rel, lowered[folded]))
            lowered[folded] = name
            if (group not in GROUP_SIZES and group != "animations") or not name.endswith(".svg") or rel_dir.count("/") != 1:
                findings.append(Finding("unexpected-file", rel))
                continue
            if os.path.islink(full):
                check_link(full, rel, dirpath, findings)
                continue
            if not os.path.isfile(full):
                findings.append(Finding("not-regular", rel))
                continue
            svg_findings(full, rel, group, findings)


def read_manifest(path, name):
    import install

    try:
        with open(path, encoding="utf-8") as handle:
            return install.parse_manifest(handle.read(), name)
    except (install.InstallError, UnicodeDecodeError) as error:
        return str(error)


def check_manifests(root, findings):
    import install

    listed = set()
    owners = {}
    manifests = sorted(f for f in os.listdir(root) if f.startswith("MANIFEST."))
    if not manifests:
        findings.append(Finding("manifest-missing", "MANIFEST"))
    for manifest in manifests:
        path = os.path.join(root, manifest)
        if os.path.islink(path) or not os.path.isfile(path):
            findings.append(Finding("manifest-not-regular", manifest))
            continue
        if not install.COMPONENT.fullmatch(manifest[len("MANIFEST."):]):
            findings.append(Finding("manifest-component", manifest))
            continue
        entries = read_manifest(path, manifest)
        if isinstance(entries, str):
            findings.append(Finding("manifest-malformed", manifest, entries))
            continue
        for rel, (kind, value, size) in entries.items():
            if rel in owners:
                findings.append(Finding("manifest-duplicate", rel, "%s and %s" % (owners[rel], manifest)))
                continue
            owners[rel] = manifest
            listed.add(rel)
            full = os.path.join(root, rel)
            if kind == "F":
                if not os.path.isfile(full) or os.path.islink(full):
                    findings.append(Finding("manifest-missing-file", rel))
                    continue
                with open(full, "rb") as data:
                    content = data.read()
                if hashlib.sha256(content).hexdigest() != value or len(content) != size:
                    findings.append(Finding("manifest-mismatch", rel))
            elif not os.path.islink(full) or os.readlink(full) != value:
                findings.append(Finding("manifest-link-mismatch", rel))
    present = set()
    for dirpath, dirs, files in os.walk(root):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]:
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            if not rel.startswith("MANIFEST.") and rel != "icon-theme.cache":
                present.add(rel)
    for rel in sorted(present - listed):
        findings.append(Finding("manifest-unlisted", rel))


def check_directories_used(root, listed, findings):
    if listed is None:
        return
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        if os.path.isdir(full) and not os.path.islink(full):
            for sub in sorted(os.listdir(full)):
                rel = "%s/%s" % (entry, sub)
                if os.path.isdir(os.path.join(full, sub)) and rel not in listed:
                    findings.append(Finding("directory-unlisted", rel))


def check_against_sources(root, repo, findings):
    import themebuild

    plan = themebuild.Plan(repo)
    plan.collect()
    present = sorted(f[len("MANIFEST."):] for f in os.listdir(root) if f.startswith("MANIFEST."))
    selected = set(present) & set(themebuild.COMPONENTS)
    expected_files = {f[0] for f in plan.files if plan.component[f[0]] in selected}
    expected_links = {l[0]: l[1] for l in plan.links if plan.component[l[0]] in selected}
    found_files, found_links = set(), {}
    for dirpath, dirs, files in os.walk(root):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel.count("/") == 0:
                continue
            if os.path.islink(full):
                found_links[rel] = os.readlink(full)
            else:
                found_files.add(rel)
    for rel in sorted(expected_files - found_files):
        findings.append(Finding("source-missing-file", rel))
    for rel in sorted(found_files - expected_files):
        findings.append(Finding("source-unexpected-file", rel))
    for rel in sorted(set(expected_links) - set(found_links)):
        findings.append(Finding("source-missing-link", rel))
    for rel in sorted(set(found_links) - set(expected_links)):
        findings.append(Finding("source-unexpected-link", rel))
    for rel in sorted(set(found_links) & set(expected_links)):
        if found_links[rel] != expected_links[rel]:
            findings.append(Finding("source-link-target", rel, found_links[rel]))
    if "core" in selected:
        every = themebuild.theme_directories(
            [f[0] for f in plan.files if plan.component[f[0]] in selected] + [l[0] for l in plan.links if plan.component[l[0]] in selected]
        )
        path = os.path.join(root, "index.theme")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                if handle.read() != themebuild.index_theme(every):
                    findings.append(Finding("index-differs", "index.theme"))


def validate(root, manifests=True, repo=None, index=True):
    findings = []
    listed = check_index(root, findings) if index else None
    check_tree(root, findings)
    check_directories_used(root, listed, findings)
    if manifests:
        check_manifests(root, findings)
    if repo is not None:
        check_against_sources(root, repo, findings)
        cross = overlay_links(root, repo)
        findings = [f for f in findings if not (f.code == "link-dangling" and f.path in cross)]
    return findings


def overlay_links(root, repo):
    import themebuild

    plan = themebuild.Plan(repo)
    plan.collect()
    selected = {f[len("MANIFEST."):] for f in os.listdir(root) if f.startswith("MANIFEST.")}
    cross = set()
    for rel, base in plan.links:
        target = rel.rpartition("/")[0] + "/" + base
        if plan.component[rel] in selected and plan.component.get(target) not in selected:
            cross.add(rel)
    return cross


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a built Resina theme tree")
    parser.add_argument("root")
    parser.add_argument("--no-manifest", action="store_true", help="skip manifest checks")
    parser.add_argument("--no-index", action="store_true", help="skip index.theme checks, for overlay trees")
    parser.add_argument("--repo", help="repository root; compare the tree with the source data")
    args = parser.parse_args(argv)
    if args.repo:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        findings = validate(
            os.path.abspath(args.root),
            manifests=not args.no_manifest,
            repo=os.path.abspath(args.repo) if args.repo else None,
            index=not args.no_index,
        )
    except (OSError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    for finding in findings:
        print(finding)
    print("%d finding(s)" % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
