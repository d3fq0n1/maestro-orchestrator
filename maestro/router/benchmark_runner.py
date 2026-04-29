"""
BenchmarkRunner — evaluates Router admission quality against
labeled examples.

Track C step 2 of the items-4-6 cluster. Runs each
``BenchmarkExample`` through the spec's admission formula

    admit(C) iff (trust(C) * relevance(Q, C)) / (distance(Q, C) + epsilon) >= tau(tier(C))

and aggregates per-tier and overall precision / recall / F1
(plus optional ranking metrics when the example carries
``ranked_admit`` / ``ranked_reject`` annotations).

Trust comes from the dataset (per ``BenchmarkCandidate.trust``)
so the runner can simulate scenarios without depending on a
live Librarian or Whirlpool. Relevance is computed from
embeddings + tag match against the same convention used by the
Router at runtime (router-distance.md §relevance).

The runner is stateless apart from its constructor configuration
(distance metric, embedder, weights, per-tier tau). Calling
``evaluate`` multiple times against different datasets is safe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

from maestro.router.benchmark import (
    BenchmarkCandidate,
    BenchmarkDataset,
    BenchmarkExample,
    BenchmarkResult,
    CandidateOutcome,
    ExampleOutcome,
    RankingMetrics,
    TierMetrics,
)
from maestro.router.distance import (
    DistanceMetric,
    DistanceWeights,
    Tier,
)


_DEFAULT_TAU_PER_TIER = {
    Tier.CARTRIDGE: 0.8,
    Tier.WHIRLPOOL: 0.4,
    Tier.WEIGHT_PRIOR: 0.3,
}

_DEFAULT_EPSILON = 0.01
_DEFAULT_RELEVANCE_W_TOPIC = 0.7
_DEFAULT_RELEVANCE_W_TYPE = 0.3
_DEFAULT_NDCG_KS = (5, 10)


def _tag_match(query_tags: tuple, candidate_tags: tuple) -> float:
    """Tag-match score for relevance.

    Mirrors router-distance.md §relevance(Q, C):
      * 1.0 on exact tag intersection (any common tag)
      * 1.0 on dotted prefix match (one side prefixes the other)
      * 0.0 otherwise
    """
    if not query_tags or not candidate_tags:
        return 0.0
    qset = set(query_tags)
    cset = set(candidate_tags)
    # Exact intersection
    if qset & cset:
        return 1.0
    # Dotted prefix match either direction
    for qt in qset:
        if "." not in qt:
            continue
        for ct in cset:
            if "." not in ct:
                continue
            if qt.startswith(ct + ".") or ct.startswith(qt + "."):
                return 1.0
    return 0.0


def _ranked_metrics_for_example(
    example: BenchmarkExample,
    candidate_scores: dict,
    ndcg_ks: tuple,
) -> Optional[dict]:
    """Compute MAP and NDCG@k for one example, or None if no
    ranking annotations are present.

    candidate_scores: ``{candidate_id: float}`` mapping each
    candidate to its admission criterion score. Ranked higher
    score = preferred admit.
    """
    if not example.ranked_admit:
        return None
    # The set of candidates the spec says SHOULD admit, in
    # preference order.
    relevant = list(example.ranked_admit)
    if not relevant:
        return None

    # Sort all candidates by descending score to get the runner's
    # ranking. Ties broken by candidate_id for determinism.
    runner_ranking = sorted(
        candidate_scores.items(),
        key=lambda pair: (-pair[1], pair[0]),
    )
    runner_order = [cid for cid, _ in runner_ranking]

    # MAP: average precision over the relevant set
    relevant_set = set(relevant)
    precisions: list = []
    hits = 0
    for i, cid in enumerate(runner_order, 1):
        if cid in relevant_set:
            hits += 1
            precisions.append(hits / i)
    map_score = sum(precisions) / len(relevant_set) if relevant_set else 0.0

    # NDCG@k for each k in ndcg_ks
    # Relevance grade: position-based (top of ranked_admit = highest gain)
    grade = {cid: len(relevant) - rank for rank, cid in enumerate(relevant)}
    ndcg_at_k: dict = {}
    for k in ndcg_ks:
        dcg = 0.0
        for rank, cid in enumerate(runner_order[:k], 1):
            g = grade.get(cid, 0)
            if g == 0:
                continue
            dcg += g / math.log2(rank + 1)
        # Ideal DCG
        ideal = sorted(grade.values(), reverse=True)
        idcg = sum(g / math.log2(rank + 1) for rank, g in enumerate(ideal[:k], 1))
        ndcg_at_k[k] = dcg / idcg if idcg > 0 else 0.0

    return {"map": map_score, "ndcg_at_k": ndcg_at_k}


@dataclass(frozen=True)
class _RunningCounts:
    """Mutable-via-replace running tally of TP/FP/TN/FN.

    Frozen-with-replace lets us avoid leaking a mutable dict to
    callers while still accumulating during a run.
    """

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def add(self, expected: bool, predicted: bool) -> "_RunningCounts":
        if predicted and expected:
            return _RunningCounts(self.tp + 1, self.fp, self.tn, self.fn)
        if predicted and not expected:
            return _RunningCounts(self.tp, self.fp + 1, self.tn, self.fn)
        if not predicted and expected:
            return _RunningCounts(self.tp, self.fp, self.tn, self.fn + 1)
        return _RunningCounts(self.tp, self.fp, self.tn + 1, self.fn)


class BenchmarkRunner:
    """Runs a labeled dataset through admission decisions.

    Construction
    ------------
    distance_metric:
        The DistanceMetric whose admission decisions are being
        benchmarked. Embedder need not be set on it (the runner
        owns its own embedder for query / candidate text), but
        if the metric was built with d_counter wired to a real
        embedder, that runs as part of the composite.
    embedder:
        ``Callable[[str], list[float]]`` for embedding query and
        candidate text. The runner uses this both to drive
        ``DistanceMetric.components`` and to compute the
        embedding-cosine portion of relevance.
    weights:
        ``DistanceWeights`` for collapsing components into the
        composite distance. Defaults to ``DistanceWeights()``.
    tau_per_tier:
        Per-tier admission threshold. Defaults to
        Cartridge=0.8, Whirlpool=0.4, Weight-prior=0.3 per
        router-distance.md.
    relevance_w_topic / relevance_w_type:
        Relevance combiner weights. Defaults match
        router-distance.md §relevance(Q, C): topic 0.7, type 0.3.
    epsilon:
        Numerical stability denominator added to the composite
        distance before division. Default 0.01.
    ndcg_ks:
        K values for NDCG@k reporting (default (5, 10)).
    """

    def __init__(
        self,
        distance_metric: DistanceMetric,
        embedder: Callable[[str], list],
        *,
        weights: Optional[DistanceWeights] = None,
        tau_per_tier: Optional[dict] = None,
        relevance_w_topic: float = _DEFAULT_RELEVANCE_W_TOPIC,
        relevance_w_type: float = _DEFAULT_RELEVANCE_W_TYPE,
        epsilon: float = _DEFAULT_EPSILON,
        ndcg_ks: tuple = _DEFAULT_NDCG_KS,
    ):
        self._distance = distance_metric
        self._embedder = embedder
        self._weights = weights or DistanceWeights()
        self._tau_per_tier = dict(tau_per_tier or _DEFAULT_TAU_PER_TIER)
        self._w_topic = relevance_w_topic
        self._w_type = relevance_w_type
        self._epsilon = epsilon
        self._ndcg_ks = tuple(ndcg_ks)

    def evaluate(self, dataset: BenchmarkDataset) -> BenchmarkResult:
        """Run every example in ``dataset`` and return aggregated metrics."""
        overall = _RunningCounts()
        per_tier: dict = {}     # Tier -> _RunningCounts
        example_outcomes: list = []
        ranking_accumulator: list = []   # list of (map, ndcg_at_k dict)

        for example in dataset.examples:
            example_outcome, candidate_scores = self._evaluate_example(example)
            example_outcomes.append(example_outcome)

            for outcome in example_outcome.candidate_outcomes:
                overall = overall.add(outcome.expected_admit, outcome.actual_admit)
                tier_counts = per_tier.get(outcome.tier, _RunningCounts())
                per_tier[outcome.tier] = tier_counts.add(
                    outcome.expected_admit, outcome.actual_admit,
                )

            rmetrics = _ranked_metrics_for_example(
                example, candidate_scores, self._ndcg_ks,
            )
            if rmetrics is not None:
                ranking_accumulator.append(rmetrics)

        return BenchmarkResult(
            dataset_name=dataset.name,
            examples_evaluated=len(dataset.examples),
            overall_metrics=self._counts_to_metrics(None, overall),
            tier_metrics={
                tier: self._counts_to_metrics(tier, counts)
                for tier, counts in per_tier.items()
            },
            ranking_metrics=self._aggregate_ranking(ranking_accumulator),
            per_example_outcomes=tuple(example_outcomes),
        )

    # ---- per-example / per-candidate ----

    def _evaluate_example(
        self, example: BenchmarkExample,
    ) -> tuple:
        """Score every candidate in one example.

        Returns ``(ExampleOutcome, {candidate_id: score})``. The
        score map drives the ranking metrics computation in the
        outer loop.
        """
        outcomes: list = []
        scores: dict = {}
        q_emb = self._embedder(example.query.text)

        for candidate in example.candidates:
            outcome = self._evaluate_candidate(example.query, q_emb, candidate)
            outcomes.append(outcome)
            scores[candidate.id] = outcome.score

        return (
            ExampleOutcome(
                example_id=example.example_id,
                candidate_outcomes=tuple(outcomes),
            ),
            scores,
        )

    def _evaluate_candidate(
        self,
        query,
        query_embedding: list,
        candidate: BenchmarkCandidate,
    ) -> CandidateOutcome:
        c_emb = self._embedder(candidate.text)

        components = self._distance.components(
            query_embedding=query_embedding,
            claim_embedding=c_emb,
            query_tags=list(query.tags),
            query_text=query.text,
            claim_text=candidate.text,
            claim_node_id=candidate.id,
        )
        composite_distance = components.composite(self._weights)

        # Relevance per router-distance.md §relevance(Q, C)
        cos_similarity = 1.0 - self._distance.d_embed(query_embedding, c_emb)
        cos_similarity = max(0.0, min(1.0, cos_similarity))
        type_score = _tag_match(query.tags, candidate.tags)
        relevance = self._w_topic * cos_similarity + self._w_type * type_score
        relevance = max(0.0, min(1.0, relevance))

        # Admission criterion
        score = (candidate.trust * relevance) / (composite_distance + self._epsilon)
        tau = self._tau_per_tier.get(candidate.tier, 0.5)
        admit = score >= tau

        return CandidateOutcome(
            candidate_id=candidate.id,
            tier=candidate.tier,
            expected_admit=candidate.expected_admit,
            actual_admit=admit,
            score=score,
            composite_distance=composite_distance,
            relevance=relevance,
            trust=candidate.trust,
            tau=tau,
        )

    # ---- aggregation helpers ----

    @staticmethod
    def _counts_to_metrics(
        tier: Optional[Tier], counts: _RunningCounts,
    ) -> TierMetrics:
        return TierMetrics(
            tier=tier,
            true_positives=counts.tp,
            false_positives=counts.fp,
            true_negatives=counts.tn,
            false_negatives=counts.fn,
        )

    def _aggregate_ranking(self, accumulator: list) -> Optional[RankingMetrics]:
        if not accumulator:
            return None
        n = len(accumulator)
        avg_map = sum(r["map"] for r in accumulator) / n
        ndcg_aggregated: dict = {}
        for k in self._ndcg_ks:
            ks = [r["ndcg_at_k"].get(k, 0.0) for r in accumulator]
            ndcg_aggregated[k] = sum(ks) / n
        return RankingMetrics(
            map_score=avg_map,
            ndcg_at_k=ndcg_aggregated,
            examples_with_ranking=n,
        )


