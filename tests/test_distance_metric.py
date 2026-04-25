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

from maestro.router.distance import DistanceMetric, DistanceWeights
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
