# SPDX-License-Identifier: EUPL-1.2
import codecs
import os
import shutil

import support
import themebuild
import validate


def codes(findings):
    return sorted(set(f.code for f in findings))


class ValidateTests(support.TempCase):
    def setUp(self):
        super().setUp()
        self.repo = self.path("repo")
        support.make_repo(self.repo)
        self.theme = self.path("Resina")
        themebuild.build(self.repo, self.theme, "full")

    def rewrite(self, rel, transform):
        path = os.path.join(self.theme, rel)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(transform(text))

    def rewrite_manifest(self, transform):
        for name in os.listdir(self.theme):
            if name.startswith("MANIFEST."):
                path = os.path.join(self.theme, name)
                with open(path, encoding="utf-8") as handle:
                    lines = handle.read().splitlines()
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("\n".join(transform(lines)) + "\n")

    def expect(self, code, manifests=False, repo=None):
        found = codes(validate.validate(self.theme, manifests=manifests, repo=repo))
        self.assertIn(code, found)

    def test_clean_tree_has_no_findings(self):
        self.assertEqual(validate.validate(self.theme, repo=self.repo), [])

    def test_dangling_alias(self):
        os.remove(os.path.join(self.theme, "scalable/apps/beta.svg"))
        self.expect("link-dangling")

    def test_absolute_alias(self):
        link = os.path.join(self.theme, "scalable/places/game-folder.svg")
        os.remove(link)
        os.symlink("/etc/passwd", link)
        self.expect("link-unsafe")

    def test_alias_chain(self):
        os.symlink("game-folder.svg", os.path.join(self.theme, "scalable/places/second.svg"))
        self.expect("link-chain")

    def test_alias_loop(self):
        os.symlink("loop-b.svg", os.path.join(self.theme, "scalable/places/loop-a.svg"))
        os.symlink("loop-a.svg", os.path.join(self.theme, "scalable/places/loop-b.svg"))
        self.expect("link-chain")

    def test_alias_to_directory(self):
        link = os.path.join(self.theme, "scalable/places/game-folder.svg")
        os.remove(link)
        os.makedirs(os.path.join(self.theme, "scalable/places/dir.svg"))
        os.symlink("dir.svg", link)
        self.expect("link-target-kind")

    def test_retargeted_alias_is_caught_against_the_sources(self):
        link = os.path.join(self.theme, "scalable/places/game-folder.svg")
        os.remove(link)
        os.symlink("folder-github.svg", link)
        self.rewrite_manifest(lambda lines: [l.replace("places/game-folder.svg folder.svg", "places/game-folder.svg folder-github.svg") for l in lines])
        self.assertEqual(validate.validate(self.theme), [])
        self.expect("source-link-target", manifests=True, repo=self.repo)

    def test_removed_overlay_is_caught_against_the_sources(self):
        os.remove(os.path.join(self.theme, "scalable/apps/beta.svg"))
        self.rewrite_manifest(lambda lines: [l for l in lines if not l.endswith(" scalable/apps/beta.svg")])
        self.assertNotIn("source-missing-file", codes(validate.validate(self.theme)))
        self.expect("source-missing-file", manifests=True, repo=self.repo)

    def test_unexpected_file_is_caught_against_the_sources(self):
        shutil.copy(os.path.join(self.theme, "scalable/places/folder.svg"), os.path.join(self.theme, "scalable/places/extra.svg"))
        self.expect("source-unexpected-file", manifests=False, repo=self.repo)

    def test_index_differing_from_the_plan_is_caught(self):
        self.rewrite("index.theme", lambda t: t.replace("Comment=", "Comment=changed "))
        self.expect("index-differs", repo=self.repo)

    def test_missing_index(self):
        os.remove(os.path.join(self.theme, "index.theme"))
        self.expect("index-missing")

    def test_missing_index_section(self):
        self.rewrite("index.theme", lambda t: t.replace("[scalable/status]", "[scalable/other]"))
        self.expect("index-section-missing")

    def test_duplicate_index_section(self):
        self.rewrite("index.theme", lambda t: t + "\n[scalable/status]\nSize=1\n")
        self.expect("index-malformed")

    def test_duplicate_index_key(self):
        self.rewrite("index.theme", lambda t: t.replace("Example=folder", "Example=folder\nExample=computer"))
        self.expect("index-malformed")

    def test_wrong_theme_name(self):
        self.rewrite("index.theme", lambda t: t.replace("Name=Resina", "Name=resina"))
        self.expect("index-name")

    def test_wrong_inherits(self):
        self.rewrite("index.theme", lambda t: t.replace("Inherits=hicolor", "Inherits=Adwaita"))
        self.expect("index-inherits")

    def test_unknown_context(self):
        self.rewrite("index.theme", lambda t: t.replace("Context=Places", "Context=Plaaces"))
        self.expect("index-context")

    def test_context_mismatch(self):
        self.rewrite("index.theme", lambda t: t.replace("[scalable/apps]\nContext=Applications", "[scalable/apps]\nContext=Places"))
        self.expect("index-context-mismatch")

    def test_range_violation(self):
        self.rewrite("index.theme", lambda t: t.replace("MaxSize=512", "MaxSize=4", 1))
        self.expect("index-range")

    def test_wrong_nominal_size(self):
        self.rewrite("index.theme", lambda t: t.replace("Size=128", "Size=64", 1))
        self.expect("index-range")

    def test_fixed_type_on_scalable_directory(self):
        self.rewrite("index.theme", lambda t: t.replace("Type=Scalable", "Type=Fixed", 1))
        self.expect("index-type")

    def test_unlisted_directory(self):
        os.makedirs(os.path.join(self.theme, "scalable/extra"))
        self.expect("directory-unlisted")

    def test_animation_sheet_has_the_frame_grid_size(self):
        self.rewrite("animations/24/process-working.svg", lambda t: t.replace('width="96"', 'width="97"'))
        self.expect("svg-sheet-size")

    def test_animation_sheet_viewbox(self):
        self.rewrite("animations/24/process-working.svg", lambda t: t.replace('viewBox="0 0 96 72"', 'viewBox="0 0 96 73"'))
        self.expect("svg-viewbox")

    def test_animation_sheet_colour_is_fixed(self):
        self.rewrite("animations/24/process-working.svg", lambda t: t.replace('stroke="#868686"', 'stroke="#ff0000"', 1))
        self.expect("svg-fixed-colour")

    def test_animation_directory_must_be_fixed(self):
        self.rewrite("index.theme", lambda t: t.replace("[animations/24]" + chr(10) + "Context=Animations" + chr(10) + "Size=24" + chr(10) + "Type=Fixed", "[animations/24]" + chr(10) + "Context=Animations" + chr(10) + "Size=24" + chr(10) + "Type=Scalable"))
        self.expect("index-animation")

    def test_wrong_viewbox(self):
        self.rewrite("scalable/places/folder.svg", lambda t: t.replace('viewBox="0 0 128 128"', 'viewBox="0 0 64 64"', 1))
        self.expect("svg-viewbox")

    def test_empty_svg(self):
        support.write(os.path.join(self.theme, "scalable/places/folder.svg"), '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"></svg>')
        self.expect("svg-empty")

    def test_broken_xml(self):
        support.write(os.path.join(self.theme, "scalable/places/folder.svg"), "<svg")
        self.expect("svg-parse")

    def test_deeply_nested_xml_does_not_crash_the_validator(self):
        text = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">' + "<g>" * 20000 + "</g>" * 20000 + "</svg>"
        support.write(os.path.join(self.theme, "scalable/places/folder.svg"), text)
        self.assertIsInstance(validate.validate(self.theme, manifests=False), list)

    def test_oversized_svg(self):
        support.write(os.path.join(self.theme, "scalable/places/folder.svg"), "<svg>" + " " * (2 << 20) + "</svg>")
        self.expect("svg-too-large")

    def test_doctype_and_comments(self):
        for text in ('<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>', '<svg xmlns="http://www.w3.org/2000/svg"><!-- x --></svg>'):
            support.write(os.path.join(self.theme, "scalable/places/folder.svg"), text)
            self.expect("svg-doctype")

    def test_non_utf8_encodings_are_rejected(self):
        body = '<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"/>'
        for data in (body.encode("utf-16"), codecs.BOM_UTF8 + body.encode("utf-8")):
            with open(os.path.join(self.theme, "scalable/places/folder.svg"), "wb") as handle:
                handle.write(data)
            self.expect("svg-encoding")

    def add_to_places(self, extra):
        self.rewrite("scalable/places/folder.svg", lambda t: t.replace("</svg>", extra + "</svg>"))

    def test_text_forbidden(self):
        self.add_to_places('<text x="1" y="1">PDF</text>')
        self.expect("svg-forbidden-element")

    def test_metadata_title_and_desc_forbidden(self):
        for index, element in enumerate(("<metadata>x</metadata>", "<title>x</title>", "<desc>x</desc>")):
            fresh = self.path("fresh-%d" % index)
            themebuild.build(self.repo, fresh, "full")
            path = os.path.join(fresh, "scalable/places/folder.svg")
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text.replace("</svg>", element + "</svg>"))
            self.assertIn("svg-forbidden-element", codes(validate.validate(fresh, manifests=False)))

    def test_foreign_namespace_element_forbidden(self):
        self.add_to_places('<x:block xmlns:x="urn:example:block">AAAA</x:block>')
        self.expect("svg-foreign-element")

    def test_namespaced_attribute_forbidden(self):
        self.rewrite("scalable/places/folder.svg", lambda t: t.replace("<g", '<g xmlns:x="urn:x" x:a="1"', 1))
        self.expect("svg-namespaced-attribute")

    def test_unknown_data_attribute_forbidden(self):
        self.rewrite("scalable/places/folder.svg", lambda t: t.replace("<svg ", '<svg data-origin="x" ', 1))
        self.expect("svg-data-attribute")

    def test_documented_data_attribute_allowed(self):
        self.rewrite("scalable/places/folder.svg", lambda t: t.replace("<svg ", '<svg data-dynamic="clock" ', 1))
        self.assertNotIn("svg-data-attribute", codes(validate.validate(self.theme)))

    def test_style_and_event_attributes_forbidden(self):
        self.rewrite("scalable/places/folder.svg", lambda t: t.replace("<svg ", '<svg style="fill:red" onload="x()" ', 1))
        found = codes(validate.validate(self.theme))
        self.assertIn("svg-forbidden-attribute", found)
        self.assertIn("svg-event-attribute", found)

    def test_dangling_reference(self):
        self.add_to_places('<path d="M0 0H1V1Z" fill="url(#missing)"/>')
        self.expect("svg-dangling-reference")

    def test_morphology_forbidden(self):
        self.rewrite(
            "scalable/places/folder.svg",
            lambda t: t.replace("</svg>", '<defs><filter id="x"><feMorphology operator="dilate" radius="1"/></filter></defs></svg>', 1),
        )
        self.expect("svg-forbidden-primitive")

    def test_clip_path_forbidden(self):
        self.add_to_places('<clipPath id="q"><path d="M0 0H1V1Z"/></clipPath>')
        self.expect("svg-clippath-outside-defs")

    def test_external_reference(self):
        self.add_to_places('<g href="https://example.invalid/x.svg#a"/>')
        self.expect("svg-external-reference")

    def test_stroke_in_symbolic_forbidden(self):
        self.rewrite("symbolic/actions/go-next-symbolic.svg", lambda t: t.replace("<path", '<path stroke="currentColor"', 1))
        self.expect("svg-stroke-in-symbolic")

    def test_fixed_colour_in_symbolic_forbidden(self):
        self.rewrite("symbolic/actions/go-next-symbolic.svg", lambda t: t.replace('fill="currentColor"', 'fill="#ff0000"', 1))
        self.expect("svg-fixed-colour")

    def test_symbolic_fixed_colour_through_color_attribute(self):
        self.rewrite("symbolic/actions/go-next-symbolic.svg", lambda t: t.replace("<path", '<path color="#ff0000"', 1))
        self.expect("svg-fixed-colour")

    def test_symbolic_fixed_colour_through_stop_color(self):
        self.rewrite("symbolic/actions/go-next-symbolic.svg", lambda t: t.replace("<path", '<path stop-color="#ff0000"', 1))
        self.expect("svg-fixed-colour")

    def test_overlay_link_to_core_target_is_accepted_only_with_the_sources(self):
        support.write(os.path.join(self.repo, "aliases/color.tsv"), "org.example.Beta" + chr(9) + "apps/alpha" + chr(9) + "thirdparty" + chr(10))
        overlay = self.path("overlay")
        themebuild.build(self.repo, overlay, "thirdparty")
        self.assertEqual(validate.validate(overlay, repo=self.repo, index=False), [])
        self.assertIn("link-dangling", {f.code for f in validate.validate(overlay, index=False)})

    def test_root_symlink_is_reported(self):
        os.remove(os.path.join(self.theme, "NOTICE"))
        os.symlink("/etc/passwd", os.path.join(self.theme, "NOTICE"))
        self.expect("root-not-regular")

    def test_fifo_named_svg_is_reported_without_blocking(self):
        path = os.path.join(self.theme, "scalable/places/pipe.svg")
        os.mkfifo(path)
        self.expect("not-regular")

    def test_case_collision(self):
        shutil.copy(os.path.join(self.theme, "scalable/places/folder.svg"), os.path.join(self.theme, "scalable/places/Folder.svg"))
        self.expect("case-collision")

    def test_stray_file(self):
        support.write(os.path.join(self.theme, "scalable/places/readme.txt"), "x")
        self.expect("unexpected-file")

    def test_stray_root_file(self):
        support.write(os.path.join(self.theme, "stray.bin"), "x")
        self.expect("unexpected-file")

    def test_file_in_unknown_directory(self):
        support.write(os.path.join(self.theme, "other/a.svg"), "<svg/>")
        self.expect("unexpected-file")

    def test_manifest_mismatch(self):
        self.rewrite("scalable/places/folder.svg", lambda t: t + "\n")
        self.expect("manifest-mismatch", manifests=True)

    def test_manifest_unlisted(self):
        shutil.copy(os.path.join(self.theme, "scalable/places/folder.svg"), os.path.join(self.theme, "scalable/places/extra.svg"))
        self.expect("manifest-unlisted", manifests=True)

    def test_manifest_missing(self):
        for name in os.listdir(self.theme):
            if name.startswith("MANIFEST."):
                os.remove(os.path.join(self.theme, name))
        self.expect("manifest-missing", manifests=True)

    def test_manifest_with_bad_size_is_a_finding(self):
        self.rewrite_manifest(lambda lines: lines + ["F %s notanumber x.svg" % ("0" * 64)])
        self.expect("manifest-malformed", manifests=True)

    def test_manifest_link_mismatch(self):
        self.rewrite_manifest(lambda lines: [l.replace("game-folder.svg folder.svg", "game-folder.svg other.svg") for l in lines])
        self.expect("manifest-link-mismatch", manifests=True)

    def test_command_line_reports_findings(self):
        self.assertEqual(validate.main([self.theme, "--repo", self.repo]), 0)
        os.remove(os.path.join(self.theme, "index.theme"))
        self.assertEqual(validate.main([self.theme]), 1)

    def test_overlay_tree_validates_without_index(self):
        overlay = self.path("overlay")
        themebuild.build(self.repo, overlay, "thirdparty")
        self.assertEqual(validate.validate(overlay, index=False, repo=self.repo), [])


if __name__ == "__main__":
    import unittest

    unittest.main()
