"""
Benchmark types for evaluating Router admission quality.

Track C of the items-4-6 cluster. Defines the dataset schema
``BenchmarkRunner`` consumes and the result schema it produces.

Decisions baked in:

  Q-C1 = c: Dataset carries both binary admit-decision labels
            (``BenchmarkCandidate.expected_admit``) AND optional
            ranking annotations (``BenchmarkExample.ranked_admit``
            / ``ranked_reject``) so the runner produces both
            classification and ranking metrics when annotations
            are present.

  Q-C2 = beta: ``BenchmarkResult`` exposes overall + per-tier
            metrics so operators can see if the Router is biased
            (e.g., over-admitting Whirlpool items at the cost of
            Cartridges). Long-shot tail metrics are deferred —
            they require ``ContextRouter``'s tail-sampling code
            which is still scaffolded.

This module is types only. The runner that consumes them lives
in ``benchmark_runner.py`` (Track C step 2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from maestro.router.distance import Tier


# ---- dataset types ----


@dataclass(frozen=True)
class BenchmarkQuery:
    """The query side of a benchmark example.

    ``tags`` mirrors the runtime ``query_tags`` plumbing in
    ``DistanceMetric.components`` and supports both flat and
    dotted forms.
    """

    text: str
    tags: tuple = ()


@dataclass(frozen=True)
class BenchmarkCandidate:
    """One candidate the runner must decide admit-or-reject on.

    ``trust`` is per-candidate so the dataset can simulate
    different tier-trust scenarios (high-trust Cartridge vs
    low-trust Whirlpool item, cartridge with revocation pending,
    etc.) without depending on a live Librarian.

    ``tier`` mirrors ``router-distance.md`` §Trust and Relevance
    so the runner can apply per-tier ``tau`` thresholds.
    """

    id: str
    text: str
    tier: Tier
    expected_admit: bool
    trust: float = 0.5
    tags: tuple = ()
    notes: str = ""


@dataclass(frozen=True)
class BenchmarkExample:
    """One labeled admission example.

    The base shape (``query`` + ``candidates``) supports binary
    classification metrics. The optional ``ranked_admit`` and
    ``ranked_reject`` lists carry preference order over
    candidate IDs for ranking metrics — Q-C1=c gives operators
    both surfaces in one schema.

    ``notes`` is for human-readable test-set documentation
    (which adversarial pattern this example exercises, etc.) and
    is preserved through serialization but not consumed by the
    runner.
    """

    example_id: str
    query: BenchmarkQuery
    candidates: tuple = ()
    ranked_admit: tuple = ()
    ranked_reject: tuple = ()
    notes: str = ""


@dataclass(frozen=True)
class BenchmarkDataset:
    """A named collection of benchmark examples.

    Ships with a ``name`` so multiple datasets can coexist (e.g.,
    one for admission quality, another for adversarial
    robustness once the integrated runner exists).
    """

    name: str
    examples: tuple = ()
    description: str = ""


# ---- result types ----


@dataclass(frozen=True)
class TierMetrics:
    """Precision / recall / F1 for one tier (or for the overall set).

    Counts are stored; precision / recall / F1 are computed
    properties so the dataclass stays cheap to construct and
    serialize. Zero-division returns 0.0 rather than NaN —
    operators want a deterministic number, and 0.0 carries the
    "no data" signal well enough alongside the raw counts.
    """

    tier: Optional[Tier] = None
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0

    @property
    def support(self) -> int:
        """Total candidates the metric was computed over."""
        return (
            self.true_positives
            + self.false_positives
            + self.true_negatives
            + self.false_negatives
        )

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p = self.precision
        r = self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


@dataclass(frozen=True)
class CandidateOutcome:
    """Per-candidate benchmark outcome.

    Records the runner's decision plus the intermediate signals
    that produced it, so operators can inspect why a candidate
    was admitted or rejected.
    """

    candidate_id: str
    tier: Tier
    expected_admit: bool
    actual_admit: bool
    score: float                # (trust * relevance) / (distance + epsilon)
    composite_distance: float
    relevance: float
    trust: float
    tau: float                  # threshold in force for this candidate's tier


@dataclass(frozen=True)
class ExampleOutcome:
    """Per-example outcome — all candidate outcomes for one example."""

    example_id: str
    candidate_outcomes: tuple = ()


@dataclass(frozen=True)
class RankingMetrics:
    """Ranking metrics, populated only when an example carries
    ``ranked_admit`` / ``ranked_reject`` annotations.

    Mean Average Precision (MAP) and NDCG@k are the standard
    ranking metrics. ``ndcg_at_k`` is keyed by k so a benchmark
    can report multiple cutoffs in one result.
    """

    map_score: float = 0.0
    ndcg_at_k: dict = field(default_factory=dict)
    examples_with_ranking: int = 0


@dataclass(frozen=True)
class BenchmarkResult:
    """Aggregate result of running a ``BenchmarkDataset``.

    The runner returns one of these. The frozen-dataclass shape
    means a result can be serialized for trend tracking (a
    Router config change can be A/B'd by comparing two
    BenchmarkResults).

    ``tier_metrics`` is keyed by Tier; absent tiers (no
    candidates of that tier in the dataset) are omitted rather
    than included with zero counts.
    """

    dataset_name: str
    examples_evaluated: int
    overall_metrics: TierMetrics
    tier_metrics: dict = field(default_factory=dict)
    ranking_metrics: Optional[RankingMetrics] = None
    per_example_outcomes: tuple = ()


# ---- on-disk format ----


def load_dataset(path) -> BenchmarkDataset:
    """Load a BenchmarkDataset from a JSON file.

    Format::

        {
          "name": "...",
          "description": "...",
          "examples": [
            {
              "example_id": "...",
              "notes": "...",
              "query": {"text": "...", "tags": [...]},
              "candidates": [
                {"id": "...", "text": "...", "tier": "...",
                 "expected_admit": bool, "trust": float,
                 "tags": [...], "notes": "..."},
                ...
              ],
              "ranked_admit": [...],
              "ranked_reject": [...]
            },
            ...
          ]
        }

    ``tier`` is the lowercase string form of ``Tier``
    (``"cartridge"``, ``"whirlpool"``, ``"weight_prior"``).
    Missing optional fields fall back to dataclass defaults.
    """
    raw = json.loads(Path(path).read_text())
    return _parse_dataset(raw)


def _parse_dataset(raw: dict) -> BenchmarkDataset:
    examples = tuple(
        _parse_example(e) for e in raw.get("examples", [])
    )
    return BenchmarkDataset(
        name=raw.get("name", ""),
        examples=examples,
        description=raw.get("description", ""),
    )


def _parse_example(raw: dict) -> BenchmarkExample:
    return BenchmarkExample(
        example_id=raw["example_id"],
        query=BenchmarkQuery(
            text=raw["query"]["text"],
            tags=tuple(raw["query"].get("tags", [])),
        ),
        candidates=tuple(
            _parse_candidate(c) for c in raw.get("candidates", [])
        ),
        ranked_admit=tuple(raw.get("ranked_admit", [])),
        ranked_reject=tuple(raw.get("ranked_reject", [])),
        notes=raw.get("notes", ""),
    )


def _parse_candidate(raw: dict) -> BenchmarkCandidate:
    return BenchmarkCandidate(
        id=raw["id"],
        text=raw["text"],
        tier=Tier(raw["tier"]),
        expected_admit=bool(raw["expected_admit"]),
        trust=float(raw.get("trust", 0.5)),
        tags=tuple(raw.get("tags", [])),
        notes=raw.get("notes", ""),
    )
