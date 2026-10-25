# SPDX-License-Identifier: EUPL-1.2
import hashlib
import os
import re

import svgbake

THEME_NAME = "Resina"
COMPONENTS = ("core", "thirdparty")
NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
NOTICE_FILES = (("NOTICE", "NOTICE"), ("LICENSES/EUPL-1.2.txt", "EUPL-1.2.txt"), ("LICENSES/OFL-1.1.txt", "OFL-1.1.txt"))
OVERLAY_NOTICE_FILES = (("NOTICE", "NOTICE.thirdparty"), ("LICENSES/EUPL-1.2.txt", "EUPL-1.2.thirdparty.txt"), ("LICENSES/OFL-1.1.txt", "OFL-1.1.thirdparty.txt"))
PLAIN_DIRECTORIES = ("actions", "apps", "status", "devices", "emblems", "categories")
COLOR_SPEC_DIRECTORIES = {"Applications": "apps", "Categories": "categories", "Devices": "devices", "MimeTypes": "mimetypes", "Places": "places", "Status": "status"}
COLOR_CATEGORIES = ("apps", "places", "mimetypes", "devices", "status")
COLOR_CONTEXTS = {
    "apps": "Applications",
    "categories": "Categories",
    "places": "Places",
    "mimetypes": "MimeTypes",
    "devices": "Devices",
    "status": "Status",
    "places-small": "Places",
    "places-medium": "Places",
}
SYMBOLIC_DIRS = {
    "Actions": "actions",
    "Animations": "animations",
    "Applications": "apps",
    "Categories": "categories",
    "Devices": "devices",
    "Emblems": "emblems",
    "International": "intl",
    "MimeTypes": "mimetypes",
    "Places": "places",
    "Status": "status",
}
PROFILES = ("full", "core", "thirdparty")
COLOR_SIZE = 128
COLOR_MIN = 16
COLOR_MAX = 512
FOLDER_TIERS = (
    ("scalable/places-small", 22, 16, 24, "compact"),
    ("scalable/places-medium", 48, 25, 64, "relief"),
)
LARGE_FOLDER_MIN = 65
SYMBOLIC_SIZE = 16
SYMBOLIC_MIN = 8
SYMBOLIC_MAX = 512
ANIMATION_SIZES = (16, 22, 24, 32)
ANIMATED_ICONS = ("process-working",)


class BuildError(Exception):
    pass


def read_pairs(path):
    pairs = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 2:
                raise BuildError("malformed line in %s: %r" % (path, line))
            pairs.append((parts[0], parts[1]))
    return pairs


def read_alias_rows(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) == 2:
                parts.append("")
            if len(parts) != 3 or parts[2] not in ("", "thirdparty"):
                raise BuildError("malformed line in %s: %r" % (path, line))
            rows.append(tuple(parts))
    return rows


def read_names(path):
    names = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            check_name(line)
            if line in names:
                raise BuildError("duplicate entry %r in %s" % (line, path))
            names.append(line)
    return names


def unique_pairs(path):
    result = {}
    for key, value in read_pairs(path):
        if key in result:
            raise BuildError("duplicate entry %r in %s" % (key, path))
        result[key] = value
    return result


def check_name(name):
    if not NAME_PATTERN.fullmatch(name) or name.endswith(".svg"):
        raise BuildError("unsafe icon name %r" % name)


def list_svgs(directory):
    names = []
    for entry in sorted(os.listdir(directory)):
        full = os.path.join(directory, entry)
        if not entry.endswith(".svg") or os.path.islink(full) or not os.path.isfile(full):
            raise BuildError("unexpected entry in %s: %s" % (directory, entry))
        names.append(entry[:-4])
    return names


def check_source_layout(repo):
    allowed = {"src": ({"color", "symbolic", "symbolic-rtl"}, set()), "src/color": (set(COLOR_CATEGORIES), {"places-small", "places-medium"})}
    for base, (required, optional) in allowed.items():
        found = set(os.listdir(os.path.join(repo, base)))
        if not required <= found or not found <= required | optional:
            raise BuildError("unexpected entries in %s: %s" % (base, sorted(found ^ required)))


def color_dir(category, name, spec):
    if category == "apps" and (name.startswith("applications-") or spec.get(name) == "Categories"):
        return "categories"
    return category


class Plan:
    def __init__(self, repo):
        self.repo = repo
        self.files = []
        self.links = []
        self.classes = unique_pairs(os.path.join(repo, "names", "color-classes.tsv"))
        self.contexts = unique_pairs(os.path.join(repo, "names", "symbolic-contexts.tsv"))
        self.spec = unique_pairs(os.path.join(repo, "names", "naming-spec.tsv"))
        self.copies = []
        self.symbolic_classes = unique_pairs(os.path.join(repo, "names", "symbolic-classes.tsv"))
        self.color_alias_rows = read_alias_rows(os.path.join(repo, "aliases", "color.tsv"))
        self.symbolic_alias_rows = read_alias_rows(os.path.join(repo, "aliases", "symbolic.tsv"))
        self.color_dest = {}
        self.symbolic_dest = {}
        self.mirrors = read_names(os.path.join(repo, "names", "rtl-mirrors.txt"))
        self.drawn = {}
        self.component = {}

    def collect(self):
        check_source_layout(self.repo)
        for category in COLOR_CATEGORIES:
            src_dir = os.path.join(self.repo, "src", "color", category)
            for name in list_svgs(src_dir):
                directory = color_dir(category, name, self.spec)
                rel = "scalable/%s/%s.svg" % (directory, name)
                key = "%s/%s" % (category, name)
                if key in self.color_dest:
                    raise BuildError("duplicate source " + key)
                check_name(name)
                self.color_dest[key] = rel
                if self.classes.get(key) not in COMPONENTS:
                    raise BuildError("unclassified colour icon " + key)
                self.component[rel] = self.classes[key]
                self.files.append((rel, os.path.join(src_dir, name + ".svg"), "color"))
        src_dir = os.path.join(self.repo, "src", "symbolic")
        for name in list_svgs(src_dir):
            if name not in self.contexts:
                raise BuildError("symbolic icon without context " + name)
            context = self.contexts[name]
            if context not in SYMBOLIC_DIRS:
                raise BuildError("unknown context %s for %s" % (context, name))
            check_name(name)
            if self.symbolic_classes.get(name) not in COMPONENTS:
                raise BuildError("symbolic icon without class " + name)
            rel = "symbolic/%s/%s-symbolic.svg" % (SYMBOLIC_DIRS[context], name)
            self.symbolic_dest[name] = rel
            self.component[rel] = self.symbolic_classes[name]
            self.files.append((rel, os.path.join(src_dir, name + ".svg"), "symbolic"))
        for name in ANIMATED_ICONS:
            if name not in self.symbolic_dest:
                raise BuildError("animated icon without a symbolic source " + name)
            for size in ANIMATION_SIZES:
                rel = "animations/%d/%s.svg" % (size, name)
                self.component[rel] = self.component[self.symbolic_dest[name]]
                self.files.append((rel, os.path.join(src_dir, name + ".svg"), "sheet:%d" % size))
        rtl_dir = os.path.join(self.repo, "src", "symbolic-rtl")
        for name in list_svgs(rtl_dir):
            if name not in self.symbolic_dest:
                raise BuildError("right-to-left drawing without a symbolic icon " + name)
            self.drawn[name] = os.path.join(rtl_dir, name + ".svg")
        extra = (set(self.contexts) | set(self.symbolic_classes)) - set(self.symbolic_dest)
        if extra:
            raise BuildError("data for missing icons: %s" % sorted(extra))
        folded = {}
        for rel in [f[0] for f in self.files]:
            if folded.setdefault(rel.lower(), rel) != rel:
                raise BuildError("names differ only in case: %s and %s" % (folded[rel.lower()], rel))
        stale = set(self.classes) - set(self.color_dest)
        if stale:
            raise BuildError("classes for missing colour icons: %s" % sorted(stale))
        self.collect_aliases()
        self.collect_compact()

    def collect_compact(self):
        for directory, _, _, _, kind in FOLDER_TIERS:
            drawn = {}
            tier_dir = os.path.join(self.repo, "src", "color", directory.rpartition("/")[2])
            for name in list_svgs(tier_dir) if os.path.isdir(tier_dir) else []:
                if "places/" + name not in self.color_dest:
                    raise BuildError("compact drawing without a folder icon: " + name)
                drawn[name] = os.path.join(tier_dir, name + ".svg")
            variants = {}
            for key, rel in self.color_dest.items():
                if not rel.startswith("scalable/places/"):
                    continue
                name = key.partition("/")[2]
                source = os.path.join(self.repo, "src", "color", "places", name + ".svg")
                if name in drawn:
                    variants[source] = (drawn[name], "color")
                    continue
                with open(source, "rb") as handle:
                    if svgbake.compactable(handle.read()):
                        variants[source] = (source, kind)
                    else:
                        variants[source] = (source, "color")
            taken = set(rel for rel, _, _ in self.files)
            for rel, source, _ in list(self.files):
                if rel.startswith("scalable/places/") and source in variants:
                    tier_rel = "%s/%s" % (directory, rel.rpartition("/")[2])
                    self.component[tier_rel] = self.component[rel]
                    taken.add(tier_rel)
                    self.files.append((tier_rel, variants[source][0], variants[source][1]))
            for rel, base in list(self.links):
                if rel.startswith("scalable/places/") and "%s/%s" % (directory, base) in taken:
                    tier_rel = "%s/%s" % (directory, rel.rpartition("/")[2])
                    self.component[tier_rel] = self.component[rel]
                    self.links.append((tier_rel, base))

    def add_copy(self, copy_rel, target_rel, taken, owner):
        if copy_rel in taken:
            raise BuildError("alias collides with existing entry " + copy_rel)
        taken.add(copy_rel)
        source = [f[1] for f in self.files if f[0] == target_rel][0]
        self.component[copy_rel] = owner or self.component[target_rel]
        self.files.append((copy_rel, source, self.kind_of[target_rel]))
        self.copies.append(copy_rel)

    def collect_aliases(self):
        taken = set(rel for rel, _, _ in self.files)
        self.kind_of = {rel: kind for rel, _, kind in self.files}
        placed = []
        for name, target, owner in self.color_alias_rows:
            check_name(name)
            if target not in self.color_dest:
                raise BuildError("alias %s targets missing %s" % (name, target))
            target_rel = self.color_dest[target]
            directory, _, base = target_rel.rpartition("/")
            want = COLOR_SPEC_DIRECTORIES.get(self.spec.get(name, ""))
            if want and "scalable/" + want != directory:
                self.add_copy("scalable/%s/%s.svg" % (want, name), target_rel, taken, owner)
            else:
                self.add_link("%s/%s.svg" % (directory, name), base, taken, target_rel, owner)
        for name, target, owner in self.symbolic_alias_rows:
            check_name(name)
            if target not in self.symbolic_dest:
                raise BuildError("alias %s targets missing %s" % (name, target))
            target_rel = self.symbolic_dest[target]
            directory, _, base = target_rel.rpartition("/")
            want = SYMBOLIC_DIRS.get(self.spec.get(name, ""))
            if want and "symbolic/" + want != directory:
                self.add_copy("symbolic/%s/%s-symbolic.svg" % (want, name), target_rel, taken, owner)
                placed.append((name, "symbolic/" + want, "%s-symbolic.svg" % name, owner, "symbolic/%s/%s-symbolic.svg" % (want, name)))
            else:
                self.add_link("%s/%s-symbolic.svg" % (directory, name), base, taken, target_rel, owner)
                placed.append((name, directory, base, owner, target_rel))
        for name, rel in self.symbolic_dest.items():
            placed.append((name, rel.rpartition("/")[0], rel.rpartition("/")[2], "", rel))
        sources = {rel: path for rel, path, _ in self.files}
        drawn_for = {name: target for name, target, _ in self.symbolic_alias_rows if target in self.drawn}
        drawn_for.update({name: name for name in self.drawn if name in self.symbolic_dest})
        for name in self.mirrors:
            if name in drawn_for:
                raise BuildError("icon is both mirrored and drawn: " + name)
        variants = [(name, "symbolic-rtl", None) for name in self.mirrors]
        variants += [(name, "symbolic", self.drawn[target]) for name, target in sorted(drawn_for.items())]
        for name, kind, drawing in variants:
            found = [row for row in placed if row[0] == name]
            if len(found) != 1:
                raise BuildError("right-to-left icon is not a symbolic icon: " + name)
            _, directory, _, owner, target_rel = found[0]
            rel = "%s/%s-symbolic-rtl.svg" % (directory, name)
            if rel in taken:
                raise BuildError("right-to-left icon collides with existing entry " + rel)
            taken.add(rel)
            self.component[rel] = owner or self.component[target_rel]
            self.files.append((rel, drawing or sources[target_rel], kind))
        coloured = {key.split("/")[1] for key in self.color_dest} | {row[0] for row in self.color_alias_rows}
        for name, directory, base, owner, target_rel in sorted(placed):
            if directory.split("/")[1] not in PLAIN_DIRECTORIES or name in coloured:
                continue
            link_rel = "%s/%s.svg" % (directory, name)
            if link_rel in taken:
                continue
            self.add_link(link_rel, base, taken, target_rel, owner)

    def add_link(self, link_rel, base, taken, target_rel, owner):
        if link_rel in taken:
            raise BuildError("alias collides with existing entry " + link_rel)
        if link_rel.rsplit("/", 1)[1] == base:
            raise BuildError("alias points at itself " + link_rel)
        taken.add(link_rel)
        self.component[link_rel] = owner or self.component[target_rel]
        self.links.append((link_rel, base))

    def selected(self, profile):
        if profile not in PROFILES:
            raise BuildError("unknown profile " + profile)
        keep = {"full": ("core", "thirdparty"), "core": ("core",), "thirdparty": ("thirdparty",)}[profile]
        files = [f for f in self.files if self.component[f[0]] in keep]
        links = [l for l in self.links if self.component[l[0]] in keep]
        return files, links


def theme_directories(paths):
    seen = {}
    for rel in paths:
        directory = rel.rpartition("/")[0]
        seen[directory] = True
    return sorted(seen)


def index_theme(directories):
    lines = [
        "[Icon Theme]",
        "Name=%s" % THEME_NAME,
        "Comment=Resina icon theme: full-colour volumes and a 24-unit symbolic set",
        "Example=folder",
        "Inherits=hicolor",
        "FollowsColorScheme=true",
        "Directories=%s" % ",".join(directories),
        "",
    ]
    for directory in directories:
        kind, _, group = directory.partition("/")
        if kind == "animations":
            lines += ["[%s]" % directory, "Context=Animations", "Size=%d" % int(group), "Type=Fixed", ""]
            continue
        tier = [row for row in FOLDER_TIERS if row[0] == directory]
        if tier:
            size, low, high = tier[0][1:4]
            context = COLOR_CONTEXTS[group]
        elif kind == "scalable":
            size, low, high = COLOR_SIZE, COLOR_MIN, COLOR_MAX
            if directory == "scalable/places" and FOLDER_TIERS[0][0] in directories:
                low = LARGE_FOLDER_MIN
            context = COLOR_CONTEXTS[group]
        else:
            size, low, high = SYMBOLIC_SIZE, SYMBOLIC_MIN, SYMBOLIC_MAX
            context = {v: k for k, v in SYMBOLIC_DIRS.items()}[group]
        lines += [
            "[%s]" % directory,
            "Context=%s" % context,
            "Size=%d" % size,
            "MinSize=%d" % low,
            "MaxSize=%d" % high,
            "Type=Scalable",
            "",
        ]
    return "\n".join(lines)


def render(kind, source_path):
    with open(source_path, "rb") as handle:
        data = handle.read()
    if kind == "color":
        data = svgbake.bake_rim(data)
    elif kind == "compact":
        data = svgbake.bake_rim(svgbake.compact_folder(data))
    elif kind == "relief":
        data = svgbake.bake_rim(svgbake.relief_folder(data))
    elif kind.startswith("sheet:"):
        data = svgbake.animation_sheet(data, int(kind[6:]))
    elif kind == "symbolic-rtl":
        data = svgbake.bake_symbolic(svgbake.mirror_symbolic(data))
    else:
        data = svgbake.bake_symbolic(data)
    return data.rstrip(b"\n") + b"\n"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def build(repo, out, profile="full"):
    plan = Plan(repo)
    plan.collect()
    files, links = plan.selected(profile)
    if os.path.lexists(out):
        raise BuildError("output exists: " + out)
    every = theme_directories([f[0] for f in plan.files] + [l[0] for l in plan.links])
    core_only = theme_directories(
        [f[0] for f in plan.files if plan.component[f[0]] == "core"] + [l[0] for l in plan.links if plan.component[l[0]] == "core"]
    )
    if every != core_only:
        raise BuildError("core set lacks directories: %s" % sorted(set(every) - set(core_only)))
    components = {}
    for rel, source, kind in sorted(files):
        try:
            data = render(kind, source)
        except svgbake.BakeError as error:
            raise BuildError("%s: %s" % (rel, error)) from error
        write(os.path.join(out, rel), data)
        components.setdefault(plan.component[rel], []).append(("F", rel, sha256(data), len(data)))
    for rel, base in sorted(links):
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(base, path)
        components.setdefault(plan.component[rel], []).append(("L", rel, base, 0))
    if profile != "thirdparty":
        all_paths = [f[0] for f in plan.files if plan.component[f[0]] == "core" or profile == "full"] + [
            l[0] for l in plan.links if plan.component[l[0]] == "core" or profile == "full"
        ]
        text = index_theme(theme_directories(all_paths)).encode("utf-8")
        write(os.path.join(out, "index.theme"), text)
        components.setdefault("core", []).append(("F", "index.theme", sha256(text), len(text)))
        for source, name in NOTICE_FILES:
            with open(os.path.join(repo, source), "rb") as handle:
                text = handle.read()
            write(os.path.join(out, name), text)
            components["core"].append(("F", name, sha256(text), len(text)))
    if profile == "thirdparty":
        for source, name in OVERLAY_NOTICE_FILES:
            with open(os.path.join(repo, source), "rb") as handle:
                text = handle.read()
            write(os.path.join(out, name), text)
            components["thirdparty"].append(("F", name, sha256(text), len(text)))
    for component, entries in components.items():
        lines = []
        for kind, rel, value, size in sorted(entries, key=lambda e: e[1]):
            if kind == "F":
                lines.append("F %s %d %s" % (value, size, rel))
            else:
                lines.append("L %s %s" % (rel, value))
        write(os.path.join(out, "MANIFEST.%s" % component), ("\n".join(lines) + "\n").encode("utf-8"))
    return out
