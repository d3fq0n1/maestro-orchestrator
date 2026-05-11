"""
Integration test for Track C step 3: load + run the synthetic
seed dataset against a baseline DistanceMetric configuration.

Establishes the end-to-end harness:

  data/benchmarks/admission_seed.json
    -> load_dataset(path) -> BenchmarkDataset
    -> BenchmarkRunner(distance_metric, embedder).evaluate(...)
    -> BenchmarkResult with overall + per-tier + ranking metrics

Tuning the DistanceMetric so the seed dataset reaches a target
F1 against the labeled ground truth is data-blocked work that
follows once real annotation is available. This test only
verifies the harness runs end-to-end and produces non-degenerate
metrics.
"""

import hashlib
from pathlib import Path

import pytest

from maestro.router.benchmark import (
    BenchmarkDataset,
    BenchmarkResult,
    load_dataset,
)
from maestro.router.benchmark_runner import BenchmarkRunner
from maestro.router.distance import (
    DistanceMetric,
    DistanceWeights,
    Tier,
)


SEED_PATH = (
    Path(__file__).resolve().parent.parent
    / "data" / "benchmarks" / "admission_seed.json"
)


def _topic_embedder(dim: int = 32):
    """Topic-aware mean-zero embedder.

    Words are hashed individually; the embedding is the mean of
    word-vectors. This gives the runner a coarse semantic signal
    (queries with overlapping content words have higher cosine
    similarity than queries with disjoint vocabulary) without
    requiring a real embedding service.
    """
    cache: dict = {}

    def _word_vector(word: str):
        if word in cache:
            return cache[word]
        digest = hashlib.sha256(word.lower().encode("utf-8")).digest()
        v = tuple((b / 255.0) - 0.5 for b in digest[:dim])
        cache[word] = v
        return v

    def embed(text: str):
        words = text.split()
        if not words:
            return [0.0] * dim
        vectors = [_word_vector(w) for w in words]
        averaged = [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]
        return averaged

    return embed


# ---- loader ----


def test_seed_file_exists():
    assert SEED_PATH.exists(), f"missing seed file at {SEED_PATH}"


def test_load_dataset_parses_seed():
    dataset = load_dataset(SEED_PATH)
    assert isinstance(dataset, BenchmarkDataset)
    assert dataset.name == "admission-seed-v1"
    assert dataset.description != ""
    assert len(dataset.examples) >= 12, (
        f"seed should hold ~12 examples, got {len(dataset.examples)}"
    )


def test_load_dataset_preserves_candidate_metadata():
    """Round-trip the JSON format preserves all candidate fields."""
    dataset = load_dataset(SEED_PATH)
    first_example = dataset.examples[0]
    assert first_example.example_id == "topic-match-cartridge"
    assert first_example.notes != ""
    cart = first_example.candidates[0]
    assert cart.id == "CART:tax-code@2024"
    assert cart.tier == Tier.CARTRIDGE
    assert cart.trust == 0.95
    assert cart.tags == ("law.us.federal",)
    assert cart.expected_admit is True


def test_load_dataset_preserves_ranked_admit():
    dataset = load_dataset(SEED_PATH)
    # The first example has ranked_admit
    first = dataset.examples[0]
    assert first.ranked_admit == ("CART:tax-code@2024",)


# ---- end-to-end harness ----


def test_runner_evaluates_seed_dataset():
    """Smoke test: the harness runs end-to-end without raising
    and produces a BenchmarkResult of the expected shape.
    """
    dataset = load_dataset(SEED_PATH)
    runner = BenchmarkRunner(
        distance_metric=DistanceMetric(),
        embedder=_topic_embedder(),
    )
    result = runner.evaluate(dataset)

    assert isinstance(result, BenchmarkResult)
    assert result.dataset_name == "admission-seed-v1"
    assert result.examples_evaluated == len(dataset.examples)
    # Every example produced an outcome
    assert len(result.per_example_outcomes) == len(dataset.examples)
    # Overall support equals total candidates
    expected_support = sum(len(e.candidates) for e in dataset.examples)
    assert result.overall_metrics.support == expected_support


def test_runner_produces_per_tier_metrics_for_represented_tiers():
    dataset = load_dataset(SEED_PATH)
    runner = BenchmarkRunner(
        distance_metric=DistanceMetric(),
        embedder=_topic_embedder(),
    )
    result = runner.evaluate(dataset)

    # Seed has cartridges, whirlpool items, and weight-prior tags
    assert Tier.CARTRIDGE in result.tier_metrics
    assert Tier.WHIRLPOOL in result.tier_metrics
    assert Tier.WEIGHT_PRIOR in result.tier_metrics

    # Each tier has a positive support count
    for tier in (Tier.CARTRIDGE, Tier.WHIRLPOOL, Tier.WEIGHT_PRIOR):
        assert result.tier_metrics[tier].support > 0


def test_runner_produces_ranking_metrics_when_seed_has_ranked_admit():
    dataset = load_dataset(SEED_PATH)
    runner = BenchmarkRunner(
        distance_metric=DistanceMetric(),
        embedder=_topic_embedder(),
    )
    result = runner.evaluate(dataset)

    # At least one example carries ranked_admit
    assert result.ranking_metrics is not None
    assert result.ranking_metrics.examples_with_ranking >= 1
    assert 0.0 <= result.ranking_metrics.map_score <= 1.0


def test_runner_metrics_are_deterministic_across_runs():
    """Same dataset + same metric + same embedder seeds must
    yield identical metrics.
    """
    dataset = load_dataset(SEED_PATH)
    a = BenchmarkRunner(
        distance_metric=DistanceMetric(),
        embedder=_topic_embedder(),
    ).evaluate(dataset)
    b = BenchmarkRunner(
        distance_metric=DistanceMetric(),
        embedder=_topic_embedder(),
    ).evaluate(dataset)
    assert a.overall_metrics == b.overall_metrics
    assert a.tier_metrics == b.tier_metrics


def test_runner_metrics_change_with_tau():
    """Sanity: increasing the cartridge tau eliminates admissions
    so cartridge precision becomes 0.0 (since true_positives drops
    to 0). Confirms the runner respects tau_per_tier overrides.
    """
    dataset = load_dataset(SEED_PATH)
    base = BenchmarkRunner(
        distance_metric=DistanceMetric(),
        embedder=_topic_embedder(),
    ).evaluate(dataset)
    strict = BenchmarkRunner(
        distance_metric=DistanceMetric(),
        embedder=_topic_embedder(),
        tau_per_tier={
            Tier.CARTRIDGE: 1e9,
            Tier.WHIRLPOOL: 1e9,
            Tier.WEIGHT_PRIOR: 1e9,
        },
    ).evaluate(dataset)

    # Strict policy: nothing admits anywhere
    assert strict.overall_metrics.true_positives == 0
    assert strict.overall_metrics.false_positives == 0
    # The base run admitted at least something (we don't pin the
    # exact count — that's the data-blocked tuning question — but
    # the strict run should differ).
    assert (
        strict.overall_metrics.true_positives !=
        base.overall_metrics.true_positives
        or strict.overall_metrics.false_positives !=
        base.overall_metrics.false_positives
    )


def test_runner_metrics_in_unit_interval():
    dataset = load_dataset(SEED_PATH)
    result = BenchmarkRunner(
        distance_metric=DistanceMetric(),
        embedder=_topic_embedder(),
    ).evaluate(dataset)

    assert 0.0 <= result.overall_metrics.precision <= 1.0
    assert 0.0 <= result.overall_metrics.recall <= 1.0
    assert 0.0 <= result.overall_metrics.f1 <= 1.0
    for tier_metrics in result.tier_metrics.values():
        assert 0.0 <= tier_metrics.precision <= 1.0
        assert 0.0 <= tier_metrics.recall <= 1.0
        assert 0.0 <= tier_metrics.f1 <= 1.0
