"""
Smoke tests for maestro/router/benchmark_runner.py.

Track C step 2. Validates the BenchmarkRunner end-to-end:
admission decisions per the spec formula, per-tier aggregation,
ranking metrics. Uses a hand-built dataset so the expected
outcomes are knowable.
"""

import hashlib
import math

import pytest

from maestro.router.benchmark import (
    BenchmarkCandidate,
    BenchmarkDataset,
    BenchmarkExample,
    BenchmarkQuery,
    BenchmarkResult,
    RankingMetrics,
    TierMetrics,
)
from maestro.router.benchmark_runner import (
    BenchmarkRunner,
    _tag_match,
)
from maestro.router.distance import (
    DistanceMetric,
    DistanceWeights,
    Tier,
)


# ---- helpers ----


def _hash_embedder(dim: int = 16):
    """Deterministic test embedder."""
    def embed(text: str):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[:dim]]
    return embed


def _topic_embedder(dim: int = 16):
    """Topic-aware test embedder.

    Embeddings within the same 'topic' (first word of text) are
    identical; across topics they're approximately orthogonal.

    Implementation note: vectors are centered around zero
    (range ``[-0.5, 0.5]``) so two unrelated topics produce a
    mean cosine similarity near zero. An all-positive embedding
    space would force every cosine into ``[0, 1]``, making
    "different topic" still look like 70%+ similarity by
    accident — defeating the test.
    """
    def embed(text: str):
        first = text.strip().split(" ", 1)[0] if text.strip() else "x"
        digest = hashlib.sha256(first.encode("utf-8")).digest()
        return [(b / 255.0) - 0.5 for b in digest[:dim]]
    return embed


def _runner(distance: DistanceMetric = None, embedder=None, **kwargs) -> BenchmarkRunner:
    return BenchmarkRunner(
        distance_metric=distance or DistanceMetric(),
        embedder=embedder or _topic_embedder(),
        **kwargs,
    )


# ---- _tag_match ----


def test_tag_match_exact_intersection():
    assert _tag_match(("law", "us"), ("law", "ca")) == 1.0
    assert _tag_match(("a",), ("a",)) == 1.0


def test_tag_match_no_overlap():
    assert _tag_match(("law",), ("medicine",)) == 0.0


def test_tag_match_empty():
    assert _tag_match((), ("law",)) == 0.0
    assert _tag_match(("law",), ()) == 0.0


def test_tag_match_dotted_prefix_either_direction():
    assert _tag_match(("law.us.federal",), ("law.us",)) == 1.0
    assert _tag_match(("law.us",), ("law.us.state",)) == 1.0


def test_tag_match_dotted_no_prefix_relation():
    assert _tag_match(("law.us",), ("law.ca",)) == 0.0


# ---- BenchmarkRunner basic shapes ----


def test_runner_evaluate_returns_benchmark_result():
    dataset = BenchmarkDataset(name="empty")
    result = _runner().evaluate(dataset)
    assert isinstance(result, BenchmarkResult)
    assert result.dataset_name == "empty"
    assert result.examples_evaluated == 0
    assert result.overall_metrics == TierMetrics()
    assert result.tier_metrics == {}
    assert result.ranking_metrics is None
    assert result.per_example_outcomes == ()


# ---- single-example outcomes ----


def _topic_match_example():
    """Cartridge clearly on-topic should admit; off-topic
    cartridge should reject.
    """
    return BenchmarkExample(
        example_id="topic-match",
        query=BenchmarkQuery(text="law about taxes", tags=("law.us",)),
        candidates=(
            BenchmarkCandidate(
                id="CART:tax-code@2024",
                text="law about deductions",       # same first word -> same topic embed
                tier=Tier.CARTRIDGE,
                expected_admit=True,
                trust=0.95,
                tags=("law.us.federal",),         # prefix match
            ),
            BenchmarkCandidate(
                id="CART:cooking@2024",
                text="cooking with garlic",       # different topic
                tier=Tier.CARTRIDGE,
                expected_admit=False,
                trust=0.95,
                tags=("food.recipe",),
            ),
        ),
    )


def test_runner_admits_on_topic_cartridge_and_rejects_off_topic():
    dataset = BenchmarkDataset(
        name="topic-match", examples=(_topic_match_example(),),
    )
    result = _runner(embedder=_topic_embedder()).evaluate(dataset)
    outcomes = result.per_example_outcomes[0].candidate_outcomes
    on_topic = next(o for o in outcomes if o.candidate_id == "CART:tax-code@2024")
    off_topic = next(o for o in outcomes if o.candidate_id == "CART:cooking@2024")
    assert on_topic.actual_admit is True
    assert off_topic.actual_admit is False
    # Composite distance reflects topic match
    assert on_topic.composite_distance < off_topic.composite_distance


def test_runner_per_tier_metrics_populated():
    dataset = BenchmarkDataset(
        name="topic-match", examples=(_topic_match_example(),),
    )
    result = _runner(embedder=_topic_embedder()).evaluate(dataset)
    assert Tier.CARTRIDGE in result.tier_metrics
    cart = result.tier_metrics[Tier.CARTRIDGE]
    assert cart.tier == Tier.CARTRIDGE
    # Both candidates were Cartridges; we got both right
    assert cart.true_positives == 1
    assert cart.true_negatives == 1
    assert cart.false_positives == 0
    assert cart.false_negatives == 0
    assert cart.precision == 1.0
    assert cart.recall == 1.0
    assert cart.f1 == 1.0


def test_runner_overall_metrics_aggregate_across_tiers():
    """Cross-tier example: 1 cartridge + 1 whirlpool, both
    correctly classified. Overall metrics should reflect both.
    """
    example = BenchmarkExample(
        example_id="cross-tier",
        query=BenchmarkQuery(text="law about taxes", tags=("law.us",)),
        candidates=(
            BenchmarkCandidate(
                id="CART:tax@1",
                text="law about deductions",
                tier=Tier.CARTRIDGE,
                expected_admit=True,
                trust=0.95,
                tags=("law.us",),
            ),
            BenchmarkCandidate(
                id="WP:law-feed:abc12345",
                text="law breaking news today",
                tier=Tier.WHIRLPOOL,
                expected_admit=True,
                trust=0.6,
                tags=("law.us",),
            ),
        ),
    )
    dataset = BenchmarkDataset(name="cross-tier", examples=(example,))
    result = _runner(embedder=_topic_embedder()).evaluate(dataset)
    # Both tiers represented
    assert Tier.CARTRIDGE in result.tier_metrics
    assert Tier.WHIRLPOOL in result.tier_metrics
    # Overall counts both
    overall = result.overall_metrics
    assert overall.support == 2


# ---- per-tier tau resolution ----


def test_runner_uses_per_tier_tau():
    """Whirlpool tau is lower (default 0.4) than Cartridge tau
    (default 0.8). A score of 0.6 should admit a Whirlpool item
    but not a Cartridge of the same trust.
    """
    candidates = (
        BenchmarkCandidate(
            id="CART:on@1", text="law tax",
            tier=Tier.CARTRIDGE, expected_admit=True, trust=0.5,
            tags=("law.us",),
        ),
        BenchmarkCandidate(
            id="WP:on:11111111", text="law tax",
            tier=Tier.WHIRLPOOL, expected_admit=True, trust=0.5,
            tags=("law.us",),
        ),
    )
    example = BenchmarkExample(
        example_id="tau-sensitivity",
        query=BenchmarkQuery(text="law tax", tags=("law.us",)),
        candidates=candidates,
    )
    dataset = BenchmarkDataset(name="t", examples=(example,))
    runner = _runner(embedder=_topic_embedder())
    result = runner.evaluate(dataset)
    cart_outcome = next(
        o for o in result.per_example_outcomes[0].candidate_outcomes
        if o.candidate_id == "CART:on@1"
    )
    wp_outcome = next(
        o for o in result.per_example_outcomes[0].candidate_outcomes
        if o.candidate_id == "WP:on:11111111"
    )
    assert cart_outcome.tau == 0.8
    assert wp_outcome.tau == 0.4
    # Both are on-topic, same trust; whirlpool admits where cartridge may not
    if cart_outcome.score < 0.8 and wp_outcome.score >= 0.4:
        assert cart_outcome.actual_admit is False
        assert wp_outcome.actual_admit is True


def test_runner_tau_per_tier_is_overridable():
    candidates = (
        BenchmarkCandidate(
            id="CART:any@1", text="law tax",
            tier=Tier.CARTRIDGE, expected_admit=True, trust=0.5,
            tags=("law.us",),
        ),
    )
    example = BenchmarkExample(
        example_id="custom-tau",
        query=BenchmarkQuery(text="law tax", tags=("law.us",)),
        candidates=candidates,
    )
    dataset = BenchmarkDataset(name="t", examples=(example,))
    # Override Cartridge tau to 0.0 -> any positive score admits
    runner = _runner(
        embedder=_topic_embedder(),
        tau_per_tier={Tier.CARTRIDGE: 0.0, Tier.WHIRLPOOL: 0.0, Tier.WEIGHT_PRIOR: 0.0},
    )
    result = runner.evaluate(dataset)
    cart_outcome = result.per_example_outcomes[0].candidate_outcomes[0]
    assert cart_outcome.tau == 0.0
    assert cart_outcome.actual_admit is True


# ---- candidate outcome inspection ----


def test_runner_candidate_outcome_records_intermediate_signals():
    """Per-candidate outcome carries score, distance, relevance,
    trust, tau so operators can debug admissions.
    """
    example = _topic_match_example()
    dataset = BenchmarkDataset(name="t", examples=(example,))
    result = _runner(embedder=_topic_embedder()).evaluate(dataset)
    o = result.per_example_outcomes[0].candidate_outcomes[0]
    assert o.candidate_id is not None
    assert o.tier in (Tier.CARTRIDGE, Tier.WHIRLPOOL, Tier.WEIGHT_PRIOR)
    assert isinstance(o.expected_admit, bool)
    assert isinstance(o.actual_admit, bool)
    assert o.score >= 0.0
    assert 0.0 <= o.composite_distance <= 1.0
    assert 0.0 <= o.relevance <= 1.0
    assert 0.0 <= o.trust <= 1.0
    assert o.tau >= 0.0


# ---- ranking metrics ----


def test_runner_ranking_metrics_present_when_annotations_present():
    example = BenchmarkExample(
        example_id="ranked",
        query=BenchmarkQuery(text="law about taxes", tags=("law.us",)),
        candidates=(
            BenchmarkCandidate(
                id="C1", text="law about deductions",
                tier=Tier.CARTRIDGE, expected_admit=True, trust=0.95,
                tags=("law.us",),
            ),
            BenchmarkCandidate(
                id="C2", text="law about jurisdiction",
                tier=Tier.CARTRIDGE, expected_admit=True, trust=0.9,
                tags=("law.us",),
            ),
            BenchmarkCandidate(
                id="C3", text="cooking",
                tier=Tier.CARTRIDGE, expected_admit=False, trust=0.95,
                tags=("food",),
            ),
        ),
        ranked_admit=("C1", "C2"),
    )
    dataset = BenchmarkDataset(name="ranked", examples=(example,))
    result = _runner(embedder=_topic_embedder()).evaluate(dataset)
    assert result.ranking_metrics is not None
    assert result.ranking_metrics.examples_with_ranking == 1
    # MAP in [0, 1]
    assert 0.0 <= result.ranking_metrics.map_score <= 1.0
    # NDCG@k present for default ks
    assert 5 in result.ranking_metrics.ndcg_at_k
    assert 10 in result.ranking_metrics.ndcg_at_k


def test_runner_ranking_metrics_none_when_no_annotations():
    example = _topic_match_example()  # has no ranked_admit
    dataset = BenchmarkDataset(name="t", examples=(example,))
    result = _runner(embedder=_topic_embedder()).evaluate(dataset)
    assert result.ranking_metrics is None


def test_runner_perfect_ranking_yields_high_map():
    """If the runner ranks the relevant items at the top, MAP
    approaches 1.0.
    """
    example = BenchmarkExample(
        example_id="perfect-rank",
        query=BenchmarkQuery(text="law tax", tags=("law.us",)),
        candidates=(
            BenchmarkCandidate(
                id="CART:on@1", text="law about taxes",
                tier=Tier.CARTRIDGE, expected_admit=True, trust=0.95,
                tags=("law.us",),
            ),
            BenchmarkCandidate(
                id="CART:off@1", text="cooking with garlic",
                tier=Tier.CARTRIDGE, expected_admit=False, trust=0.95,
                tags=("food",),
            ),
        ),
        ranked_admit=("CART:on@1",),
    )
    dataset = BenchmarkDataset(name="t", examples=(example,))
    result = _runner(embedder=_topic_embedder()).evaluate(dataset)
    # Only one relevant item; if it's ranked first, MAP = 1.0
    assert result.ranking_metrics is not None
    assert math.isclose(result.ranking_metrics.map_score, 1.0, rel_tol=1e-6)
    assert result.ranking_metrics.ndcg_at_k[5] == 1.0


# ---- multiple examples ----


def test_runner_aggregates_across_multiple_examples():
    examples = (
        _topic_match_example(),
        BenchmarkExample(
            example_id="another",
            query=BenchmarkQuery(text="law about housing", tags=("law.us",)),
            candidates=(
                BenchmarkCandidate(
                    id="CART:housing@1",
                    text="law about renting",
                    tier=Tier.CARTRIDGE, expected_admit=True, trust=0.9,
                    tags=("law.us",),
                ),
            ),
        ),
    )
    dataset = BenchmarkDataset(name="multi", examples=examples)
    result = _runner(embedder=_topic_embedder()).evaluate(dataset)
    assert result.examples_evaluated == 2
    assert result.overall_metrics.support == 3   # 2 + 1 candidates


# ---- determinism ----


def test_runner_evaluate_is_deterministic():
    """Same dataset + same metric + same embedder seed produces
    the same result.
    """
    dataset = BenchmarkDataset(
        name="det", examples=(_topic_match_example(),),
    )
    a = _runner(embedder=_topic_embedder()).evaluate(dataset)
    b = _runner(embedder=_topic_embedder()).evaluate(dataset)
    assert a.overall_metrics == b.overall_metrics
    assert a.tier_metrics == b.tier_metrics


# ---- multiple evaluate calls don't share state ----


def test_runner_evaluate_does_not_carry_state_between_runs():
    runner = _runner(embedder=_topic_embedder())
    dataset = BenchmarkDataset(name="t", examples=(_topic_match_example(),))
    a = runner.evaluate(dataset)
    b = runner.evaluate(dataset)
    # Counts equal (deterministic), but they're independent results
    assert a.overall_metrics == b.overall_metrics
    assert a is not b


# ---- relevance combiner ----


def test_runner_custom_relevance_weights():
    """relevance_w_topic + relevance_w_type defaults are 0.7/0.3.
    Setting w_type=1.0, w_topic=0.0 makes relevance entirely
    tag-driven.
    """
    candidates = (
        BenchmarkCandidate(
            id="CART:any@1",
            text="completely-unrelated text",
            tier=Tier.CARTRIDGE,
            expected_admit=True,
            trust=0.95,
            tags=("law.us",),       # tag matches query
        ),
    )
    example = BenchmarkExample(
        example_id="tag-only-relevance",
        query=BenchmarkQuery(text="law tax", tags=("law.us",)),
        candidates=candidates,
    )
    dataset = BenchmarkDataset(name="t", examples=(example,))
    runner = _runner(
        embedder=_topic_embedder(),
        relevance_w_topic=0.0,
        relevance_w_type=1.0,
    )
    result = runner.evaluate(dataset)
    o = result.per_example_outcomes[0].candidate_outcomes[0]
    # All relevance comes from tag match (=1.0); embed cosine ignored
    assert math.isclose(o.relevance, 1.0, rel_tol=1e-6)
