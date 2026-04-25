"""
Smoke tests for maestro/router/graph.py CompositeGraphView.

Uses in-memory fakes for the Librarian and Whirlpool surfaces so the
graph layer can be validated independently of the still-stubbed
storage backends. The fakes implement only the methods
CompositeGraphView calls.

Coverage:
  - known-tags aggregation across Librarian + Whirlpool
  - exact-tag anchor resolution
  - longest-prefix fallback on dotted tags
  - flat-unknown drop
  - cartridge neighbors: SUPERSEDES + REVOKES + SHARED_TAG
  - whirlpool-item neighbors: SHARED_TAG + SHARED_CORROBORATOR
  - tag neighbors: cross-tier SHARED_TAG
  - lazy cache: second neighbors() call hits the cache, not the store
  - invalidate(): clears cache and rebuilds known_tags

NullGraphView is also exercised to confirm the abstract contract.
"""

from dataclasses import dataclass, field

import pytest

from maestro.router.graph import (
    CompositeGraphView,
    EdgeType,
    GraphEdge,
    GraphView,
    NullGraphView,
    NodeKind,
    _short_item_slug,
)


# ---------- in-memory fakes ----------


@dataclass
class FakeManifest:
    cartridge_id: str
    version: str
    domain_tags: list = field(default_factory=list)


@dataclass
class FakeRef:
    cartridge_id: str
    version: str


@dataclass
class FakeProv:
    source_id: str


@dataclass
class FakeItem:
    item_id: str
    domain_tags: list = field(default_factory=list)
    provenance: list = field(default_factory=list)


class FakeLibrarian:
    """Minimal stand-in for maestro.librarian.store.Librarian."""

    def __init__(self):
        self._manifests: dict = {}        # slug -> FakeManifest
        self._supersedes: dict = {}       # slug -> [target_slug, ...]
        self._revokes: dict = {}          # slug -> [target_slug, ...]
        # call counters (used to verify caching)
        self.calls_get_by_slug = 0
        self.calls_supersedes = 0
        self.calls_revokes = 0
        self.calls_cartridges_with_tag = 0
        self.calls_known_tags = 0

    def add(self, manifest: FakeManifest, supersedes=(), revokes=()):
        slug = f"CART:{manifest.cartridge_id}@{manifest.version}"
        self._manifests[slug] = manifest
        self._supersedes[slug] = list(supersedes)
        self._revokes[slug] = list(revokes)

    def known_tags(self) -> set:
        self.calls_known_tags += 1
        out: set = set()
        for m in self._manifests.values():
            out.update(m.domain_tags)
        return out

    def get_by_slug(self, slug: str):
        self.calls_get_by_slug += 1
        return self._manifests.get(slug)

    def supersedes_slugs(self, slug: str) -> list:
        self.calls_supersedes += 1
        return list(self._supersedes.get(slug, ()))

    def revokes_slugs(self, slug: str) -> list:
        self.calls_revokes += 1
        return list(self._revokes.get(slug, ()))

    def cartridges_with_tag(self, tag: str):
        self.calls_cartridges_with_tag += 1
        for slug, m in self._manifests.items():
            if tag in m.domain_tags:
                yield FakeRef(cartridge_id=m.cartridge_id, version=m.version)


class FakeWhirlpool:
    """Minimal stand-in for maestro.whirlpool.whirlpool.Whirlpool."""

    def __init__(self, whirlpool_id: str):
        self.whirlpool_id = whirlpool_id
        self._items: dict = {}            # short_slug -> FakeItem
        self.calls_get_by_slug = 0
        self.calls_items_with_tag = 0
        self.calls_items_with_source = 0
        self.calls_known_tags = 0

    def add(self, item: FakeItem):
        self._items[_short_item_slug(item.item_id)] = item

    def known_tags(self) -> set:
        self.calls_known_tags += 1
        out: set = set()
        for it in self._items.values():
            out.update(it.domain_tags)
        return out

    def iter_items(self):
        return iter(self._items.values())

    def get_by_slug(self, short: str):
        self.calls_get_by_slug += 1
        return self._items.get(short)

    def items_with_tag(self, tag: str):
        self.calls_items_with_tag += 1
        for it in self._items.values():
            if tag in it.domain_tags:
                yield it

    def items_with_source(self, source_id: str):
        self.calls_items_with_source += 1
        for it in self._items.values():
            if any(p.source_id == source_id for p in it.provenance):
                yield it


# ---------- NullGraphView contract ----------


def test_null_graph_view_is_abstract_contract():
    null = NullGraphView()
    assert isinstance(null, GraphView)
    assert list(null.neighbors("CART:anything@1")) == []
    assert list(null.anchors_for_tags(["law.us"])) == []


def test_graph_view_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        GraphView()  # abstract methods


# ---------- known-tags aggregation ----------


def test_known_tags_unions_librarian_and_whirlpool():
    lib = FakeLibrarian()
    lib.add(FakeManifest("si-prefixes", "2024.01.01",
                         domain_tags=["unit.si", "math.dim"]))
    wp = FakeWhirlpool("law-feed")
    wp.add(FakeItem("sha256:a7f3c20100000000",
                    domain_tags=["law.us.federal"]))
    g = CompositeGraphView(lib, [wp])

    tags = g._known_tags
    assert "unit.si" in tags
    assert "math.dim" in tags
    assert "law.us.federal" in tags


# ---------- anchor resolution ----------


def _build_anchors_graph():
    lib = FakeLibrarian()
    lib.add(FakeManifest("rfc9110", "rfc-2022-06",
                         domain_tags=["proto.http", "proto.http.semantics"]))
    wp = FakeWhirlpool("legal-feed")
    wp.add(FakeItem("sha256:b1b1b1b1deadbeef",
                    domain_tags=["law.us"]))
    return CompositeGraphView(lib, [wp])


def test_exact_tag_anchor():
    g = _build_anchors_graph()
    assert list(g.anchors_for_tags(["proto.http"])) == ["TAG:proto.http"]


def test_longest_prefix_fallback_on_dotted_tag():
    g = _build_anchors_graph()
    # exact "law.us.state.california" is unknown; "law.us" is known
    out = list(g.anchors_for_tags(["law.us.state.california"]))
    assert out == ["TAG:law.us"]


def test_flat_unknown_tag_drops_silently():
    g = _build_anchors_graph()
    assert list(g.anchors_for_tags(["completely-unknown"])) == []


def test_anchor_dedup_across_input_tags():
    g = _build_anchors_graph()
    # both inputs fall back to the same parent anchor
    out = list(g.anchors_for_tags([
        "law.us.california", "law.us.federal",
    ]))
    assert out == ["TAG:law.us"]


# ---------- cartridge neighbors ----------


def test_cartridge_neighbors_emit_supersedes_revokes_and_tags():
    lib = FakeLibrarian()
    lib.add(FakeManifest("si", "v1", domain_tags=["unit.si"]))
    lib.add(FakeManifest("si", "v2",
                         domain_tags=["unit.si", "unit.si.prefix"]),
            supersedes=["CART:si@v1"],
            revokes=["CART:si-old@v0"])
    g = CompositeGraphView(lib, [])

    edges = list(g.neighbors("CART:si@v2"))
    types = [e.edge_type for e in edges]
    targets = {e.dst for e in edges}

    assert EdgeType.SUPERSEDES in types
    assert EdgeType.REVOKES in types
    assert types.count(EdgeType.SHARED_TAG) == 2
    assert "CART:si@v1" in targets
    assert "CART:si-old@v0" in targets
    assert "TAG:unit.si" in targets
    assert "TAG:unit.si.prefix" in targets


def test_cartridge_neighbors_unknown_slug_returns_empty():
    lib = FakeLibrarian()
    g = CompositeGraphView(lib, [])
    assert list(g.neighbors("CART:does-not-exist@1")) == []


# ---------- whirlpool-item neighbors ----------


def test_whirlpool_item_neighbors_emit_tags_and_corroborators():
    wp = FakeWhirlpool("law")
    item_a = FakeItem(
        "sha256:aaaaaaaa11111111",
        domain_tags=["law.us.federal"],
        provenance=[FakeProv("nytimes.com"), FakeProv("reuters.com")],
    )
    item_b = FakeItem(
        "sha256:bbbbbbbb22222222",
        domain_tags=["law.us.federal"],
        provenance=[FakeProv("nytimes.com")],
    )
    item_c = FakeItem(
        "sha256:cccccccc33333333",
        domain_tags=["law.us.federal"],
        provenance=[FakeProv("ap.org")],   # no overlap with item_a
    )
    wp.add(item_a)
    wp.add(item_b)
    wp.add(item_c)
    g = CompositeGraphView(None, [wp])

    edges = list(g.neighbors("WP:law:aaaaaaaa"))
    type_counts: dict = {}
    for e in edges:
        type_counts[e.edge_type] = type_counts.get(e.edge_type, 0) + 1

    # one SHARED_TAG (one tag), one SHARED_CORROBORATOR (item_b),
    # item_c has no shared source so no edge to it
    assert type_counts.get(EdgeType.SHARED_TAG) == 1
    assert type_counts.get(EdgeType.SHARED_CORROBORATOR) == 1

    targets = {e.dst for e in edges}
    assert "WP:law:bbbbbbbb" in targets
    assert "WP:law:cccccccc" not in targets


def test_whirlpool_item_self_excluded_from_corroborators():
    wp = FakeWhirlpool("feed")
    only_one = FakeItem(
        "sha256:1234567800000000",
        domain_tags=["x.y"],
        provenance=[FakeProv("source-1")],
    )
    wp.add(only_one)
    g = CompositeGraphView(None, [wp])

    edges = list(g.neighbors("WP:feed:12345678"))
    # self-edges must not be emitted even though items_with_source
    # would include the item itself
    self_targets = [e for e in edges if e.dst == "WP:feed:12345678"]
    assert self_targets == []


# ---------- tag neighbors (cross-tier) ----------


def test_tag_neighbors_cross_tier():
    lib = FakeLibrarian()
    lib.add(FakeManifest("si", "v1", domain_tags=["unit.si"]))
    wp = FakeWhirlpool("phys-feed")
    wp.add(FakeItem("sha256:dddddddd44444444", domain_tags=["unit.si"]))
    g = CompositeGraphView(lib, [wp])

    edges = list(g.neighbors("TAG:unit.si"))
    targets = {e.dst for e in edges}
    assert "CART:si@v1" in targets
    assert "WP:phys-feed:dddddddd" in targets
    # both edges should be SHARED_TAG
    assert all(e.edge_type == EdgeType.SHARED_TAG for e in edges)


# ---------- caching + invalidation ----------


def test_lazy_cache_hits_store_only_once():
    lib = FakeLibrarian()
    lib.add(FakeManifest("c", "v1", domain_tags=["t"]))
    g = CompositeGraphView(lib, [])

    base = lib.calls_get_by_slug
    list(g.neighbors("CART:c@v1"))   # miss
    list(g.neighbors("CART:c@v1"))   # hit
    list(g.neighbors("CART:c@v1"))   # hit
    # only one underlying lookup despite three calls
    assert lib.calls_get_by_slug == base + 1


def test_invalidate_clears_cache_and_refreshes_tags():
    lib = FakeLibrarian()
    lib.add(FakeManifest("c", "v1", domain_tags=["t.one"]))
    g = CompositeGraphView(lib, [])

    list(g.neighbors("CART:c@v1"))
    assert "t.one" in g._known_tags

    # Add a new manifest and invalidate
    lib.add(FakeManifest("c2", "v1", domain_tags=["t.two"]))
    g.invalidate()

    # Cache cleared: a fresh lookup must re-hit the store
    base = lib.calls_get_by_slug
    list(g.neighbors("CART:c@v1"))
    assert lib.calls_get_by_slug == base + 1
    # known-tags rebuilt: new tag now visible
    assert "t.two" in g._known_tags


# ---------- helper sanity ----------


def test_short_item_slug_strips_prefix_and_truncates():
    assert _short_item_slug("sha256:abcdef0123456789") == "abcdef01"
    assert _short_item_slug("abcdef0123456789") == "abcdef01"


def test_node_kind_values_stable():
    # Defensive: external code keys off these strings; if you rename
    # them, audit data/r2/preadmit/ entries first.
    assert NodeKind.CARTRIDGE.value == "cartridge"
    assert NodeKind.WHIRLPOOL_ITEM.value == "whirlpool_item"
    assert NodeKind.TAG.value == "tag"


def test_graph_edge_is_frozen():
    e = GraphEdge(src="A", dst="B", edge_type=EdgeType.SHARED_TAG)
    with pytest.raises(Exception):
        e.src = "mutated"   # frozen dataclass
