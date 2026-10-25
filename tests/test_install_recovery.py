# SPDX-License-Identifier: EUPL-1.2
import os
import shutil
import signal

import support
import install
import themebuild
import validate
from test_install import InstallTestCase


class RecoveryTests(InstallTestCase):
    def edit(self, rel):
        path = os.path.join(self.target, rel)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("<!-- edited -->")
        return path

    def test_interrupted_uninstall_keeps_edited_files_tracked(self):
        install.install(self.tree, self.icons)
        rel = "scalable/status/image-missing.svg"
        path = self.edit(rel)
        original = install.Theme.lstat

        def failing(theme, name):
            if name.startswith(install.PENDING_PREFIX):
                raise OSError("simulated interruption")
            return original(theme, name)

        install.Theme.lstat = failing
        try:
            with self.assertRaises(OSError):
                install.uninstall(self.icons)
        finally:
            install.Theme.lstat = original
        with open(os.path.join(self.target, "MANIFEST.core"), encoding="utf-8") as handle:
            self.assertIn(rel, handle.read())
        edited = support.sha256_file(path)
        report = install.install(self.tree, self.icons)
        self.assertEqual(report["preserved"], [rel])
        self.assertEqual(support.sha256_file(path), edited)

    def test_unreadable_manifest_needs_force_and_then_recovers(self):
        install.install(self.tree, self.icons)
        manifest = os.path.join(self.target, "MANIFEST.core")
        with open(manifest, "r+", encoding="utf-8") as handle:
            handle.truncate(20)
        with self.assertRaises(install.InstallError):
            install.uninstall(self.icons)
        with self.assertRaises(install.InstallError):
            install.install(self.tree, self.icons)
        install.install(self.tree, self.icons, force=True)
        self.assertEqual(validate.validate(self.target, repo=self.repo), [])

    def test_unreadable_manifest_is_reported_by_a_forced_uninstall(self):
        install.install(self.tree, self.icons)
        with open(os.path.join(self.target, "MANIFEST.thirdparty"), "w", encoding="utf-8") as handle:
            handle.write("garbage" + chr(10))
        report = install.uninstall(self.icons, force=True)
        self.assertEqual(report["unreadable"], ["MANIFEST.thirdparty"])
        self.assertFalse(os.path.exists(os.path.join(self.target, "MANIFEST.thirdparty")))

    def test_a_path_can_move_between_components_in_an_upgrade(self):
        install.install(self.tree, self.icons)
        classes = dict(support.COLOR_ICONS)
        classes["apps/beta"] = "core"
        support.write(os.path.join(self.repo, "names/color-classes.tsv"), "".join("%s\t%s\n" % item for item in sorted(classes.items())))
        newtree = self.path("tree2")
        themebuild.build(self.repo, newtree, "full")
        install.install(newtree, self.icons)
        with open(os.path.join(self.target, "MANIFEST.core"), encoding="utf-8") as handle:
            self.assertIn("scalable/apps/beta.svg", handle.read())
        with open(os.path.join(self.target, "MANIFEST.thirdparty"), encoding="utf-8") as handle:
            self.assertNotIn("scalable/apps/beta.svg", handle.read())
        self.assertTrue(os.path.exists(os.path.join(self.target, "scalable/apps/beta.svg")))
        self.assertEqual(validate.validate(self.target, repo=self.repo), [])

    def test_editor_backups_of_manifests_are_not_components(self):
        install.install(self.tree, self.icons)
        shutil.copyfile(os.path.join(self.target, "MANIFEST.core"), os.path.join(self.target, "MANIFEST.core~"))
        install.install(self.tree, self.icons)
        report = install.uninstall(self.icons)
        self.assertEqual(report["preserved"], [])

    def test_fifo_at_a_tracked_path_does_not_hang(self):
        install.install(self.tree, self.icons)
        path = os.path.join(self.target, "scalable/status/image-missing.svg")
        os.remove(path)
        try:
            os.mkfifo(path)
        except OSError:
            self.skipTest("this filesystem cannot create a FIFO")
        signal.alarm(20)
        try:
            report = install.install(self.tree, self.icons)
            self.assertEqual(report["preserved"], ["scalable/status/image-missing.svg"])
            report = install.uninstall(self.icons)
            self.assertIn("scalable/status/image-missing.svg", report["preserved"])
        finally:
            signal.alarm(0)

    def test_manifests_are_flushed_when_durability_is_on(self):
        calls = []
        real = os.fsync
        install.DURABLE = True
        os.fsync = lambda descriptor: calls.append(descriptor) or real(descriptor)
        try:
            install.install(self.tree, self.icons)
        finally:
            os.fsync = real
            install.DURABLE = False
        self.assertGreaterEqual(len(calls), 4)

    def test_reinstall_after_uninstall_with_an_icon_cache_present(self):
        install.install(self.tree, self.icons)
        cache = os.path.join(self.target, install.CACHE)
        support.write(cache, "cache")
        install.uninstall(self.icons)
        self.assertFalse(os.path.exists(self.target))
        install.install(self.tree, self.icons)
        support.write(cache, "stale")
        install.install(self.tree, self.icons)
        self.assertFalse(os.path.exists(cache))

    def test_uninstall_of_one_component_keeps_a_file_the_other_also_lists(self):
        install.install(self.tree, self.icons)
        with open(os.path.join(self.target, "MANIFEST.core"), encoding="utf-8") as handle:
            core = handle.read().splitlines()
        shared = [l for l in core if l.endswith(" scalable/status/image-missing.svg")][0]
        with open(os.path.join(self.target, "MANIFEST.thirdparty"), "a", encoding="utf-8") as handle:
            handle.write(shared + chr(10))
        install.uninstall(self.icons, ["thirdparty"])
        self.assertTrue(os.path.exists(os.path.join(self.target, "scalable/status/image-missing.svg")))

    def test_relative_data_home_is_ignored(self):
        saved = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = "relative/share"
        try:
            self.assertTrue(os.path.isabs(install.default_icons_dir()))
        finally:
            if saved is None:
                del os.environ["XDG_DATA_HOME"]
            else:
                os.environ["XDG_DATA_HOME"] = saved

    def test_the_theme_directory_is_locked_while_it_is_open(self):
        import fcntl

        os.makedirs(self.icons, exist_ok=True)
        theme = install.open_theme(self.icons, create=True)
        try:
            other = os.open(self.target, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(other)
        finally:
            theme.close()

    def test_install_and_uninstall_racing_each_other_both_finish(self):
        import threading

        errors = []

        def installer():
            for _ in range(15):
                try:
                    install.install(self.tree, self.icons)
                except Exception as error:
                    errors.append(error)

        def remover():
            for _ in range(15):
                try:
                    install.uninstall(self.icons)
                except Exception as error:
                    errors.append(error)

        threads = [threading.Thread(target=installer), threading.Thread(target=remover)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        install.install(self.tree, self.icons)
        self.assertEqual(validate.validate(self.target, repo=self.repo), [])

    def test_the_core_set_is_not_removed_from_under_the_overlay(self):
        install.install(self.tree, self.icons)
        before = support.tree_digest(self.target)
        with self.assertRaises(install.InstallError):
            install.uninstall(self.icons, ["core"])
        self.assertEqual(support.tree_digest(self.target), before)
        install.uninstall(self.icons, ["core"], force=True)
        self.assertFalse(os.path.exists(os.path.join(self.target, "MANIFEST.core")))

    def test_an_unreadable_overlay_manifest_stops_uninstall_before_anything_is_removed(self):
        install.install(self.tree, self.icons)
        with open(os.path.join(self.target, "MANIFEST.thirdparty"), "w", encoding="utf-8") as handle:
            handle.write("garbage" + chr(10))
        before = support.tree_digest(self.target)
        with self.assertRaises(install.InstallError):
            install.uninstall(self.icons)
        self.assertEqual(support.tree_digest(self.target), before)

    def test_force_reports_the_files_it_overwrote(self):
        install.install(self.tree, self.icons)
        os.remove(os.path.join(self.target, "MANIFEST.core"))
        os.remove(os.path.join(self.target, "MANIFEST.thirdparty"))
        path = os.path.join(self.target, "scalable/status/image-missing.svg")
        support.write(path, "something else")
        report = install.install(self.tree, self.icons, force=True)
        self.assertIn("scalable/status/image-missing.svg", report["overwritten"])

    def test_crash_leftovers_are_removed_by_uninstall(self):
        install.install(self.tree, self.icons)
        leftover = os.path.join(self.target, "scalable/apps", install.TEMPORARY + "123-alpha.svg")
        support.write(leftover, "partial")
        install.uninstall(self.icons)
        self.assertFalse(os.path.exists(self.target))


if __name__ == "__main__":
    import unittest

    unittest.main()
