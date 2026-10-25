#!/usr/bin/env python3
# SPDX-License-Identifier: EUPL-1.2
import argparse
import hashlib
import io
import lzma
import os
import sys
import tarfile

import validate

THEME = "Resina"


class PackError(Exception):
    pass


def entries(tree):
    found = []
    for dirpath, dirs, files in os.walk(tree):
        dirs.sort()
        rel_dir = os.path.relpath(dirpath, tree)
        if rel_dir != ".":
            found.append(rel_dir.replace(os.sep, "/"))
        for name in sorted(files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]):
            rel = name if rel_dir == "." else "%s/%s" % (rel_dir.replace(os.sep, "/"), name)
            found.append(rel)
    return sorted(set(found))


def make_tar(tree, epoch):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        top = tarfile.TarInfo(THEME)
        top.type = tarfile.DIRTYPE
        top.mode = 0o755
        top.mtime = epoch
        archive.addfile(top)
        for rel in entries(tree):
            full = os.path.join(tree, rel)
            info = tarfile.TarInfo("%s/%s" % (THEME, rel))
            info.mtime = epoch
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if os.path.islink(full):
                info.type = tarfile.SYMTYPE
                info.linkname = os.readlink(full)
                info.mode = 0o777
                archive.addfile(info)
            elif os.path.isdir(full):
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                archive.addfile(info)
            else:
                with open(full, "rb") as handle:
                    data = handle.read()
                info.size = len(data)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def pack(tree, output, epoch, repo=None):
    if not os.path.isdir(tree):
        raise PackError("not a directory: " + tree)
    if not output.endswith(".tar.xz"):
        raise PackError("output name must end with .tar.xz: " + output)
    findings = validate.validate(tree, repo=repo, index=os.path.exists(os.path.join(tree, "index.theme")))
    if findings:
        raise PackError("tree does not validate (%d finding(s)), first: %s" % (len(findings), findings[0]))
    tar = make_tar(tree, epoch)
    compressed = lzma.compress(tar, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=6)
    with open(output, "wb") as handle:
        handle.write(compressed)
    lines = ["%s  %s" % (hashlib.sha256(compressed).hexdigest(), os.path.basename(output))]
    with open(output + ".sha256", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create a reproducible theme archive")
    parser.add_argument("tree")
    parser.add_argument("output")
    parser.add_argument("--epoch", type=int, default=None)
    parser.add_argument("--repo", default=None, help="repository root; lets an overlay tree link to files of the core set")
    args = parser.parse_args(argv)
    epoch = args.epoch
    if epoch is None:
        value = os.environ.get("SOURCE_DATE_EPOCH")
        if value is None:
            print("error: pass --epoch or set SOURCE_DATE_EPOCH", file=sys.stderr)
            return 1
        try:
            epoch = int(value)
        except ValueError:
            print("error: SOURCE_DATE_EPOCH is not an integer: %r" % value, file=sys.stderr)
            return 1
    try:
        for line in pack(os.path.abspath(args.tree), os.path.abspath(args.output), epoch, os.path.abspath(args.repo) if args.repo else None):
            print(line)
    except (PackError, OSError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
