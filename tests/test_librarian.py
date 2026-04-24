"""Unit tests for LibrarianAgent + run_librarian_session.

These tests use a deterministic fake provider (no network calls) so the
selection, dissenter, consensus, and R2-metadata code paths can be
exercised without API keys.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from maestro.agents.base import Agent
from maestro.bundles.catalog import Catalog
from maestro.bundles.manifest import regenerate
from maestro.r2 import R2Engine
from maestro.specialists.librarian import (
    LibrarianAgent,
    LibrarianSelection,
    _extract_json_object,
    _majority_consensus,
    _parse_selection,
    _rotating_dissenter,
    run_librarian_session,
)


SAMPLE_DOCX = """---
name: docx
description: "Build word documents in python with python-docx."
---
Build .docx files.
"""

SAMPLE_PPTX = """---
name: pptx
description: "Build powerpoint presentations in python with python-pptx."
---
Build .pptx files.
"""

SAMPLE_BRAND = """---
name: brand-guidelines
description: "Apply brand guidelines to documents and presentations."
---
Apply brand rules.
"""


def _make_corpus(root: Path) -> None:
    for name, body in [
        ("docx", SAMPLE_DOCX),
        ("pptx", SAMPLE_PPTX),
        ("brand-guidelines", SAMPLE_BRAND),
    ]:
        d = root / name
        d.mkdir()
        (d / "SKILL.md").write_text(body)


class FakeProvider(Agent):
    """Deterministic provider that returns a canned JSON selection."""

    def __init__(self, name: str, bundles: list[str], rationale: str = ""):
        self.name = name
        self.model = "fake"
        self._bundles = bundles
        self._rationale = rationale

    async def fetch(self, prompt: str) -> str:
        return json.dumps({
            "bundles": [
                {"bundle_id": b, "scope": "test", "confidence": 0.9}
                for b in self._bundles
            ],
            "rationale": self._rationale,
        })


class FakeDissenterProvider(Agent):
    """Provider that returns different output when it sees dissenter framing."""

    def __init__(self, name: str, normal: list[str], dissent: list[str]):
        self.name = name
        self.model = "fake"
        self._normal = normal
        self._dissent = dissent

    async def fetch(self, prompt: str) -> str:
        bundles = self._dissent if "DISSENTER MODE" in prompt else self._normal
        return json.dumps({
            "bundles": [{"bundle_id": b, "confidence": 0.8} for b in bundles],
        })


class TestJsonExtractor(unittest.TestCase):

    def test_extracts_from_code_fence(self):
        text = 'Here you go:\n```json\n{"bundles": []}\n```'
        extracted = _extract_json_object(text)
        self.assertEqual(json.loads(extracted), {"bundles": []})

    def test_extracts_outermost_object(self):
        text = 'noise {"a": {"b": 1}} trailing'
        extracted = _extract_json_object(text)
        self.assertEqual(json.loads(extracted), {"a": {"b": 1}})

    def test_returns_none_on_no_object(self):
        self.assertIsNone(_extract_json_object("just prose"))


class TestSelectionParser(unittest.TestCase):

    def setUp(self):
        self.known = {"a" * 64, "b" * 64}

    def test_parses_valid_reply(self):
        raw = json.dumps({
            "bundles": [
                {"bundle_id": "a" * 64, "scope": "core", "confidence": 0.7},
                {"bundle_id": "b" * 64, "confidence": 0.9},
            ],
            "rationale": "chose both",
        })
        sel = _parse_selection(raw, "selector", self.known)
        self.assertEqual(sel.role, "selector")
        self.assertEqual(set(sel.bundle_ids), self.known)
        self.assertEqual(sel.scopes["a" * 64], "core")
        self.assertAlmostEqual(sel.confidences["b" * 64], 0.9)
        self.assertEqual(sel.rationale, "chose both")

    def test_drops_unknown_ids(self):
        raw = json.dumps({"bundles": [{"bundle_id": "c" * 64}]})
        sel = _parse_selection(raw, "selector", self.known)
        self.assertEqual(sel.bundle_ids, [])

    def test_malformed_json_is_empty(self):
        sel = _parse_selection("not json", "selector", self.known)
        self.assertEqual(sel.bundle_ids, [])
        self.assertEqual(sel.rationale, "")

    def test_clamps_confidence(self):
        raw = json.dumps({"bundles": [{"bundle_id": "a" * 64, "confidence": 5.0}]})
        sel = _parse_selection(raw, "selector", self.known)
        self.assertLessEqual(sel.confidences["a" * 64], 1.0)

    def test_canonical_json_stable(self):
        s1 = LibrarianSelection(
            role="selector",
            bundle_ids=["b" * 64, "a" * 64],
            confidences={"a" * 64: 0.7, "b" * 64: 0.9},
        )
        s2 = LibrarianSelection(
            role="selector",
            bundle_ids=["a" * 64, "b" * 64],
            confidences={"b" * 64: 0.9, "a" * 64: 0.7},
        )
        self.assertEqual(s1.to_canonical_json(), s2.to_canonical_json())


class TestMajorityConsensus(unittest.TestCase):

    def _sel(self, bundle_ids):
        return LibrarianSelection(role="selector", bundle_ids=bundle_ids)

    def test_bundle_with_majority_wins(self):
        sels = [self._sel(["a", "b"]), self._sel(["a", "c"]), self._sel(["a", "d"])]
        chosen, confs = _majority_consensus(sels)
        self.assertIn("a", chosen)
        self.assertNotIn("b", chosen)
        self.assertEqual(confs["a"], 1.0)

    def test_excludes_dissenter_from_vote(self):
        sels = [
            self._sel(["a"]),
            self._sel(["a"]),
            LibrarianSelection(role="dissenter", bundle_ids=["z"]),
        ]
        chosen, _ = _majority_consensus(sels)
        self.assertEqual(chosen, ["a"])

    def test_empty_selections(self):
        chosen, confs = _majority_consensus([])
        self.assertEqual(chosen, [])
        self.assertEqual(confs, {})


class TestRotatingDissenter(unittest.TestCase):

    def test_rotates_by_modulo(self):
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td) / "c"
            corpus.mkdir()
            _make_corpus(corpus)
            cat = Catalog.from_skills_root(corpus)
            council = [
                LibrarianAgent(FakeProvider(f"p{i}", []), cat, name=f"L{i}")
                for i in range(3)
            ]
            for i in range(6):
                self.assertIs(_rotating_dissenter(council, i), council[i % 3])


class TestLibrarianSession(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / "corpus"
        root.mkdir()
        _make_corpus(root)
        self.catalog = Catalog.from_skills_root(root)
        ids = {m.name: m.bundle_id for m in self.catalog}
        self.docx = ids["docx"]
        self.pptx = ids["pptx"]
        self.brand = ids["brand-guidelines"]
        self.ledger_dir = Path(self.tmp.name) / "r2"
        self.r2 = R2Engine(ledger_dir=str(self.ledger_dir))

    def tearDown(self):
        self.tmp.cleanup()

    def test_consensus_picks_majority(self):
        council = [
            LibrarianAgent(FakeProvider("A", [self.docx, self.brand]), self.catalog, name="A"),
            LibrarianAgent(FakeProvider("B", [self.docx, self.brand]), self.catalog, name="B"),
            LibrarianAgent(FakeProvider("C", [self.docx, self.pptx]), self.catalog, name="C"),
        ]
        result = asyncio.run(run_librarian_session(
            task="python script to build a .docx with brand guidelines",
            council=council,
            catalog=self.catalog,
            session_count=0,
        ))
        self.assertIn(self.docx, result.consensus_bundle_ids)
        self.assertIn(self.brand, result.consensus_bundle_ids)
        self.assertNotIn(self.pptx, result.consensus_bundle_ids)

    def test_dissenter_selection_recorded_separately(self):
        council = [
            LibrarianAgent(
                FakeDissenterProvider("A", [self.docx], [self.pptx]),
                self.catalog, name="A",
            ),
            LibrarianAgent(FakeProvider("B", [self.docx]), self.catalog, name="B"),
            LibrarianAgent(FakeProvider("C", [self.docx]), self.catalog, name="C"),
        ]
        result = asyncio.run(run_librarian_session(
            task="build a .docx",
            council=council,
            catalog=self.catalog,
            session_count=0,  # dissenter = council[0] = A
        ))
        self.assertEqual(result.dissenter, "A")
        # Majority (from selector pass) should still be docx
        self.assertIn(self.docx, result.consensus_bundle_ids)
        # Dissenter selection should include pptx and NOT bubble up into
        # the consensus vote
        self.assertIn(self.pptx, result.dissenter_bundle_ids)
        self.assertNotIn(self.pptx, result.consensus_bundle_ids)

    def test_r2_metadata_populated(self):
        council = [
            LibrarianAgent(FakeProvider("A", [self.docx]), self.catalog, name="A"),
            LibrarianAgent(FakeProvider("B", [self.docx]), self.catalog, name="B"),
            LibrarianAgent(FakeProvider("C", [self.docx]), self.catalog, name="C"),
        ]
        result = asyncio.run(run_librarian_session(
            task="build a .docx",
            council=council,
            catalog=self.catalog,
            r2=self.r2,
            session_count=0,
        ))
        self.assertIsNotNone(result.r2_entry_id)

        entry_data = self.r2.load_entry(result.r2_entry_id)
        meta = entry_data.get("metadata", {})
        self.assertTrue(meta.get("librarian"))
        self.assertEqual(meta.get("selection"), [self.docx])
        self.assertEqual(meta.get("manifest_snapshot"), self.catalog.snapshot_hash())
        self.assertIn("candidate_ids", meta)
        self.assertEqual(meta.get("dissenter"), "A")
        self.assertIsNone(meta.get("downstream_outcome"))
        self.assertIn("per_specialist", meta)

    def test_session_requires_two_librarians(self):
        council = [
            LibrarianAgent(FakeProvider("only", [self.docx]), self.catalog, name="only"),
        ]
        with self.assertRaises(ValueError):
            asyncio.run(run_librarian_session(
                task="x", council=council, catalog=self.catalog,
            ))

    def test_provider_exception_non_fatal(self):
        class BrokenProvider(Agent):
            name = "broken"
            model = "broken"
            async def fetch(self, prompt):
                raise RuntimeError("boom")

        council = [
            LibrarianAgent(BrokenProvider(), self.catalog, name="broken-agent"),
            LibrarianAgent(FakeProvider("ok1", [self.docx]), self.catalog, name="ok1"),
            LibrarianAgent(FakeProvider("ok2", [self.docx]), self.catalog, name="ok2"),
        ]
        result = asyncio.run(run_librarian_session(
            task="x", council=council, catalog=self.catalog, session_count=99,
        ))
        # Broken provider shows up as empty selector; ok1+ok2 carry docx to consensus
        self.assertIn(self.docx, result.consensus_bundle_ids)


class TestAgentContract(unittest.TestCase):
    """LibrarianAgent should still behave as a plain Agent."""

    def test_is_agent_subclass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "c"
            root.mkdir()
            _make_corpus(root)
            cat = Catalog.from_skills_root(root)
            la = LibrarianAgent(FakeProvider("p", []), cat, name="test")
            self.assertIsInstance(la, Agent)
            self.assertEqual(la.name, "test")
            self.assertTrue(la.model)

    def test_fetch_returns_canonical_json_string(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "c"
            root.mkdir()
            _make_corpus(root)
            cat = Catalog.from_skills_root(root)
            docx = next(m for m in cat if m.name == "docx").bundle_id
            la = LibrarianAgent(FakeProvider("p", [docx]), cat, name="test")
            raw = asyncio.run(la.fetch("build a .docx in python"))
            decoded = json.loads(raw)
            self.assertEqual(decoded["role"], "selector")
            self.assertIn(docx, decoded["bundle_ids"])


if __name__ == "__main__":
    unittest.main()
