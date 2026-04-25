"""
Smoke tests for maestro/router/distance.py — DistanceMetric.

Step 3 scope: GraphView injection into the constructor. The actual
BFS body of d_graph lands in step 4; these tests pin the dispatch
plumbing introduced in step 3 (option R semantics: NullGraphView
default, stub-constant fallback under NullGraphView, real-view
storage when one is supplied).
"""

from typing import Iterable

from maestro.router.distance import DistanceMetric, DistanceWeights
from maestro.router.graph import (
    GraphEdge,
    GraphView,
    NullGraphView,
)


# ---- a minimal real GraphView used to verify "real view" storage ----


class StubGraphView(GraphView):
    """Concrete (non-Null) GraphView used purely to assert that
    DistanceMetric stores it. Returns no edges and no anchors; the
    BFS is wired in step 4.
    """

    def neighbors(self, node_id: str) -> Iterable[GraphEdge]:
        return ()

    def anchors_for_tags(self, tags: Iterable[str]) -> Iterable[str]:
        return ()


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
    directly without invoking the (yet-to-be-written) BFS.
    """
    dm = DistanceMetric(graph_stub_value=0.42)
    assert dm.d_graph(query_tags=[], claim_tags=[], claim_manifest_hash=None) == 0.42


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
