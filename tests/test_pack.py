# SPDX-License-Identifier: EUPL-1.2
import os
import tarfile
import unittest

import support
import pack
import themebuild
import validate


class PackTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.path("repo")
        support.make_repo(self.repo)

    def packed(self, name, epoch=1700000000):
        tree = self.path(name)
        themebuild.build(self.repo, tree, "full")
        archive = self.path(name + ".tar.xz")
        lines = pack.pack(tree, archive, epoch)
        with open(archive, "rb") as handle:
            return tree, archive, lines, handle.read()

    def test_independent_builds_give_identical_archives(self):
        _, _, first, first_bytes = self.packed("one")
        _, _, second, second_bytes = self.packed("two")
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first[0].split()[0], second[0].split()[0])

    def test_epoch_changes_archive(self):
        _, _, _, a = self.packed("one", 1700000000)
        _, _, _, b = self.packed("two", 1700000001)
        self.assertNotEqual(a, b)

    def test_archive_layout_and_ownership(self):
        _, archive, _, _ = self.packed("one")
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            self.assertEqual(members[0].name, "Resina")
            self.assertTrue(all(m.name == "Resina" or m.name.startswith("Resina/") for m in members))
            self.assertTrue(all(m.uid == 0 and m.gid == 0 and m.uname == "" and m.gname == "" for m in members))
            self.assertTrue(all(m.mtime == 1700000000 for m in members))
            self.assertTrue(all(m.mode == (0o755 if m.isdir() else 0o777 if m.issym() else 0o644) for m in members))
            links = [m for m in members if m.issym()]
            self.assertTrue(links)
            self.assertTrue(all("/" not in m.linkname for m in links))

    def test_members_sorted(self):
        _, archive, _, _ = self.packed("one")
        with tarfile.open(archive) as tar:
            names = [m.name for m in tar.getmembers()][1:]
        self.assertEqual(names, sorted(names))

    def test_checksum_file_matches_the_archive(self):
        _, archive, lines, data = self.packed("one")
        import hashlib

        self.assertEqual(lines[0].split()[0], hashlib.sha256(data).hexdigest())
        with open(archive + ".sha256", encoding="utf-8") as handle:
            self.assertEqual(handle.read().splitlines(), lines)

    def test_overlay_archive_needs_the_repository_for_its_links_to_the_core_set(self):
        import pack

        repo = self.path("repo")
        support.make_repo(repo)
        support.write(os.path.join(repo, "aliases/color.tsv"), "org.example.Beta" + chr(9) + "apps/alpha" + chr(9) + "thirdparty" + chr(10))
        tree = self.path("overlay")
        themebuild.build(repo, tree, "thirdparty")
        with self.assertRaises(pack.PackError):
            pack.pack(tree, self.path("a.tar.xz"), 0)
        pack.pack(tree, self.path("b.tar.xz"), 0, repo)

    def test_extraction_validates(self):
        _, archive, _, _ = self.packed("one")
        out = self.path("extract")
        os.makedirs(out)
        with tarfile.open(archive) as tar:
            tar.extractall(out, filter="tar")
        self.assertEqual(validate.validate(os.path.join(out, "Resina"), repo=self.repo), [])

    def test_missing_tree_fails(self):
        with self.assertRaises(pack.PackError):
            pack.pack(self.path("nothing"), self.path("x.tar.xz"), 0)

    def test_wrong_suffix_fails(self):
        tree = self.path("tree")
        themebuild.build(self.repo, tree, "full")
        with self.assertRaises(pack.PackError):
            pack.pack(tree, self.path("x.tar.gz"), 0)

    def test_invalid_tree_is_refused(self):
        tree = self.path("tree")
        themebuild.build(self.repo, tree, "full")
        os.remove(os.path.join(tree, "index.theme"))
        os.remove(os.path.join(tree, "scalable/apps/beta.svg"))
        with self.assertRaises(pack.PackError):
            pack.pack(tree, self.path("x.tar.xz"), 0)

    def test_unsafe_link_is_refused(self):
        tree = self.path("tree")
        themebuild.build(self.repo, tree, "full")
        link = os.path.join(tree, "scalable/places/game-folder.svg")
        os.remove(link)
        os.symlink("/etc/passwd", link)
        with self.assertRaises(pack.PackError):
            pack.pack(tree, self.path("x.tar.xz"), 0)

    def test_command_line_requires_an_epoch(self):
        tree = self.path("tree")
        themebuild.build(self.repo, tree, "full")
        saved = os.environ.pop("SOURCE_DATE_EPOCH", None)
        try:
            self.assertEqual(pack.main([tree, self.path("x.tar.xz")]), 1)
            os.environ["SOURCE_DATE_EPOCH"] = "not-a-number"
            self.assertEqual(pack.main([tree, self.path("x.tar.xz")]), 1)
            os.environ["SOURCE_DATE_EPOCH"] = "5"
            self.assertEqual(pack.main([tree, self.path("x.tar.xz")]), 0)
        finally:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
            if saved is not None:
                os.environ["SOURCE_DATE_EPOCH"] = saved


if __name__ == "__main__":
    unittest.main()
