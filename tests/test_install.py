# SPDX-License-Identifier: EUPL-1.2
import os
import stat

import support
import install
import themebuild
import validate


class InstallTestCase(support.TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.path("repo")
        support.make_repo(self.repo)
        self.tree = self.path("tree")
        themebuild.build(self.repo, self.tree, "full")
        self.icons = self.path("icons")
        os.makedirs(os.path.join(self.icons, "Other", "scalable"))
        support.write(os.path.join(self.icons, "Other", "index.theme"), "[Icon Theme]\nName=Other\n")
        self.target = os.path.join(self.icons, "Resina")

    def listing(self, root):
        found = []
        for dirpath, dirs, files in os.walk(root):
            for name in files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]:
                found.append(os.path.relpath(os.path.join(dirpath, name), root))
        return sorted(found)

    def manual_tree(self, name, manifest_lines, files):
        tree = self.path(name)
        os.makedirs(tree)
        for rel, data in files.items():
            support.write(os.path.join(tree, rel), data)
        support.write(os.path.join(tree, "MANIFEST.core"), "\n".join(manifest_lines) + "\n")
        return tree

    def file_line(self, rel, data):
        import hashlib

        return "F %s %d %s" % (hashlib.sha256(data.encode()).hexdigest(), len(data.encode()), rel)


class LifecycleTests(InstallTestCase):
    def test_fresh_install_matches_tree(self):
        install.install(self.tree, self.icons)
        self.assertEqual(self.listing(self.target), self.listing(self.tree))
        self.assertEqual(validate.validate(self.target, repo=self.repo), [])

    def test_install_is_idempotent(self):
        install.install(self.tree, self.icons)
        before = support.tree_digest(self.target)
        install.install(self.tree, self.icons)
        self.assertEqual(support.tree_digest(self.target), before)

    def test_modes_ignore_the_umask(self):
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)
        install.install(self.tree, self.icons)
        for dirpath, dirs, files in os.walk(self.target):
            for name in dirs:
                self.assertEqual(stat.S_IMODE(os.lstat(os.path.join(dirpath, name)).st_mode), 0o755, name)
            for name in files:
                full = os.path.join(dirpath, name)
                if not os.path.islink(full):
                    self.assertEqual(stat.S_IMODE(os.lstat(full).st_mode), 0o644, name)
        self.assertEqual(stat.S_IMODE(os.stat(self.target).st_mode), 0o755)

    def test_no_temporary_files_remain(self):
        install.install(self.tree, self.icons)
        self.assertEqual([p for p in self.listing(self.target) if install.TEMPORARY in p], [])

    def test_unrelated_theme_untouched(self):
        before = support.tree_digest(os.path.join(self.icons, "Other"))
        install.install(self.tree, self.icons)
        install.uninstall(self.icons)
        self.assertEqual(support.tree_digest(os.path.join(self.icons, "Other")), before)

    def test_uninstall_removes_everything_tracked(self):
        install.install(self.tree, self.icons)
        report = install.uninstall(self.icons)
        self.assertFalse(os.path.exists(self.target))
        self.assertEqual(report["preserved"], [])

    def test_uninstall_preserves_user_files(self):
        install.install(self.tree, self.icons)
        support.write(os.path.join(self.target, "scalable/apps/mine.svg"), "<svg/>")
        install.uninstall(self.icons)
        self.assertEqual(self.listing(self.target), ["scalable/apps/mine.svg"])

    def test_uninstall_keeps_tracking_of_modified_files(self):
        install.install(self.tree, self.icons)
        path = os.path.join(self.target, "scalable/places/folder.svg")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("<!-- edited -->")
        report = install.uninstall(self.icons)
        self.assertIn("scalable/places/folder.svg", report["preserved"])
        manifest = os.path.join(self.target, "MANIFEST.core")
        self.assertTrue(os.path.exists(manifest))
        with open(manifest, encoding="utf-8") as handle:
            self.assertEqual(len(handle.read().splitlines()), 1)
        install.install(self.tree, self.icons)
        self.assertTrue(os.path.exists(os.path.join(self.target, "scalable/apps/alpha.svg")))
        with open(path, encoding="utf-8") as handle:
            self.assertTrue(handle.read().endswith("<!-- edited -->"))

    def test_upgrade_replaces_and_removes_stale(self):
        install.install(self.tree, self.icons)
        os.remove(os.path.join(self.repo, "src/color/places/folder.svg"))
        support.write(os.path.join(self.repo, "src/color/places/folder-new.svg"), support.COLOR_SVG)
        classes = dict(support.COLOR_ICONS)
        del classes["places/folder"]
        classes["places/folder-new"] = "core"
        support.write(os.path.join(self.repo, "names/color-classes.tsv"), "".join("%s\t%s\n" % item for item in sorted(classes.items())))
        support.write(os.path.join(self.repo, "aliases/color.tsv"), "org.example.Beta\tapps/beta\n")
        newtree = self.path("tree2")
        themebuild.build(self.repo, newtree, "full")
        report = install.install(newtree, self.icons)
        self.assertGreater(report["removed_stale"], 0)
        self.assertFalse(os.path.lexists(os.path.join(self.target, "scalable/places/folder.svg")))
        self.assertFalse(os.path.lexists(os.path.join(self.target, "scalable/places/game-folder.svg")))
        self.assertTrue(os.path.exists(os.path.join(self.target, "scalable/places/folder-new.svg")))
        self.assertEqual(validate.validate(self.target), [])

    def test_upgrade_preserves_user_modification(self):
        install.install(self.tree, self.icons)
        path = os.path.join(self.target, "scalable/status/image-missing.svg")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("<!-- edited -->")
        edited = support.sha256_file(path)
        report = install.install(self.tree, self.icons)
        self.assertEqual(report["preserved"], ["scalable/status/image-missing.svg"])
        self.assertEqual(support.sha256_file(path), edited)

    def test_overlay_installs_and_uninstalls_separately(self):
        core = self.path("core")
        overlay = self.path("overlay")
        themebuild.build(self.repo, core, "core")
        themebuild.build(self.repo, overlay, "thirdparty")
        install.install(core, self.icons)
        install.install(overlay, self.icons)
        self.assertTrue(os.path.exists(os.path.join(self.target, "scalable/apps/beta.svg")))
        install.uninstall(self.icons, ["thirdparty"])
        self.assertFalse(os.path.exists(os.path.join(self.target, "scalable/apps/beta.svg")))
        self.assertTrue(os.path.exists(os.path.join(self.target, "scalable/apps/alpha.svg")))
        self.assertEqual(validate.validate(self.target, repo=self.repo), [])

    def test_installing_a_smaller_profile_keeps_the_other_component_tracked(self):
        install.install(self.tree, self.icons)
        core = self.path("core")
        themebuild.build(self.repo, core, "core")
        install.install(core, self.icons)
        self.assertTrue(os.path.exists(os.path.join(self.target, "MANIFEST.thirdparty")))
        self.assertTrue(os.path.exists(os.path.join(self.target, "scalable/apps/beta.svg")))

    def test_missing_manifest_in_source_fails(self):
        for name in os.listdir(self.tree):
            if name.startswith("MANIFEST."):
                os.remove(os.path.join(self.tree, name))
        with self.assertRaises(install.InstallError):
            install.install(self.tree, self.icons)

    def test_command_line_reports_errors_without_traceback(self):
        self.assertEqual(install.main(["install", self.path("nothing"), "--icons-dir", self.icons]), 1)
        self.assertEqual(install.main(["install", self.tree, "--icons-dir", self.icons]), 0)
        self.assertEqual(install.main(["uninstall", "--icons-dir", self.icons]), 0)


class RefusalTests(InstallTestCase):
    def test_refuses_foreign_theme_directory(self):
        os.makedirs(self.target)
        support.write(os.path.join(self.target, "index.theme"), "[Icon Theme]\nName=Resina\n")
        with self.assertRaises(install.InstallError):
            install.install(self.tree, self.icons)
        self.assertEqual(self.listing(self.target), ["index.theme"])

    def test_refuses_untracked_collision_without_writing_anything(self):
        install.install(self.tree, self.icons)
        os.remove(os.path.join(self.target, "MANIFEST.thirdparty"))
        before = support.tree_digest(self.target)
        with self.assertRaises(install.InstallError):
            install.install(self.tree, self.icons)
        self.assertEqual(support.tree_digest(self.target), before)

    def test_force_overwrites_foreign_theme_directory(self):
        os.makedirs(self.target)
        support.write(os.path.join(self.target, "index.theme"), "[Icon Theme]\nName=Resina\n")
        install.install(self.tree, self.icons, force=True)
        self.assertEqual(validate.validate(self.target, repo=self.repo), [])

    def test_force_over_a_directory_fails_cleanly_and_recovers(self):
        os.makedirs(os.path.join(self.target, "scalable/apps/alpha.svg"))
        support.write(os.path.join(self.target, "scalable/apps/alpha.svg/x"), "x")
        with self.assertRaises(install.InstallError):
            install.install(self.tree, self.icons, force=True)
        self.assertTrue(os.path.isdir(os.path.join(self.target, "scalable/apps/alpha.svg")))

    def test_refuses_symlinked_theme_directory(self):
        os.symlink(os.path.join(self.icons, "Other"), self.target)
        with self.assertRaises(install.InstallError):
            install.install(self.tree, self.icons)
        with self.assertRaises(install.InstallError):
            install.uninstall(self.icons)

    def test_refuses_when_the_theme_path_is_a_file(self):
        support.write(self.target, "not a directory")
        with self.assertRaises(install.InstallError):
            install.install(self.tree, self.icons)

    def test_rejects_traversal_in_manifest(self):
        for rel in ("../escape.svg", "/abs.svg", "a//b.svg", "./x.svg", "MANIFEST.evil"):
            tree = self.manual_tree("t-" + str(abs(hash(rel))), [self.file_line(rel, "x")], {})
            with self.assertRaises(install.InstallError, msg=rel):
                install.install(tree, self.icons)
        self.assertFalse(os.path.exists(os.path.join(self.icons, "escape.svg")))

    def test_rejects_link_targets_that_leave_the_directory(self):
        outside = self.path("outside")
        os.makedirs(outside)
        for target in (outside, "../x.svg", "a/b.svg", "/etc/passwd", ".", ".."):
            tree = self.manual_tree("l-" + str(abs(hash(target))), ["L alias.svg %s" % target], {})
            with self.assertRaises(install.InstallError, msg=target):
                install.install(tree, self.icons)
        self.assertEqual(os.listdir(outside), [])

    def test_rejects_entries_below_a_link(self):
        outside = self.path("outside")
        os.makedirs(outside)
        data = "payload"
        tree = self.manual_tree(
            "below",
            ["L esc target.svg", self.file_line("esc/pwn.svg", data)],
            {"esc/pwn.svg": data},
        )
        with self.assertRaises(install.InstallError):
            install.install(tree, self.icons)
        self.assertEqual(os.listdir(outside), [])

    def test_rejects_a_source_that_differs_from_its_digest(self):
        tree = self.manual_tree("digest", [self.file_line("a.svg", "expected")], {"a.svg": "different"})
        with self.assertRaises(install.InstallError):
            install.install(tree, self.icons)
        self.assertFalse(os.path.exists(os.path.join(self.target, "a.svg")))

    def test_rejects_a_symlinked_source_file(self):
        secret = self.path("secret")
        support.write(secret, "secret")
        os.chmod(secret, 0o600)
        tree = self.manual_tree("symsrc", [self.file_line("a.svg", "secret")], {})
        os.symlink(secret, os.path.join(tree, "a.svg"))
        with self.assertRaises(install.InstallError):
            install.install(tree, self.icons)
        self.assertFalse(os.path.exists(os.path.join(self.target, "a.svg")))

    def test_rejects_malformed_manifest_fields(self):
        for line in ("F nothex 1 a.svg", "F %s x a.svg" % ("0" * 64), "F %s 1" % ("0" * 64), "X a b", "L a"):
            tree = self.manual_tree("m-" + str(abs(hash(line))), [line], {})
            with self.assertRaises(install.InstallError, msg=line):
                install.install(tree, self.icons)

    def test_rejects_duplicate_manifest_entries(self):
        line = self.file_line("a.svg", "x")
        tree = self.manual_tree("dup", [line, line], {"a.svg": "x"})
        with self.assertRaises(install.InstallError):
            install.install(tree, self.icons)

    def test_rejects_unsafe_component_names(self):
        tree = self.manual_tree("comp", [self.file_line("a.svg", "x")], {"a.svg": "x"})
        os.rename(os.path.join(tree, "MANIFEST.core"), os.path.join(tree, "MANIFEST.Bad Name"))
        with self.assertRaises(install.InstallError):
            install.install(tree, self.icons)

    def test_does_not_write_through_a_symlinked_subdirectory(self):
        install.install(self.tree, self.icons)
        victim = self.path("victim")
        os.makedirs(victim)
        installed = os.path.join(self.target, "scalable/apps")
        for name in os.listdir(installed):
            os.remove(os.path.join(installed, name))
        os.rmdir(installed)
        os.symlink(victim, installed)
        with self.assertRaises(install.InstallError):
            install.install(self.tree, self.icons)
        self.assertEqual(os.listdir(victim), [])

    def test_uninstall_does_not_delete_through_a_symlinked_subdirectory(self):
        install.install(self.tree, self.icons)
        victim = self.path("victim")
        os.makedirs(victim)
        support.write(os.path.join(victim, "alpha.svg"), support.COLOR_SVG)
        installed = os.path.join(self.target, "scalable/apps")
        for name in os.listdir(installed):
            os.remove(os.path.join(installed, name))
        os.rmdir(installed)
        os.symlink(victim, installed)
        install.uninstall(self.icons)
        self.assertEqual(os.listdir(victim), ["alpha.svg"])


class InterruptionTests(InstallTestCase):
    def test_interrupted_install_can_be_retried_and_removed(self):
        original = install.install_entry
        calls = {"count": 0}

        def failing(target, rel, entry, data):
            calls["count"] += 1
            if calls["count"] == 5:
                raise OSError("simulated interruption")
            return original(target, rel, entry, data)

        install.install_entry = failing
        try:
            with self.assertRaises(OSError):
                install.install(self.tree, self.icons)
        finally:
            install.install_entry = original
        self.assertTrue(os.path.exists(os.path.join(self.target, "PENDING.core")))
        install.install(self.tree, self.icons)
        self.assertEqual(validate.validate(self.target, repo=self.repo), [])
        self.assertFalse(os.path.exists(os.path.join(self.target, "PENDING.core")))

    def test_interrupted_install_can_be_removed_without_a_retry(self):
        original = install.install_entry
        calls = {"count": 0}

        def failing(target, rel, entry, data):
            calls["count"] += 1
            if calls["count"] == 5:
                raise OSError("simulated interruption")
            return original(target, rel, entry, data)

        install.install_entry = failing
        try:
            with self.assertRaises(OSError):
                install.install(self.tree, self.icons)
        finally:
            install.install_entry = original
        install.uninstall(self.icons)
        self.assertFalse(os.path.exists(self.target))


if __name__ == "__main__":
    import unittest

    unittest.main()
