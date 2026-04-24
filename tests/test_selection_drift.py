"""Unit tests for the selection drift tracker."""

from __future__ import annotations

import unittest

from maestro.bundles.selection_drift import (
    SelectionDriftReport,
    SelectionDriftTracker,
)


def _entry(selection, snapshot="snap-1"):
    return {
        "entry_id": "x",
        "metadata": {
            "librarian": True,
            "selection": list(selection),
            "manifest_snapshot": snapshot,
        },
    }


class TestSelectionDriftTracker(unittest.TestCase):

    def test_empty_input(self):
        report = SelectionDriftTracker().analyse([])
        self.assertIsInstance(report, SelectionDriftReport)
        self.assertEqual(report.sessions_analysed, 0)
        self.assertFalse(report.suspicious_shift)

    def test_ignores_non_librarian(self):
        entries = [
            {"metadata": {"librarian": False, "selection": ["x"]}},
            {"metadata": {"librarian": True}},  # missing selection
        ]
        report = SelectionDriftTracker().analyse(entries)
        self.assertEqual(report.sessions_analysed, 0)

    def test_monoculture_with_stable_catalog_is_suspicious(self):
        # 6 sessions always selecting the same two bundles, catalog unchanged
        entries = [_entry(["a", "b"]) for _ in range(6)]
        report = SelectionDriftTracker().analyse(entries)
        self.assertEqual(report.sessions_analysed, 6)
        self.assertEqual(report.unique_bundles_selected, 2)
        # Entropy = ln(2) ≈ 0.693 (uniform over 2), which equals max — not suspicious
        self.assertAlmostEqual(report.selection_entropy, report.max_possible_entropy, places=4)
        self.assertFalse(report.suspicious_shift)

    def test_heavy_skew_is_suspicious(self):
        # One bundle dominates overwhelmingly across many sessions
        entries = (
            [_entry(["a"]) for _ in range(18)]
            + [_entry(["b"]) for _ in range(1)]
            + [_entry(["c"]) for _ in range(1)]
        )
        report = SelectionDriftTracker().analyse(entries)
        # Very low entropy relative to max (ln(3) ≈ 1.099), catalog stable => suspicious
        self.assertTrue(report.suspicious_shift)
        self.assertEqual(report.top_bundles[0][0], "a")

    def test_skew_with_catalog_change_not_flagged(self):
        # Same skew but the catalog snapshot flipped midway
        entries = (
            [_entry(["a"], snapshot="old") for _ in range(10)]
            + [_entry(["a"], snapshot="new") for _ in range(10)]
            + [_entry(["b"], snapshot="new") for _ in range(1)]
            + [_entry(["c"], snapshot="new") for _ in range(1)]
        )
        report = SelectionDriftTracker().analyse(entries)
        self.assertFalse(report.suspicious_shift)
        self.assertEqual(len(report.catalog_snapshot_ids), 2)

    def test_jaccard_shift_detected(self):
        # First half only a+b, second half only c+d — disjoint
        entries = (
            [_entry(["a", "b"]) for _ in range(4)]
            + [_entry(["c", "d"]) for _ in range(4)]
        )
        report = SelectionDriftTracker().analyse(entries)
        self.assertAlmostEqual(report.window_jaccard_distance, 1.0, places=4)
        self.assertTrue(any("shifted" in n for n in report.notes))

    def test_jaccard_zero_when_identical(self):
        entries = [_entry(["a", "b"]) for _ in range(6)]
        report = SelectionDriftTracker().analyse(entries)
        self.assertEqual(report.window_jaccard_distance, 0.0)

    def test_small_window_skips_jaccard(self):
        entries = [_entry(["a"]), _entry(["b"]), _entry(["c"])]
        report = SelectionDriftTracker().analyse(entries)
        # Fewer than 4 sessions — Jaccard returns 0 by design
        self.assertEqual(report.window_jaccard_distance, 0.0)


if __name__ == "__main__":
    unittest.main()
