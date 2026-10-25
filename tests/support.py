# SPDX-License-Identifier: EUPL-1.2
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import install

install.DURABLE = False

COLOR_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">'
    '<defs><filter id="sh" x="-30%" y="-100%" width="160%" height="300%"><feGaussianBlur stdDeviation="3"/></filter>'
    '<filter id="rim" x="-8%" y="-8%" width="116%" height="116%" color-interpolation-filters="sRGB">'
    '<feMorphology in="SourceAlpha" operator="dilate" radius="2" result="d"/><feFlood flood-color="#a6622e"/>'
    '<feComposite in2="d" operator="in"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
    '<g filter="url(#rim)"><ellipse cx="64" cy="114" rx="40" ry="4" fill="#000" opacity=".3" filter="url(#sh)"/>'
    '<path d="M20 20H108V100H20Z" fill="#f5b33b"/>'
    '<clipPath id="c1"><path d="M20 20H108V100H20Z"/></clipPath>'
    '<path d="M20 20H108V100H20Z" fill="none" stroke="#fff" stroke-width="4" clip-path="url(#c1)"/></g></svg>'
)

SPINNER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="9" opacity=".35"/><path d="M12 3A9 9 0 0 1 19.79 16.5"/></svg>'
)
SYMBOLIC_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>'
)

COLOR_ICONS = {
    "apps/alpha": "core",
    "apps/beta": "thirdparty",
    "apps/applications-games": "core",
    "places/folder": "core",
    "places/folder-github": "thirdparty",
    "mimetypes/text-x-generic": "core",
    "devices/computer": "core",
    "status/image-missing": "core",
}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def make_repo(root):
    for key in COLOR_ICONS:
        write(os.path.join(root, "src/color/%s.svg" % key), COLOR_SVG)
    write(os.path.join(root, "src/symbolic/go-next.svg"), SYMBOLIC_SVG)
    write(os.path.join(root, "src/symbolic/emblem-ok.svg"), SYMBOLIC_SVG)
    write(os.path.join(root, "src/symbolic/emblem-brand.svg"), SYMBOLIC_SVG)
    write(os.path.join(root, "src/symbolic/process-working.svg"), SPINNER_SVG)
    write(os.path.join(root, "names/color-classes.tsv"), "".join("%s\t%s\n" % item for item in sorted(COLOR_ICONS.items())))
    write(os.path.join(root, "names/symbolic-contexts.tsv"), "emblem-brand\tEmblems\nemblem-ok\tEmblems\ngo-next\tActions\nprocess-working\tAnimations\n")
    write(os.path.join(root, "names/symbolic-classes.tsv"), "emblem-brand\tthirdparty\nemblem-ok\tcore\ngo-next\tcore\nprocess-working\tcore\n")
    os.makedirs(os.path.join(root, "src/symbolic-rtl"), exist_ok=True)
    write(os.path.join(root, "names/rtl-mirrors.txt"), "go-next" + chr(10))
    write(os.path.join(root, "names/naming-spec.tsv"), "applications-office" + chr(9) + "Categories" + chr(10) + "go-next" + chr(9) + "Actions" + chr(10) + "pan-up" + chr(9) + "Status" + chr(10))
    write(os.path.join(root, "aliases/color.tsv"), "org.example.Beta\tapps/beta\ngame-folder\tplaces/folder\n")
    write(os.path.join(root, "aliases/symbolic.tsv"), "pan-end\tgo-next\n")
    write(os.path.join(root, "NOTICE"), "notice text\n")
    write(os.path.join(root, "LICENSES/EUPL-1.2.txt"), "licence text\n")
    write(os.path.join(root, "LICENSES/OFL-1.1.txt"), "font licence text\n")


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="resina-test-")
        self.saved_stderr = sys.stderr
        sys.stderr = io.StringIO()
        self.addCleanup(setattr, sys, "stderr", self.saved_stderr)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)


def tree_digest(root):
    digest = hashlib.sha256()
    for dirpath, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            digest.update(rel.encode())
            if os.path.islink(full):
                digest.update(b"L" + os.readlink(full).encode())
            else:
                with open(full, "rb") as handle:
                    digest.update(handle.read())
    return digest.hexdigest()


def sha256_file(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()
