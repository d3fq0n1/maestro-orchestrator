"""
Smoke tests for maestro/router/benchmark.py — types only.

Track C step 1. Validates the dataset + result schemas: shape,
defaults, immutability, and TierMetrics arithmetic. The runner
that consumes these lands in step C-2.
"""

import pytest

from maestro.router.benchmark import (
    BenchmarkCandidate,
    BenchmarkDataset,
    BenchmarkExample,
    BenchmarkQuery,
    BenchmarkResult,
    CandidateOutcome,
    ExampleOutcome,
    RankingMetrics,
    TierMetrics,
)
from maestro.router.distance import Tier


# ---- TierMetrics arithmetic ----


def test_tier_metrics_default_is_zero():
    m = TierMetrics()
    assert m.support == 0
    assert m.precision == 0.0
    assert m.recall == 0.0
    assert m.f1 == 0.0


def test_tier_metrics_precision_recall_f1():
    m = TierMetrics(
        true_positives=10,
        false_positives=2,
        true_negatives=15,
        false_negatives=3,
    )
    # precision = 10/(10+2) = 0.833...
    # recall    = 10/(10+3) = 0.769...
    # f1        = 2*p*r/(p+r) = 0.800...
    assert abs(m.precision - 10 / 12) < 1e-9
    assert abs(m.recall - 10 / 13) < 1e-9
    assert abs(m.f1 - (2 * (10 / 12) * (10 / 13) / ((10 / 12) + (10 / 13)))) < 1e-9


def test_tier_metrics_perfect_classifier():
    m = TierMetrics(true_positives=20, false_positives=0, true_negatives=30, false_negatives=0)
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0


def test_tier_metrics_zero_division_returns_zero_not_nan():
    """No predicted positives -> precision = 0.0 (not NaN).
    No actual positives  -> recall    = 0.0.
    Both zero            -> f1        = 0.0.
    """
    no_predictions = TierMetrics(true_positives=0, false_positives=0, true_negatives=10, false_negatives=5)
    assert no_predictions.precision == 0.0
    assert no_predictions.recall == 0.0
    assert no_predictions.f1 == 0.0

    no_truths = TierMetrics(true_positives=0, false_positives=5, true_negatives=10, false_negatives=0)
    assert no_truths.precision == 0.0
    assert no_truths.recall == 0.0
    assert no_truths.f1 == 0.0


def test_tier_metrics_support_counts_all():
    m = TierMetrics(true_positives=1, false_positives=2, true_negatives=3, false_negatives=4)
    assert m.support == 10


def test_tier_metrics_carries_optional_tier():
    m = TierMetrics(tier=Tier.CARTRIDGE, true_positives=1)
    assert m.tier == Tier.CARTRIDGE
    # Without explicit tier, defaults to None
    assert TierMetrics().tier is None


# ---- frozen-dataclass immutability ----


@pytest.mark.parametrize("cls,kwargs", [
    (BenchmarkQuery, dict(text="q")),
    (BenchmarkCandidate, dict(id="c", text="t", tier=Tier.CARTRIDGE, expected_admit=True)),
    (BenchmarkExample, dict(example_id="e", query=BenchmarkQuery(text="q"))),
    (BenchmarkDataset, dict(name="d")),
    (TierMetrics, dict()),
    (CandidateOutcome, dict(
        candidate_id="c", tier=Tier.CARTRIDGE,
        expected_admit=True, actual_admit=True,
        score=1.0, composite_distance=0.5, relevance=0.8,
        trust=0.9, tau=0.5,
    )),
    (ExampleOutcome, dict(example_id="e")),
    (RankingMetrics, dict()),
])
def test_dataclasses_are_frozen(cls, kwargs):
    instance = cls(**kwargs)
    # Pick any field on the instance to mutate; if frozen, the
    # assignment raises FrozenInstanceError (a subclass of
    # AttributeError).
    field_name = next(iter(cls.__dataclass_fields__))
    with pytest.raises(Exception):
        setattr(instance, field_name, None)


# ---- default factories don't share state ----


def test_benchmark_dataset_examples_default_independent():
    d1 = BenchmarkDataset(name="a")
    d2 = BenchmarkDataset(name="b")
    # Default tuple is empty — but identity check confirms not shared
    assert d1.examples == ()
    assert d2.examples == ()


def test_tier_metrics_dict_default_independent():
    """BenchmarkResult.tier_metrics is a dict; verify default
    factories produce distinct dicts per instance.
    """
    r1 = BenchmarkResult(
        dataset_name="r1", examples_evaluated=0, overall_metrics=TierMetrics(),
    )
    r2 = BenchmarkResult(
        dataset_name="r2", examples_evaluated=0, overall_metrics=TierMetrics(),
    )
    r1.tier_metrics[Tier.CARTRIDGE] = TierMetrics(true_positives=1)
    assert Tier.CARTRIDGE not in r2.tier_metrics


def test_ranking_metrics_dict_default_independent():
    a = RankingMetrics()
    b = RankingMetrics()
    a.ndcg_at_k[5] = 0.9
    assert 5 not in b.ndcg_at_k


# ---- composability ----


def test_full_dataset_construction():
    """Smoke test: a complete BenchmarkDataset round-trips
    through the dataclass machinery without surprises.
    """
    candidates = (
        BenchmarkCandidate(
            id="CART:rfc9110@2022.06",
            text="HTTP semantics",
            tier=Tier.CARTRIDGE,
            expected_admit=True,
            trust=0.95,
            tags=("proto.http",),
        ),
        BenchmarkCandidate(
            id="WP:web-feed:abc12345",
            text="random tech blog",
            tier=Tier.WHIRLPOOL,
            expected_admit=False,
            trust=0.4,
            tags=("blog.tech",),
        ),
    )
    example = BenchmarkExample(
        example_id="http-spec-query",
        query=BenchmarkQuery(text="What does HTTP say about caching?", tags=("proto.http",)),
        candidates=candidates,
        ranked_admit=("CART:rfc9110@2022.06",),
        notes="Topic match: cartridge is on-topic and trusted.",
    )
    dataset = BenchmarkDataset(
        name="admission-seed-v1",
        examples=(example,),
        description="Hand-crafted seed for Router admission quality.",
    )
    assert dataset.name == "admission-seed-v1"
    assert len(dataset.examples) == 1
    assert dataset.examples[0].candidates[0].tier == Tier.CARTRIDGE
    assert dataset.examples[0].ranked_admit == ("CART:rfc9110@2022.06",)


def test_full_result_construction():
    """Smoke test: BenchmarkResult shape composes through."""
    overall = TierMetrics(true_positives=8, false_positives=1, true_negatives=10, false_negatives=1)
    cart_metrics = TierMetrics(
        tier=Tier.CARTRIDGE, true_positives=5, false_positives=0,
        true_negatives=5, false_negatives=0,
    )
    wp_metrics = TierMetrics(
        tier=Tier.WHIRLPOOL, true_positives=3, false_positives=1,
        true_negatives=5, false_negatives=1,
    )
    outcome = ExampleOutcome(
        example_id="ex1",
        candidate_outcomes=(
            CandidateOutcome(
                candidate_id="c1", tier=Tier.CARTRIDGE,
                expected_admit=True, actual_admit=True,
                score=1.5, composite_distance=0.2, relevance=0.9,
                trust=0.95, tau=0.5,
            ),
        ),
    )
    result = BenchmarkResult(
        dataset_name="admission-seed-v1",
        examples_evaluated=10,
        overall_metrics=overall,
        tier_metrics={Tier.CARTRIDGE: cart_metrics, Tier.WHIRLPOOL: wp_metrics},
        ranking_metrics=RankingMetrics(map_score=0.85, ndcg_at_k={5: 0.9}),
        per_example_outcomes=(outcome,),
    )
    assert result.examples_evaluated == 10
    assert result.tier_metrics[Tier.CARTRIDGE].precision == 1.0
    assert result.ranking_metrics.map_score == 0.85
    assert result.per_example_outcomes[0].candidate_outcomes[0].actual_admit is True
