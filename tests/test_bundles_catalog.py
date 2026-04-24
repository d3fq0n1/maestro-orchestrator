"""Unit tests for the catalog + prefilter."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from maestro.bundles.catalog import Catalog, CatalogQuery, extract_task_tags
from maestro.bundles.manifest import (
    generate_catalog_manifests,
    regenerate,
)


SAMPLE_PY_DOCX = """---
name: docx-writer
description: "Create word documents in python with python-docx."
---
Use python-docx to build .docx files.
"""

SAMPLE_PY_XLSX = """---
name: xlsx-writer
description: "Create spreadsheets in python with openpyxl."
---
Use openpyxl to build .xlsx files.
"""

SAMPLE_TS_WEB = """---
name: web-builder
description: "Build a typescript web app using React and playwright testing."
---
Use typescript, react, and playwright.
"""


def _build_corpus(root: Path, skills: dict[str, str]) -> None:
    for name, body in skills.items():
        d = root / name
        d.mkdir()
        (d / "SKILL.md").write_text(body)


class TestTaskTagExtraction(unittest.TestCase):

    def test_python_docx_task(self):
        tags = extract_task_tags("Write a python script to build a .docx report")
        self.assertIn("python", tags.get("language", []))
        self.assertIn("documents", tags.get("domain", []))

    def test_empty_for_vague(self):
        tags = extract_task_tags("Help me.")
        self.assertEqual(tags, {})


class TestCatalog(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / "corpus"
        root.mkdir()
        _build_corpus(root, {
            "docx-writer": SAMPLE_PY_DOCX,
            "xlsx-writer": SAMPLE_PY_XLSX,
            "web-builder": SAMPLE_TS_WEB,
        })
        self.catalog = Catalog.from_skills_root(root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_len_and_iter(self):
        self.assertEqual(len(self.catalog), 3)
        names = sorted(m.name for m in self.catalog)
        self.assertEqual(names, ["docx-writer", "web-builder", "xlsx-writer"])

    def test_get_by_id(self):
        first = self.catalog.all()[0]
        self.assertIs(self.catalog.get(first.bundle_id), first)
        self.assertIsNone(self.catalog.get("bogus"))

    def test_snapshot_hash_stable(self):
        h1 = self.catalog.snapshot_hash()
        h2 = self.catalog.snapshot_hash()
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_prefilter_narrows_on_tag_match(self):
        q = CatalogQuery.from_text("python .docx report")
        # python matches docx-writer + xlsx-writer; documents narrows to docx
        narrowed = self.catalog.prefilter(q)
        names = [m.name for m in narrowed]
        self.assertIn("docx-writer", names)
        # The web-builder is TypeScript — no python tag, so it shouldn't
        # rank above the python bundles. With our permissive prefilter,
        # when the query has python+documents tags the web bundle may be
        # excluded entirely.
        self.assertNotIn("web-builder", names)

    def test_prefilter_falls_back_when_no_match(self):
        q = CatalogQuery.from_text("help with lorem ipsum")
        result = self.catalog.prefilter(q)
        # No task tags => permissive pass-through
        self.assertEqual(len(result), 3)

    def test_prefilter_respects_max_candidates(self):
        q = CatalogQuery(text="", tags={}, max_candidates=1)
        result = self.catalog.prefilter(q)
        self.assertEqual(len(result), 1)

    def test_from_disk_reads_cache(self):
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td) / "corpus"
            corpus.mkdir()
            _build_corpus(corpus, {"docx-writer": SAMPLE_PY_DOCX})
            cache = Path(td) / "cache"
            regenerate(skills_root=corpus, manifest_dir=cache)

            loaded = Catalog.from_disk(manifest_dir=cache)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded.all()[0].name, "docx-writer")

    def test_prefilter_ranks_by_match_count(self):
        # A query that hits multiple axes should rank higher-coverage bundles first.
        q = CatalogQuery.from_text("python build a .docx document with python-docx")
        result = self.catalog.prefilter(q)
        # docx-writer matches {python, documents, python-docx} — should rank first.
        self.assertEqual(result[0].name, "docx-writer")


if __name__ == "__main__":
    unittest.main()
