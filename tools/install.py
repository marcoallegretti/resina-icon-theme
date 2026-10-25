#!/usr/bin/env python3
# SPDX-License-Identifier: EUPL-1.2
import argparse
import contextlib
import errno
import fcntl
import hashlib
import os
import re
import stat
import sys

THEME = "Resina"
MANIFEST_PREFIX = "MANIFEST."
PENDING_PREFIX = "PENDING."
DIRECTORY_MODE = 0o755
FILE_MODE = 0o644
DURABLE = True
CACHE = "icon-theme.cache"
DIGEST = re.compile(r"[0-9a-f]{64}")
LINK_TARGET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
COMPONENT = re.compile(r"[a-z][a-z0-9-]*")
TEMPORARY = ".resina-install-"
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
RESERVED_PREFIXES = (MANIFEST_PREFIX, PENDING_PREFIX)


class InstallError(Exception):
    pass


def default_icons_dir():
    base = os.environ.get("XDG_DATA_HOME", "")
    if not os.path.isabs(base):
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "icons")


def safe(rel):
    parts = rel.split("/")
    if rel.startswith("/") or "" in parts or ".." in parts or "." in parts:
        raise InstallError("unsafe path in manifest: %r" % rel)
    if parts[-1].startswith(TEMPORARY) or parts[0].startswith(RESERVED_PREFIXES):
        raise InstallError("reserved name in manifest: %r" % rel)
    if any(len(part.encode("utf-8")) > 200 or any(ord(c) < 32 for c in part) for part in parts):
        raise InstallError("unusable name in manifest: %r" % rel)


def parse_manifest(text, label):
    entries = {}
    for line in text.splitlines():
        parts = line.split(" ", 3)
        if parts[0] == "F" and len(parts) == 4:
            if not DIGEST.fullmatch(parts[1]) or not (parts[2].isascii() and parts[2].isdigit()):
                raise InstallError("malformed file entry in %s: %r" % (label, line))
            rel, entry = parts[3], ("F", parts[1], int(parts[2]))
        elif parts[0] == "L" and len(parts) == 3:
            if not LINK_TARGET.fullmatch(parts[2]):
                raise InstallError("unsafe link target in %s: %r" % (label, line))
            rel, entry = parts[1], ("L", parts[2], 0)
        else:
            raise InstallError("malformed manifest line in %s: %r" % (label, line))
        safe(rel)
        if rel in entries:
            raise InstallError("duplicate manifest entry %r" % rel)
        entries[rel] = entry
    links = {rel for rel, entry in entries.items() if entry[0] == "L"}
    for rel in entries:
        parent = rel.rpartition("/")[0]
        while parent:
            if parent in links or parent in entries:
                raise InstallError("manifest entry below a link or file: %r" % rel)
            parent = parent.rpartition("/")[0]
    return entries


def read_source_manifest(path):
    with open(path, encoding="utf-8") as handle:
        return parse_manifest(handle.read(), path)


def components_of(tree):
    names = sorted(n[len(MANIFEST_PREFIX):] for n in os.listdir(tree) if n.startswith(MANIFEST_PREFIX))
    for name in names:
        if not COMPONENT.fullmatch(name):
            raise InstallError("unsafe component name %r" % name)
    return names


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_source(tree, rel, entry):
    path = os.path.join(tree, rel)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise InstallError("source is missing: " + rel)
    if not stat.S_ISREG(info.st_mode):
        raise InstallError("source is not a regular file: " + rel)
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) != entry[2] or sha256_bytes(data) != entry[1]:
        raise InstallError("source differs from its manifest entry: " + rel)
    return data


class Theme:
    def __init__(self, descriptor, path):
        self.descriptor = descriptor
        self.path = path

    def close(self):
        os.close(self.descriptor)

    @contextlib.contextmanager
    def directory(self, rel_dir, create=False):
        chain = []
        current = os.dup(self.descriptor)
        chain.append(current)
        try:
            for part in [p for p in rel_dir.split("/") if p]:
                try:
                    following = os.open(part, DIRECTORY_FLAGS, dir_fd=current)
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, DIRECTORY_MODE, dir_fd=current)
                    following = os.open(part, DIRECTORY_FLAGS, dir_fd=current)
                    os.fchmod(following, DIRECTORY_MODE)
                except OSError as error:
                    if error.errno in (errno.ELOOP, errno.ENOTDIR):
                        raise InstallError("path component is not a plain directory: %s/%s" % (rel_dir, part))
                    raise
                chain.append(following)
                current = following
            yield current
        finally:
            for descriptor in chain:
                os.close(descriptor)

    def split(self, rel):
        parent, _, name = rel.rpartition("/")
        return parent, name

    def lstat(self, rel):
        parent, name = self.split(rel)
        try:
            with self.directory(parent) as descriptor:
                return os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return None

    def read_regular(self, rel):
        parent, name = self.split(rel)
        try:
            with self.directory(parent) as descriptor:
                handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                if not stat.S_ISREG(os.fstat(handle).st_mode):
                    os.close(handle)
                    return None
                with os.fdopen(handle, "rb") as stream:
                    return stream.read()
        except (FileNotFoundError, InstallError):
            return None
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.ENXIO):
                return None
            raise

    def readlink(self, rel):
        parent, name = self.split(rel)
        try:
            with self.directory(parent) as descriptor:
                return os.readlink(name, dir_fd=descriptor)
        except (FileNotFoundError, OSError, InstallError):
            return None

    def matches(self, rel, entry):
        kind, value, size = entry
        if kind == "L":
            return self.readlink(rel) == value
        data = self.read_regular(rel)
        return data is not None and len(data) == size and sha256_bytes(data) == value

    def replace(self, rel, create, durable=False):
        parent, name = self.split(rel)
        with self.directory(parent, create=True) as descriptor:
            try:
                existing = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None and stat.S_ISDIR(existing.st_mode):
                raise InstallError("a directory exists where a file belongs: " + rel)
            temporary = "%s%d-%s" % (TEMPORARY, os.getpid(), name)
            try:
                create(descriptor, temporary)
                os.rename(temporary, name, src_dir_fd=descriptor, dst_dir_fd=descriptor)
                if durable and DURABLE:
                    os.fsync(descriptor)
            finally:
                try:
                    os.unlink(temporary, dir_fd=descriptor)
                except FileNotFoundError:
                    pass

    def write_file(self, rel, data, durable=False):
        def create(descriptor, temporary):
            handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE, dir_fd=descriptor)
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
                os.fchmod(stream.fileno(), FILE_MODE)
                if durable and DURABLE:
                    stream.flush()
                    os.fsync(stream.fileno())

        self.replace(rel, create, durable)

    def write_link(self, rel, value):
        self.replace(rel, lambda descriptor, temporary: os.symlink(value, temporary, dir_fd=descriptor))

    def remove(self, rel):
        parent, name = self.split(rel)
        with self.directory(parent) as descriptor:
            os.unlink(name, dir_fd=descriptor)

    def listdir(self, rel_dir=""):
        try:
            with self.directory(rel_dir) as descriptor:
                return sorted(os.listdir(descriptor))
        except (FileNotFoundError, InstallError):
            return []

    def prune_empty(self, rel):
        parent = rel.rpartition("/")[0]
        while parent:
            grand, _, name = parent.rpartition("/")
            try:
                with self.directory(grand) as descriptor:
                    os.rmdir(name, dir_fd=descriptor)
            except (OSError, InstallError):
                return
            parent = grand


def open_theme(icons_dir, create):
    icons = os.path.abspath(icons_dir)
    if create:
        os.makedirs(icons, DIRECTORY_MODE, exist_ok=True)
    try:
        parent = os.open(icons, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        return None
    try:
        made = False
        try:
            os.mkdir(THEME, DIRECTORY_MODE, dir_fd=parent) if create else None
            made = create
        except FileExistsError:
            pass
        try:
            descriptor = os.open(THEME, DIRECTORY_FLAGS, dir_fd=parent)
        except FileNotFoundError:
            return None
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.ENOTDIR):
                raise InstallError("theme path is not a plain directory: " + os.path.join(icons, THEME))
            raise
        if made:
            os.fchmod(descriptor, DIRECTORY_MODE)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return Theme(descriptor, os.path.join(icons, THEME))
    finally:
        os.close(parent)


def lock_theme(icons_dir, create):
    for _ in range(20):
        theme = open_theme(icons_dir, create)
        if theme is None:
            return None
        parent = os.open(os.path.abspath(icons_dir), os.O_RDONLY | os.O_DIRECTORY)
        try:
            try:
                current = os.stat(THEME, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                current = None
        finally:
            os.close(parent)
        held = os.fstat(theme.descriptor)
        if current is not None and (current.st_dev, current.st_ino) == (held.st_dev, held.st_ino):
            return theme
        theme.close()
    raise InstallError("the theme directory keeps changing: " + os.path.join(icons_dir, THEME))


def tracked_entries(theme, component, lenient=False, unreadable=None):
    entries = {}
    for prefix in (MANIFEST_PREFIX, PENDING_PREFIX):
        data = theme.read_regular(prefix + component)
        if data is None:
            continue
        try:
            parsed = parse_manifest(data.decode("utf-8"), prefix + component)
        except (InstallError, UnicodeDecodeError):
            if not lenient:
                raise
            if unreadable is not None:
                unreadable.append(prefix + component)
            continue
        for rel, entry in parsed.items():
            entries.setdefault(rel, []).append(entry)
    return entries


def installed_components(theme):
    names = set()
    for name in theme.listdir():
        for prefix in (MANIFEST_PREFIX, PENDING_PREFIX):
            if name.startswith(prefix) and COMPONENT.fullmatch(name[len(prefix):]):
                names.add(name[len(prefix):])
    return sorted(names)


def owned_elsewhere(theme, component, lenient=False):
    owned = {}
    for other in installed_components(theme):
        if other != component:
            for rel, entries in tracked_entries(theme, other, lenient).items():
                owned.setdefault(rel, {})[other] = entries
    return owned


def manifest_bytes(entries):
    lines = []
    for rel in sorted(entries):
        kind, value, size = entries[rel]
        lines.append("F %s %d %s" % (value, size, rel) if kind == "F" else "L %s %s" % (rel, value))
    return ("\n".join(lines) + "\n").encode("utf-8")


def matches_any(theme, rel, candidates):
    return any(theme.matches(rel, entry) for entry in candidates)


def install_entry(theme, rel, entry, data):
    if entry[0] == "L":
        theme.write_link(rel, entry[1])
    else:
        theme.write_file(rel, data)


def drop_cache(theme):
    if theme.lstat(CACHE) is not None and theme.read_regular(CACHE) is not None:
        theme.remove(CACHE)


def remove_tracked(theme, tracked, protected=frozenset()):
    removed, kept = 0, []
    for rel in sorted(tracked):
        if rel in protected:
            continue
        try:
            present = theme.lstat(rel) is not None
        except InstallError:
            kept.append(rel)
            continue
        if not present:
            continue
        if matches_any(theme, rel, tracked[rel]):
            theme.remove(rel)
            theme.prune_empty(rel)
            removed += 1
        else:
            kept.append(rel)
    return removed, kept


def load_tree(tree):
    components = components_of(tree)
    if not components:
        raise InstallError("no manifest in source tree")
    staged, seen = [], {}
    for component in components:
        new = read_source_manifest(os.path.join(tree, MANIFEST_PREFIX + component))
        for rel in new:
            if rel in seen:
                raise InstallError("%r is listed by components %s and %s" % (rel, seen[rel], component))
            seen[rel] = component
        data = {rel: read_source(tree, rel, entry) for rel, entry in new.items() if entry[0] == "F"}
        staged.append((component, new, data))
    return staged


def install(tree, icons_dir, force=False):
    staged = load_tree(os.path.abspath(tree))
    icons = os.path.abspath(icons_dir)
    probe = os.path.join(icons, THEME)
    if os.path.islink(probe):
        raise InstallError("theme directory is a symbolic link: " + probe)
    if os.path.lexists(probe) and not os.path.isdir(probe):
        raise InstallError("theme path is not a directory: " + probe)
    theme = lock_theme(icons, create=True)
    report = {"installed": 0, "preserved": [], "removed_stale": 0, "overwritten": []}
    try:
        tracked_any = bool(installed_components(theme))
        if [n for n in theme.listdir() if n != CACHE] and not tracked_any and not force:
            raise InstallError("refusing to modify an existing theme directory that this tool did not install")
        plans = []
        shipped = {component: new for component, new, _ in staged}
        every_new = set().union(*[set(new) for new in shipped.values()])
        for component, new, data in staged:
            known = tracked_entries(theme, component, lenient=force)
            foreign = owned_elsewhere(theme, component, lenient=force)
            moved = {}
            for rel in new:
                owners = foreign.get(rel, {})
                for owner, entries in owners.items():
                    if owner not in shipped or rel in shipped[owner]:
                        raise InstallError("path belongs to another component: " + rel)
                    moved.setdefault(rel, []).extend(entries)
                if theme.lstat(rel) is not None and rel not in known and rel not in moved and not force:
                    raise InstallError("refusing to overwrite untracked file: " + rel)
            plans.append((component, new, data, known, moved))
        for component, new, data, known, moved in plans:
            stale = {rel: entries for rel, entries in known.items() if rel not in every_new}
            removed, kept = remove_tracked(theme, stale)
            report["removed_stale"] += removed
            report["preserved"] += kept
            record = dict(new)
            for rel in kept:
                record[rel] = stale[rel][-1]
            theme.write_file(PENDING_PREFIX + component, manifest_bytes(record), durable=True)
            for rel, entry in sorted(new.items()):
                candidates = known.get(rel, []) + moved.get(rel, []) + [entry]
                tracked = rel in known or rel in moved
                if tracked and theme.lstat(rel) is not None and not matches_any(theme, rel, candidates):
                    report["preserved"].append(rel)
                    continue
                if force and not tracked and theme.lstat(rel) is not None and not matches_any(theme, rel, [entry]):
                    report["overwritten"].append(rel)
                install_entry(theme, rel, entry, data.get(rel))
                report["installed"] += 1
            theme.write_file(MANIFEST_PREFIX + component, manifest_bytes(record), durable=True)
            theme.remove(PENDING_PREFIX + component)
        drop_cache(theme)
    finally:
        theme.close()
    return report


def clean_leftovers(top):
    for directory, directories, names in os.walk(top):
        for name in names:
            path = os.path.join(directory, name)
            if name.startswith(TEMPORARY) and not os.path.islink(path) and os.path.isfile(path):
                os.unlink(path)
    for directory, directories, names in os.walk(top, topdown=False):
        if directory != top and not os.path.islink(directory):
            try:
                os.rmdir(directory)
            except OSError:
                pass


def uninstall(icons_dir, components=None, force=False):
    icons = os.path.abspath(icons_dir)
    probe = os.path.join(icons, THEME)
    if os.path.islink(probe):
        raise InstallError("theme directory is a symbolic link: " + probe)
    if os.path.lexists(probe) and not os.path.isdir(probe):
        raise InstallError("theme path is not a directory: " + probe)
    theme = lock_theme(icons, create=False)
    report = {"removed": 0, "preserved": [], "unreadable": []}
    if theme is None:
        return report
    try:
        present = installed_components(theme)
        selected = [c for c in present if components is None or c in components]
        remaining = [c for c in present if c not in selected]
        if "core" in selected and remaining and not force:
            raise InstallError("the core set cannot be removed while %s remains installed; remove it first or use --force" % ", ".join(remaining))
        loaded = {c: tracked_entries(theme, c, lenient=force, unreadable=report["unreadable"]) for c in selected}
        protected = set()
        for other in remaining:
            protected.update(tracked_entries(theme, other, lenient=True))
        for component in selected:
            tracked = loaded[component]
            removed, kept = remove_tracked(theme, tracked, protected)
            report["removed"] += removed
            report["preserved"] += kept
            if kept:
                theme.write_file(MANIFEST_PREFIX + component, manifest_bytes({rel: tracked[rel][-1] for rel in kept}), durable=True)
                if theme.lstat(PENDING_PREFIX + component) is not None:
                    theme.remove(PENDING_PREFIX + component)
                continue
            for prefix in (PENDING_PREFIX, MANIFEST_PREFIX):
                if theme.lstat(prefix + component) is not None:
                    theme.remove(prefix + component)
        drop_cache(theme)
        if components is None:
            clean_leftovers(probe)
        try:
            os.rmdir(probe)
        except OSError:
            pass
    finally:
        theme.close()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install or remove the Resina icon theme (POSIX systems)")
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("install", help="install a built theme tree")
    add.add_argument("tree", help="directory produced by build.py")
    add.add_argument("--icons-dir", default=default_icons_dir(), help="icon directory, default $XDG_DATA_HOME/icons or ~/.local/share/icons")
    add.add_argument("--force", action="store_true", help="overwrite untracked files that collide with theme files and ignore unreadable manifests")
    rem = sub.add_parser("uninstall", help="remove the installed theme")
    rem.add_argument("--icons-dir", default=default_icons_dir(), help="icon directory, default $XDG_DATA_HOME/icons or ~/.local/share/icons")
    rem.add_argument("--component", action="append", help="remove only this component, for example thirdparty")
    rem.add_argument("--force", action="store_true", help="discard unreadable manifests instead of stopping")
    args = parser.parse_args(argv)
    try:
        if args.action == "install":
            report = install(args.tree, args.icons_dir, args.force)
        else:
            report = uninstall(args.icons_dir, args.component, args.force)
    except (InstallError, OSError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
