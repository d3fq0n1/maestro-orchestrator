"""Unit tests for the bundle manifest subsystem."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from maestro.bundles.manifest import (
    Manifest,
    compute_bundle_id,
    generate_manifest,
    generate_catalog_manifests,
    load_manifest,
    regenerate,
    save_manifest,
    _canonicalise_bundle_bytes,
    _extract_capabilities,
    _parse_front_matter,
)


SAMPLE_SKILL = """---
name: test-skill
description: "A test skill for Python that builds documents with the anthropic SDK."
license: Complete terms in LICENSE.txt
---

# Test Skill

This skill helps you build .docx and .pdf documents using python-docx
and the anthropic SDK. Use it when the user asks to create a word document
or generate an API-driven report.
"""


class TestCanonicalisation(unittest.TestCase):

    def test_canonicalise_line_endings(self):
        a = _canonicalise_bundle_bytes("hello\r\nworld\r\n")
        b = _canonicalise_bundle_bytes("hello\nworld\n")
        self.assertEqual(a, b)

    def test_canonicalise_trailing_whitespace(self):
        a = _canonicalise_bundle_bytes("hello   \nworld\t\n")
        b = _canonicalise_bundle_bytes("hello\nworld\n")
        self.assertEqual(a, b)

    def test_canonicalise_trailing_blank_lines(self):
        a = _canonicalise_bundle_bytes("hello\nworld\n\n\n\n")
        b = _canonicalise_bundle_bytes("hello\nworld\n")
        self.assertEqual(a, b)

    def test_bundle_id_stable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "SKILL.md"
            p.write_text(SAMPLE_SKILL)
            id1 = compute_bundle_id(p)
            # Whitespace-only change should not change id
            p.write_text(SAMPLE_SKILL.replace("\n", "\r\n"))
            id2 = compute_bundle_id(p)
            self.assertEqual(id1, id2)

    def test_bundle_id_different_for_different_content(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.md"
            p2 = Path(td) / "b.md"
            p1.write_text(SAMPLE_SKILL)
            p2.write_text(SAMPLE_SKILL + "extra content")
            self.assertNotEqual(compute_bundle_id(p1), compute_bundle_id(p2))


class TestFrontMatterParser(unittest.TestCase):

    def test_parses_basic(self):
        fm, body = _parse_front_matter(SAMPLE_SKILL)
        self.assertEqual(fm["name"], "test-skill")
        self.assertIn("anthropic SDK", fm["description"])
        self.assertIn("# Test Skill", body)

    def test_strips_quotes(self):
        text = '---\nname: x\ndescription: "with quotes"\n---\nbody'
        fm, _ = _parse_front_matter(text)
        self.assertEqual(fm["description"], "with quotes")

    def test_handles_no_front_matter(self):
        fm, body = _parse_front_matter("just body")
        self.assertEqual(fm, {})
        self.assertEqual(body, "just body")


class TestCapabilityExtraction(unittest.TestCase):

    def test_detects_python_and_docx(self):
        caps = _extract_capabilities(
            "docx-helper",
            "Create word documents with python-docx",
            "Use python and the docx library to build .docx files.",
        )
        self.assertIn("python", caps["language"])
        self.assertIn("python-docx", caps["framework"])
        self.assertIn("documents", caps["domain"])

    def test_empty_for_noise(self):
        caps = _extract_capabilities("x", "", "")
        self.assertEqual(caps, {})


class TestGenerateManifest(unittest.TestCase):

    def test_generates_from_skill_md(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = Path(td) / "test-skill"
            bundle.mkdir()
            (bundle / "SKILL.md").write_text(SAMPLE_SKILL)

            m = generate_manifest(bundle)

            self.assertEqual(m.name, "test-skill")
            self.assertEqual(len(m.bundle_id), 64)  # sha256 hex
            self.assertTrue(m.abstract)
            self.assertIn("python", m.capabilities.get("language", []))
            self.assertEqual(m.dependencies, [])
            self.assertEqual(m.conflicts, [])
            self.assertIsNone(m.signature)
            self.assertEqual(m.path, str(bundle))

    def test_missing_skill_md_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                generate_manifest(Path(td))


class TestCatalogGeneration(unittest.TestCase):

    def test_generates_multiple(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ("alpha", "beta", "gamma"):
                d = root / name
                d.mkdir()
                (d / "SKILL.md").write_text(
                    SAMPLE_SKILL.replace("test-skill", name)
                )

            manifests = generate_catalog_manifests(root)
            self.assertEqual(len(manifests), 3)
            names = sorted(m.name for m in manifests)
            self.assertEqual(names, ["alpha", "beta", "gamma"])

    def test_skips_dirs_without_skill_md(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            good = root / "good"
            good.mkdir()
            (good / "SKILL.md").write_text(SAMPLE_SKILL)
            bad = root / "bad"
            bad.mkdir()
            (bad / "README.md").write_text("no skill here")

            manifests = generate_catalog_manifests(root)
            self.assertEqual(len(manifests), 1)
            self.assertEqual(manifests[0].name, "test-skill")


class TestRoundTrip(unittest.TestCase):

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = Path(td) / "b"
            bundle.mkdir()
            (bundle / "SKILL.md").write_text(SAMPLE_SKILL)
            m = generate_manifest(bundle)

            manifest_dir = Path(td) / "manifests"
            save_manifest(m, manifest_dir)

            loaded = load_manifest(m.bundle_id, manifest_dir)
            self.assertEqual(loaded.bundle_id, m.bundle_id)
            self.assertEqual(loaded.name, m.name)
            self.assertEqual(loaded.capabilities, m.capabilities)

    def test_regenerate_prunes_stale(self):
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td) / "corpus"
            corpus.mkdir()
            cache = Path(td) / "cache"

            # Seed with 2 skills, regenerate
            for name in ("a", "b"):
                d = corpus / name
                d.mkdir()
                (d / "SKILL.md").write_text(SAMPLE_SKILL.replace("test-skill", name))
            m1 = regenerate(skills_root=corpus, manifest_dir=cache)
            self.assertEqual(len(m1), 2)
            self.assertEqual(len(list(cache.glob("*.json"))), 2)

            # Remove one, regenerate with prune
            (corpus / "b" / "SKILL.md").unlink()
            (corpus / "b").rmdir()
            m2 = regenerate(skills_root=corpus, manifest_dir=cache)
            self.assertEqual(len(m2), 1)
            self.assertEqual(len(list(cache.glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
