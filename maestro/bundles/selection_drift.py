"""
Selection drift tracker — NCG-style monitor for librarian selections.

Where ``maestro.ncg.drift`` measures *semantic* drift between conversational
and headless outputs of a single session, this module measures *distribution*
drift across many librarian sessions. The question it answers:

    "Given the catalog hasn't changed, are the librarians' selection
     patterns changing? Is the council collapsing toward a monoculture?"

Signals produced:
  * selection_entropy        — Shannon entropy of the per-bundle selection
                                frequency distribution. Lower = more
                                monoculture.
  * window_jaccard_distance  — Jaccard distance between the selection-set
                                of the earlier half and the later half of
                                the analysed window. Higher = pattern
                                shift.
  * suspicious_shift         — True when entropy drops sharply while the
                                catalog snapshot is unchanged, which is
                                the librarian analogue of silent collapse.

This module is advisory. It does not mutate the ledger or selections; it
reads and reports. MAGI can surface its findings as
``ImprovementSignal`` entries later.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional


# --- Report shape -------------------------------------------------------

@dataclass
class SelectionDriftReport:
    """Summary of librarian selection behaviour across a window of sessions."""

    sessions_analysed: int
    unique_bundles_selected: int
    selection_entropy: float           # nats; 0 = single bundle, ln(N) = uniform
    max_possible_entropy: float        # ln(unique_bundles_selected)
    per_bundle_frequency: dict         # {bundle_id: count}
    top_bundles: list                  # [(bundle_id, count), ...] top 5
    window_jaccard_distance: float     # first-half vs second-half selection-set
    catalog_snapshot_ids: list         # distinct manifest_snapshot hashes seen
    suspicious_shift: bool             # entropy collapsed while catalog fixed
    notes: list = field(default_factory=list)


# --- Tracker ------------------------------------------------------------

class SelectionDriftTracker:
    """Analyses a sequence of librarian R2 ledger entries.

    Each ledger entry is expected to carry, under ``metadata``:
        * ``librarian``: True
        * ``selection``: [bundle_id, ...]          # the consensus selection
        * ``manifest_snapshot``: str               # catalog hash at decision time
        * ``task_tags``: dict (optional)           # query tags, if present

    Non-librarian entries are ignored silently.
    """

    # Thresholds below are deliberately conservative. Tune via R2 feedback
    # once the ledger accumulates real data.
    _ENTROPY_COLLAPSE_FRACTION = 0.5   # drop below 50% of max => suspicious
    _JACCARD_SHIFT_THRESHOLD = 0.6     # 60%+ of sets differ => notable shift

    def __init__(
        self,
        entropy_collapse_fraction: float = None,
        jaccard_shift_threshold: float = None,
    ):
        self._entropy_frac = (
            entropy_collapse_fraction
            if entropy_collapse_fraction is not None
            else self._ENTROPY_COLLAPSE_FRACTION
        )
        self._jaccard_thresh = (
            jaccard_shift_threshold
            if jaccard_shift_threshold is not None
            else self._JACCARD_SHIFT_THRESHOLD
        )

    # --- public API ---

    def analyse(self, ledger_entries: Iterable[dict]) -> SelectionDriftReport:
        """Produce a drift report from an iterable of R2 ledger entry dicts.

        Entries that are not librarian sessions (or lack ``selection``)
        are skipped. Ordering should be chronological (oldest first) for
        the first-half/second-half Jaccard comparison to be meaningful.
        """
        sessions = [e for e in ledger_entries if self._is_librarian_entry(e)]

        selections: list[list[str]] = []
        snapshots: list[str] = []
        for entry in sessions:
            meta = entry.get("metadata") or {}
            sel = meta.get("selection") or []
            if not isinstance(sel, list):
                continue
            selections.append([str(b) for b in sel])
            snap = meta.get("manifest_snapshot")
            if snap:
                snapshots.append(str(snap))

        if not selections:
            return SelectionDriftReport(
                sessions_analysed=0,
                unique_bundles_selected=0,
                selection_entropy=0.0,
                max_possible_entropy=0.0,
                per_bundle_frequency={},
                top_bundles=[],
                window_jaccard_distance=0.0,
                catalog_snapshot_ids=[],
                suspicious_shift=False,
                notes=["No librarian ledger entries in window."],
            )

        freq = self._frequencies(selections)
        entropy = self._shannon_entropy(freq)
        max_entropy = math.log(len(freq)) if len(freq) > 1 else 0.0
        jaccard = self._window_jaccard_distance(selections)

        distinct_snapshots = sorted(set(snapshots))
        catalog_stable = len(distinct_snapshots) <= 1

        suspicious = False
        notes: list[str] = []
        if max_entropy > 0 and entropy < max_entropy * self._entropy_frac:
            if catalog_stable:
                suspicious = True
                notes.append(
                    f"Entropy {entropy:.3f} is below {self._entropy_frac:.0%} of "
                    f"max {max_entropy:.3f} with a stable catalog — possible "
                    f"selection monoculture."
                )
            else:
                notes.append(
                    f"Entropy {entropy:.3f} is low but catalog changed "
                    f"({len(distinct_snapshots)} snapshots observed) — expected."
                )
        if jaccard > self._jaccard_thresh:
            notes.append(
                f"Selection sets shifted sharply across the window "
                f"(Jaccard distance {jaccard:.3f})."
            )

        top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:5]

        return SelectionDriftReport(
            sessions_analysed=len(selections),
            unique_bundles_selected=len(freq),
            selection_entropy=round(entropy, 4),
            max_possible_entropy=round(max_entropy, 4),
            per_bundle_frequency=freq,
            top_bundles=top,
            window_jaccard_distance=round(jaccard, 4),
            catalog_snapshot_ids=distinct_snapshots,
            suspicious_shift=suspicious,
            notes=notes,
        )

    # --- helpers ---

    @staticmethod
    def _is_librarian_entry(entry: dict) -> bool:
        meta = entry.get("metadata") or {}
        if not meta.get("librarian"):
            return False
        return "selection" in meta

    @staticmethod
    def _frequencies(selections: list[list[str]]) -> dict[str, int]:
        freq: dict[str, int] = {}
        for sel in selections:
            for bid in sel:
                freq[bid] = freq.get(bid, 0) + 1
        return freq

    @staticmethod
    def _shannon_entropy(freq: dict[str, int]) -> float:
        total = sum(freq.values())
        if total == 0:
            return 0.0
        entropy = 0.0
        for count in freq.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log(p)
        return entropy

    @staticmethod
    def _window_jaccard_distance(selections: list[list[str]]) -> float:
        """Jaccard distance between the selection-sets of the first and
        second halves of the window. 0 = identical, 1 = disjoint.

        Needs at least 4 sessions to be meaningful; returns 0 below that.
        """
        if len(selections) < 4:
            return 0.0
        mid = len(selections) // 2
        first_set = {b for sel in selections[:mid] for b in sel}
        second_set = {b for sel in selections[mid:] for b in sel}
        if not first_set and not second_set:
            return 0.0
        intersection = first_set & second_set
        union = first_set | second_set
        return 1.0 - (len(intersection) / len(union)) if union else 0.0
