"""
Smoke tests for maestro/router/distance.py — DistanceMetric.

Step 3 scope: GraphView injection into the constructor.
Step 4 scope: BFS body of d_graph (multi-source, max_hops=6 default,
1 - exp(-hops/k) normalization with k=3.0 default).

These tests pin both the dispatch plumbing (step 3) and the
traversal correctness (step 4). Option R semantics are preserved:
under NullGraphView, d_graph returns graph_stub_value directly; the
BFS only runs when a real GraphView is wired.
"""

import math
from typing import Iterable

import pytest

from maestro.router.distance import (
    DistanceComponents,
    DistanceMetric,
    DistanceWeights,
)
from maestro.router.graph import (
    EdgeType,
    GraphEdge,
    GraphView,
    NullGraphView,
)


# ---- a minimal real GraphView used to verify "real view" storage ----


class StubGraphView(GraphView):
    """Concrete (non-Null) GraphView used purely to assert that
    DistanceMetric stores it. Returns no edges and no anchors;
    forces the BFS into the no-anchor / no-path code paths.
    """

    def neighbors(self, node_id: str) -> Iterable[GraphEdge]:
        return ()

    def anchors_for_tags(self, tags: Iterable[str]) -> Iterable[str]:
        return ()


# ---- a hand-built fake graph for BFS tests ----


class FakeGraph(GraphView):
    """In-memory adjacency map. Edges are bidirectional at lookup
    time: neighbors(X) returns every edge incident to X, regardless
    of which end is src.

    add_edge(a, b) stores the edge under both endpoints so the BFS
    sees it from either direction. Anchors are explicit per
    ``add_anchor(tag, node_id)``.
    """

    def __init__(self):
        self._adj: dict = {}                  # node -> list[GraphEdge]
        self._anchors_by_tag: dict = {}       # tag -> list[node_id]

    def add_edge(self, a: str, b: str, edge_type: EdgeType = EdgeType.SHARED_TAG):
        edge = GraphEdge(src=a, dst=b, edge_type=edge_type)
        self._adj.setdefault(a, []).append(edge)
        self._adj.setdefault(b, []).append(edge)

    def add_anchor(self, tag: str, node_id: str):
        self._anchors_by_tag.setdefault(tag, []).append(node_id)

    def neighbors(self, node_id: str) -> Iterable[GraphEdge]:
        return list(self._adj.get(node_id, ()))

    def anchors_for_tags(self, tags: Iterable[str]) -> Iterable[str]:
        out = []
        seen: set = set()
        for tag in tags:
            for node in self._anchors_by_tag.get(tag, ()):
                if node not in seen:
                    seen.add(node)
                    out.append(node)
        return out


# ---- step 3 invariants ----


def test_default_constructor_uses_null_graph_view():
    dm = DistanceMetric()
    assert isinstance(dm._graph, NullGraphView)


def test_explicit_none_graph_view_is_replaced_with_null():
    dm = DistanceMetric(graph_view=None)
    assert isinstance(dm._graph, NullGraphView)


def test_explicit_graph_view_is_stored_as_is():
    fake = StubGraphView()
    dm = DistanceMetric(graph_view=fake)
    assert dm._graph is fake


def test_d_graph_returns_stub_under_null_graph_view():
    """Option R: today's behavior preserved when no graph is wired.

    Without a real graph view, d_graph returns graph_stub_value
    directly without invoking the BFS.
    """
    dm = DistanceMetric(graph_stub_value=0.42)
    assert dm.d_graph(query_tags=["anything"], claim_node_id="CART:x@1") == 0.42


# ---- step 4: BFS correctness ----


def _normalized(hops: int, k: float = 3.0) -> float:
    return 1.0 - math.exp(-hops / k)


def test_bfs_returns_one_when_no_anchors_resolve():
    g = FakeGraph()
    g.add_edge("A", "B")  # graph has structure but no anchors registered
    dm = DistanceMetric(graph_view=g)
    assert dm.d_graph(query_tags=["unknown"], claim_node_id="B") == 1.0


def test_bfs_returns_zero_when_claim_is_an_anchor():
    g = FakeGraph()
    g.add_anchor("law.us", "TAG:law.us")
    dm = DistanceMetric(graph_view=g)
    assert dm.d_graph(query_tags=["law.us"], claim_node_id="TAG:law.us") == 0.0


def test_bfs_returns_one_hop_normalized_value():
    g = FakeGraph()
    g.add_anchor("law.us", "TAG:law.us")
    g.add_edge("TAG:law.us", "CART:fed@1")
    dm = DistanceMetric(graph_view=g)
    got = dm.d_graph(query_tags=["law.us"], claim_node_id="CART:fed@1")
    assert math.isclose(got, _normalized(1), rel_tol=1e-9)


def test_bfs_returns_one_when_unreachable():
    g = FakeGraph()
    g.add_anchor("law.us", "TAG:law.us")
    g.add_edge("TAG:law.us", "CART:fed@1")
    # claim node has no edges into the graph
    dm = DistanceMetric(graph_view=g)
    assert dm.d_graph(query_tags=["law.us"], claim_node_id="CART:isolated@1") == 1.0


def test_bfs_returns_one_past_max_hops():
    g = FakeGraph()
    g.add_anchor("t", "TAG:t")
    # build a chain TAG:t -> N1 -> N2 -> ... -> N7 (7 hops away)
    chain = ["TAG:t"] + [f"N{i}" for i in range(1, 8)]
    for a, b in zip(chain, chain[1:]):
        g.add_edge(a, b)
    dm = DistanceMetric(graph_view=g, max_hops=6)
    # N6 (6 hops away) is reachable
    assert math.isclose(
        dm.d_graph(query_tags=["t"], claim_node_id="N6"),
        _normalized(6),
        rel_tol=1e-9,
    )
    # N7 (7 hops away) exceeds max_hops -> 1.0
    assert dm.d_graph(query_tags=["t"], claim_node_id="N7") == 1.0


def test_bfs_max_hops_is_configurable():
    g = FakeGraph()
    g.add_anchor("t", "TAG:t")
    g.add_edge("TAG:t", "N1")
    g.add_edge("N1", "N2")
    g.add_edge("N2", "N3")
    g.add_edge("N3", "N4")
    # max_hops=2: N3 (3 hops) is unreachable
    dm = DistanceMetric(graph_view=g, max_hops=2)
    assert dm.d_graph(query_tags=["t"], claim_node_id="N3") == 1.0
    # max_hops=4: N3 is reachable at 3 hops
    dm = DistanceMetric(graph_view=g, max_hops=4)
    assert math.isclose(
        dm.d_graph(query_tags=["t"], claim_node_id="N3"),
        _normalized(3),
        rel_tol=1e-9,
    )


def test_bfs_normalization_k_is_configurable():
    g = FakeGraph()
    g.add_anchor("t", "TAG:t")
    g.add_edge("TAG:t", "N1")
    # k=3 (default) -> 1-exp(-1/3) ≈ 0.2835
    dm3 = DistanceMetric(graph_view=g, normalization_k=3.0)
    # k=1 -> 1-exp(-1) ≈ 0.6321
    dm1 = DistanceMetric(graph_view=g, normalization_k=1.0)
    got3 = dm3.d_graph(query_tags=["t"], claim_node_id="N1")
    got1 = dm1.d_graph(query_tags=["t"], claim_node_id="N1")
    assert math.isclose(got3, 1 - math.exp(-1 / 3), rel_tol=1e-9)
    assert math.isclose(got1, 1 - math.exp(-1), rel_tol=1e-9)
    # smaller k makes a single hop look further
    assert got1 > got3


def test_bfs_multi_source_picks_shortest_path():
    """Two anchors, one near and one far. BFS must report the
    minimum hop count from either source.
    """
    g = FakeGraph()
    g.add_anchor("a", "ANCHOR_A")
    g.add_anchor("b", "ANCHOR_B")
    # ANCHOR_A is 4 hops from CLAIM
    g.add_edge("ANCHOR_A", "X1")
    g.add_edge("X1", "X2")
    g.add_edge("X2", "X3")
    g.add_edge("X3", "CLAIM")
    # ANCHOR_B is 1 hop from CLAIM
    g.add_edge("ANCHOR_B", "CLAIM")

    dm = DistanceMetric(graph_view=g)
    got = dm.d_graph(query_tags=["a", "b"], claim_node_id="CLAIM")
    # multi-source BFS reports the 1-hop result, not the 4-hop one
    assert math.isclose(got, _normalized(1), rel_tol=1e-9)


def test_bfs_visits_each_node_once():
    """A diamond graph has two equally-short paths to the claim.
    The BFS visited-set must keep neighbor expansion correct without
    revisiting nodes. The result should be the shortest hop count.
    """
    g = FakeGraph()
    g.add_anchor("t", "TAG:t")
    # diamond: TAG:t -> {L, R} -> CLAIM
    g.add_edge("TAG:t", "L")
    g.add_edge("TAG:t", "R")
    g.add_edge("L", "CLAIM")
    g.add_edge("R", "CLAIM")
    dm = DistanceMetric(graph_view=g)
    got = dm.d_graph(query_tags=["t"], claim_node_id="CLAIM")
    assert math.isclose(got, _normalized(2), rel_tol=1e-9)


# ---- step 5: d_embed (cosine distance) ----


def test_d_embed_identical_vectors_zero():
    dm = DistanceMetric()
    assert dm.d_embed([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 0.0


def test_d_embed_orthogonal_vectors_one():
    dm = DistanceMetric()
    got = dm.d_embed([1.0, 0.0], [0.0, 1.0])
    assert math.isclose(got, 1.0, rel_tol=1e-9)


def test_d_embed_anti_correlated_clamped_to_one():
    """cos(θ) = -1 produces 1 - (-1) = 2 raw; the clamp brings
    it back to 1.0.
    """
    dm = DistanceMetric()
    assert dm.d_embed([1.0, 0.0], [-1.0, 0.0]) == 1.0


def test_d_embed_known_intermediate_value():
    """[1, 1] vs [1, 0] => cos = 1/sqrt(2), distance = 1 - 1/sqrt(2)."""
    dm = DistanceMetric()
    got = dm.d_embed([1.0, 1.0], [1.0, 0.0])
    expected = 1.0 - 1.0 / math.sqrt(2.0)
    assert math.isclose(got, expected, rel_tol=1e-9)


def test_d_embed_empty_vectors_max_distance():
    dm = DistanceMetric()
    assert dm.d_embed([], [1.0, 2.0]) == 1.0
    assert dm.d_embed([1.0, 2.0], []) == 1.0
    assert dm.d_embed([], []) == 1.0


def test_d_embed_zero_norm_max_distance():
    """A zero vector has undefined direction; treated as max distance."""
    dm = DistanceMetric()
    assert dm.d_embed([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) == 1.0
    assert dm.d_embed([1.0, 2.0, 3.0], [0.0, 0.0, 0.0]) == 1.0


def test_d_embed_dimension_mismatch_raises():
    dm = DistanceMetric()
    with pytest.raises(ValueError):
        dm.d_embed([1.0, 2.0], [1.0, 2.0, 3.0])


# ---- step 5: DistanceComponents.composite ----


def test_composite_zero_components_zero_distance():
    c = DistanceComponents(d_embed=0.0, d_graph=0.0, d_causal=0.0, d_counter=0.0)
    assert c.composite(DistanceWeights()) == 0.0


def test_composite_max_components_max_distance():
    """All components 1.0 with default weights summing to 1.0
    yields composite 1.0.
    """
    c = DistanceComponents(d_embed=1.0, d_graph=1.0, d_causal=1.0, d_counter=1.0)
    assert math.isclose(c.composite(DistanceWeights()), 1.0, rel_tol=1e-9)


def test_composite_default_weighted_sum():
    """Defaults: w_embed=0.7, w_graph=0.15, w_causal=0.1, w_counter=0.05."""
    c = DistanceComponents(d_embed=0.5, d_graph=0.4, d_causal=0.3, d_counter=0.2)
    expected = 0.7 * 0.5 + 0.15 * 0.4 + 0.1 * 0.3 + 0.05 * 0.2
    assert math.isclose(c.composite(DistanceWeights()), expected, rel_tol=1e-9)


def test_composite_custom_weights():
    c = DistanceComponents(d_embed=1.0, d_graph=0.0, d_causal=0.0, d_counter=0.0)
    w = DistanceWeights(w_embed=1.0, w_graph=0.0, w_causal=0.0, w_counter=0.0)
    assert c.composite(w) == 1.0


def test_composite_clamps_overshoot():
    """Defensive: misconfigured weights summing to > 1.0 with
    components at 1.0 would give > 1.0 raw; the clamp prevents
    that from leaking out.
    """
    c = DistanceComponents(d_embed=1.0, d_graph=1.0, d_causal=1.0, d_counter=1.0)
    w = DistanceWeights(w_embed=1.0, w_graph=1.0, w_causal=1.0, w_counter=1.0)
    assert c.composite(w) == 1.0


# ---- step 5: DistanceMetric.components ----


def test_components_returns_distance_components_under_null_graph():
    """Under NullGraphView the d_graph slot reflects the stub
    constant; the other slots reflect their respective live or
    stub implementations.
    """
    dm = DistanceMetric(
        graph_stub_value=0.55,
        causal_stub_value=0.31,
        counter_stub_value=0.27,
    )
    out = dm.components(
        query_embedding=[1.0, 0.0],
        claim_embedding=[0.0, 1.0],   # orthogonal -> d_embed = 1.0
        query_tags=["irrelevant"],
        query_text="q",
        claim_text="c",
        claim_node_id="CART:doesnt-matter@1",
    )
    assert isinstance(out, DistanceComponents)
    assert out.d_embed == 1.0
    assert out.d_graph == 0.55
    assert out.d_causal == 0.31
    assert out.d_counter == 0.27


def test_components_uses_bfs_under_real_graph_view():
    g = FakeGraph()
    g.add_anchor("law.us", "TAG:law.us")
    g.add_edge("TAG:law.us", "CART:fed@1")
    dm = DistanceMetric(graph_view=g, causal_stub_value=0.0, counter_stub_value=0.0)
    out = dm.components(
        query_embedding=[1.0, 1.0],
        claim_embedding=[1.0, 1.0],   # identical -> d_embed = 0.0
        query_tags=["law.us"],
        query_text="q",
        claim_text="c",
        claim_node_id="CART:fed@1",   # one hop away
    )
    assert out.d_embed == 0.0
    assert math.isclose(out.d_graph, _normalized(1), rel_tol=1e-9)
    assert out.d_causal == 0.0
    assert out.d_counter == 0.0


def test_components_into_composite_end_to_end():
    """Round-trip: build components from inputs, ask the resulting
    DistanceComponents to collapse into a composite under the
    metric's own weights.
    """
    g = FakeGraph()
    g.add_anchor("t", "TAG:t")
    g.add_edge("TAG:t", "CLAIM")
    dm = DistanceMetric(
        graph_view=g,
        graph_stub_value=0.0,
        causal_stub_value=0.0,
        counter_stub_value=0.0,
    )
    out = dm.components(
        query_embedding=[1.0, 0.0],
        claim_embedding=[1.0, 0.0],   # identical -> d_embed = 0.0
        query_tags=["t"],
        query_text="q",
        claim_text="c",
        claim_node_id="CLAIM",        # one hop away
    )
    composite = out.composite(DistanceWeights())
    # only d_graph contributes; expected = 0.15 * (1 - exp(-1/3))
    expected = 0.15 * _normalized(1)
    assert math.isclose(composite, expected, rel_tol=1e-9)


# ---- track A: d_counter live (perturbed-query counterfactual) ----


def _hash_embedder(dim: int = 16):
    """Deterministic test embedder. Same text -> same vector;
    different text -> different vector. Not semantic but lets
    d_counter's math be tested end-to-end without a real
    embedding service.
    """
    import hashlib

    def embed(text: str):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[:dim]]

    return embed


def test_d_counter_returns_stub_when_no_embedder():
    dm = DistanceMetric(counter_stub_value=0.42)
    assert dm.d_counter("any query text here", "claim text") == 0.42


def test_d_counter_returns_stub_for_too_short_query():
    """A query of < 3 words can't be meaningfully word-dropped;
    fall back to the stub.
    """
    dm = DistanceMetric(
        embedder=_hash_embedder(),
        counter_stub_value=0.13,
    )
    assert dm.d_counter("short", "claim") == 0.13
    assert dm.d_counter("two words", "claim") == 0.13
    # Three words is the threshold; should NOT return stub
    assert dm.d_counter("three words now", "claim") != 0.13


def test_d_counter_in_unit_interval():
    dm = DistanceMetric(embedder=_hash_embedder())
    out = dm.d_counter("a query with reasonable length here", "the claim")
    assert 0.0 <= out <= 1.0


def test_d_counter_deterministic_for_fixed_seed():
    """Same seed + same query + same claim + same embedder
    produces the same result.
    """
    dm1 = DistanceMetric(embedder=_hash_embedder(), perturbation_seed=42)
    dm2 = DistanceMetric(embedder=_hash_embedder(), perturbation_seed=42)
    a = dm1.d_counter("a query with several content words", "the claim text")
    b = dm2.d_counter("a query with several content words", "the claim text")
    assert a == b


def test_d_counter_changes_with_seed():
    """Different perturbation_seed picks different word-drop
    indices, which generally produces different shifts.
    """
    q = "a longer query with many distinct content words to perturb"
    c = "claim text under examination"
    dm0 = DistanceMetric(embedder=_hash_embedder(), perturbation_seed=0)
    dm1 = DistanceMetric(embedder=_hash_embedder(), perturbation_seed=1)
    a = dm0.d_counter(q, c)
    b = dm1.d_counter(q, c)
    assert a != b


def test_d_counter_nonzero_for_typical_query():
    """With a hash-based embedder, perturbations land in totally
    different vector space than the original query, so the
    average shift is reliably non-zero.
    """
    dm = DistanceMetric(embedder=_hash_embedder())
    out = dm.d_counter("a query with several distinct words", "claim text")
    assert out > 0.0


def test_d_counter_perturbation_count_zero_falls_back_to_stub():
    """perturbation_count=0 means no perturbations; fall back
    to the stub.
    """
    dm = DistanceMetric(
        embedder=_hash_embedder(),
        perturbation_count=0,
        counter_stub_value=0.5,
    )
    out = dm.d_counter("a query with content", "claim")
    # The list comprehension produces zero items; shifts is empty;
    # we hit the empty-shifts fallback that returns the stub.
    assert out == 0.5


def test_d_counter_embedder_failure_falls_back_to_stub():
    def crashing_embedder(text):
        raise RuntimeError("embedder is offline")

    dm = DistanceMetric(embedder=crashing_embedder, counter_stub_value=0.7)
    assert dm.d_counter("a longer query here", "claim") == 0.7


def test_d_counter_partial_embedder_failure_drops_those_perturbations():
    """If the embedder fails for SOME perturbations but succeeds
    for others, the failed perturbations are skipped and the
    average uses only the successful ones.
    """
    base_emb = _hash_embedder()
    call_count = {"n": 0}

    def flaky_embedder(text):
        call_count["n"] += 1
        # Fail on every third embedder call (after the original query
        # and claim succeed)
        if call_count["n"] >= 3 and call_count["n"] % 2 == 1:
            raise RuntimeError("transient")
        return base_emb(text)

    dm = DistanceMetric(embedder=flaky_embedder, perturbation_count=5)
    out = dm.d_counter("a longer query with several content words", "claim")
    # Result is in [0, 1]; the exact value depends on which
    # perturbations made it through but the call must not raise
    assert 0.0 <= out <= 1.0


def test_d_counter_total_embedder_failure_via_partial_falls_back():
    """If every per-perturbation embedder call fails (but the
    initial query/claim embeds succeeded), shifts is empty and
    we fall back to the stub.
    """
    base_emb = _hash_embedder()
    call_count = {"n": 0}

    def per_perturbation_failing_embedder(text):
        call_count["n"] += 1
        # Allow the first two calls (query + claim) to succeed,
        # then fail on every subsequent call (the perturbations)
        if call_count["n"] <= 2:
            return base_emb(text)
        raise RuntimeError("perturbation embedder offline")

    dm = DistanceMetric(
        embedder=per_perturbation_failing_embedder,
        counter_stub_value=0.99,
    )
    assert dm.d_counter("a longer query with several content words", "claim") == 0.99


def test_d_counter_perturb_query_helper_drops_correct_count():
    """Validate the word-dropout helper directly: at 25% drop, a
    12-word query produces perturbations of length 9.
    """
    dm = DistanceMetric(embedder=_hash_embedder(), perturbation_drop_fraction=0.25)
    perturbations = dm._perturb_query(
        "the quick brown fox jumps over the lazy dog and then leaves"
    )
    assert len(perturbations) == 5  # default perturbation_count
    for p in perturbations:
        words = p.split()
        # 12 words * 0.25 = 3 dropped -> 9 remaining
        assert len(words) == 9


def test_d_counter_perturb_query_helper_returns_empty_for_short_query():
    dm = DistanceMetric(embedder=_hash_embedder())
    assert dm._perturb_query("two words") == []
    assert dm._perturb_query("one") == []
    assert dm._perturb_query("") == []


def test_d_counter_perturb_query_caps_drop_count():
    """Even with drop_fraction=1.0, the helper must always leave
    at least one word so the perturbation isn't an empty string.
    """
    dm = DistanceMetric(
        embedder=_hash_embedder(),
        perturbation_drop_fraction=1.0,
        perturbation_count=3,
    )
    perturbations = dm._perturb_query("five words in this query")
    assert len(perturbations) == 3
    for p in perturbations:
        assert len(p.split()) == 1   # always 1 word remains


def test_components_uses_live_d_counter_when_embedder_is_set():
    """End-to-end: components() invokes the live d_counter and
    the result is non-stub.
    """
    dm = DistanceMetric(
        embedder=_hash_embedder(),
        counter_stub_value=0.5,   # so we can tell stub from live
    )
    out = dm.components(
        query_embedding=[1.0, 0.0],
        claim_embedding=[0.0, 1.0],
        query_tags=["t"],
        query_text="a query with several content words",
        claim_text="the claim text under examination",
        claim_node_id="CART:irrelevant@1",
    )
    # d_counter result is the live value, not the stub.
    # (Vanishingly unlikely to coincidentally equal 0.5 with a
    # hash-based embedder.)
    assert out.d_counter != 0.5
    assert 0.0 <= out.d_counter <= 1.0


def test_components_uses_stub_d_counter_when_no_embedder():
    """Inverse of the above: with embedder=None (the default),
    components() reflects the stub on d_counter.
    """
    dm = DistanceMetric(counter_stub_value=0.37)
    out = dm.components(
        query_embedding=[1.0, 0.0],
        claim_embedding=[0.0, 1.0],
        query_tags=["t"],
        query_text="any query text",
        claim_text="any claim text",
        claim_node_id="CART:x@1",
    )
    assert out.d_counter == 0.37


def test_distance_weights_default_unchanged():
    """Sanity: step 3 must not perturb the weight defaults that the
    composite formula depends on.
    """
    dm = DistanceMetric()
    w = dm._weights
    assert w.w_embed == 0.7
    assert w.w_graph == 0.15
    assert w.w_causal == 0.1
    assert w.w_counter == 0.05


def test_other_stubs_still_return_their_constants():
    """d_causal and d_counter remain stubs; they are not affected
    by the graph_view injection.
    """
    dm = DistanceMetric(causal_stub_value=0.31, counter_stub_value=0.27)
    assert dm.d_causal("query", "claim") == 0.31
    assert dm.d_counter("query", "claim") == 0.27


def test_graph_view_injection_does_not_affect_other_components():
    """Construction with a real GraphView must leave the
    causal/counter stubs intact and the weights default-bound.
    """
    dm = DistanceMetric(graph_view=StubGraphView(),
                        causal_stub_value=0.11,
                        counter_stub_value=0.22)
    assert dm.d_causal("a", "b") == 0.11
    assert dm.d_counter("a", "b") == 0.22
    assert isinstance(dm._weights, DistanceWeights)
