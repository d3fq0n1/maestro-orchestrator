"""
Graph view used by the Router's d_graph distance component.

The three-tier context system treats Cartridges and Whirlpool items
as routable inference packets — frozen, typed bundles of compressed
context. A canonized Cartridge is a near-primitive: a liter is a
liter, an eight-place calculator is an eight-place calculator. A
Whirlpool item is a tentative packet still accumulating identity.

This module is the graph those packets navigate. Nodes are packets
(Cartridges, Whirlpool items) and the tags they belong to. Edges
connect packets that share structure: supersession, revocation,
shared canonical claim, shared corroborator, shared tag. The
Router's BFS (see distance.py) treats the graph as undirected and
uniformly weighted day 1; the edge type is recorded on every edge
so non-uniform weights can slot in later without reshaping the
traversal.

Node ids are human-glanceable slugs, not content hashes. The graph
is a navigation structure; integrity (signature verification,
content hashing) is the Librarian's and Whirlpool's job at their
own layer. Slug conventions:

    CART:<cartridge_id>@<version>        e.g. CART:si-prefixes@2024.01.01
    WP:<whirlpool_id>:<short-item-slug>  e.g. WP:law-feed:a7f3c201
                                         short-item-slug = first 8 hex chars
                                         of the item content hash
    TAG:<tag>                            e.g. TAG:law.us.federal

Packet routing lives here, not inference. The Librarian and
Whirlpool act as an OSPF-style routing plane: deterministic
lookup against a topology database, with summary-route fallback
(longest-prefix match on dotted tags) when an exact anchor is
missing. Agentic behavior — proposing new anchors, synthesizing
bridges — belongs on the cold path (periodic MAGI audit), not on
the admission hot path.

See docs/architecture/router-distance.md §d_graph.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class NodeKind(str, Enum):
    """What a graph node represents."""

    CARTRIDGE = "cartridge"
    WHIRLPOOL_ITEM = "whirlpool_item"
    TAG = "tag"


class EdgeType(str, Enum):
    """Structural relationship between two nodes.

    Day 1 traversal is uniform-weight and ignores this tag; it is
    recorded on every edge so non-uniform weights (e.g. a heavier
    penalty for SHARED_TAG than for SUPERSEDES) can slot in later
    without reshaping BFS.
    """

    SUPERSEDES = "supersedes"                      # Cartridge -> Cartridge
    REVOKES = "revokes"                            # Cartridge -> Cartridge
    SHARED_CLAIM = "shared_claim"                  # Cartridge <-> WP item
    SHARED_CORROBORATOR = "shared_corroborator"    # WP item <-> WP item
    SHARED_TAG = "shared_tag"                      # anything <-> Tag


@dataclass(frozen=True)
class GraphEdge:
    """One edge in the context graph.

    Undirected for traversal: ``neighbors(node_id)`` returns edges
    incident to ``node_id`` regardless of which endpoint is ``src``.
    The BFS in distance.py advances to whichever of ``src`` / ``dst``
    is not the node it arrived from.
    """

    src: str
    dst: str
    edge_type: EdgeType


class GraphView(ABC):
    """Read-only graph interface the Router's d_graph walks.

    Implementations compose over a Librarian (Cartridge edges) and
    zero or more Whirlpools (vortex edges). ``NullGraphView`` is the
    safe default used by unit tests and by the Router when no
    Librarian or Whirlpool is wired in.

    Contract for implementations:

    * ``neighbors(node_id)`` is O(degree). Implementations must not
      walk the graph here; that is the caller's job. Return the
      edges incident to ``node_id`` and stop.
    * ``anchors_for_tags(tags)`` must do longest-prefix fallback
      on dotted tags. Given ``law.us.federal.unknown``, if no
      ``TAG:law.us.federal.unknown`` anchor exists, fall back to
      ``TAG:law.us.federal`` and then ``TAG:law.us`` and then
      ``TAG:law``. Flat tags without a known exact anchor are
      silently omitted. This matches OSPF summary-route semantics:
      unknown dotted destinations reach the graph via their nearest
      known parent; completely-unknown flat destinations drop.
    """

    @abstractmethod
    def neighbors(self, node_id: str) -> Iterable[GraphEdge]:
        """Return edges incident to ``node_id``.

        May be empty. No ordering guarantee; the BFS dedupes via
        its own visited set.
        """

    @abstractmethod
    def anchors_for_tags(self, tags: Iterable[str]) -> Iterable[str]:
        """Return node ids anchoring ``tags`` into the graph.

        For each tag: try the exact ``TAG:<tag>`` anchor; for dotted
        tags, fall back to successively shorter prefixes until an
        anchor is found or the prefix is empty. Flat tags without an
        exact match are silently omitted.
        """


class NullGraphView(GraphView):
    """Empty graph. Returns no edges and no anchors.

    Safe default for unit tests and for deployments that have not
    wired a Librarian or Whirlpool into the Router. Under
    ``NullGraphView`` the BFS in distance.py finds no path from any
    anchor to any candidate; ``d_graph`` therefore returns its
    no-path-found normalization (1.0 under
    ``1 - exp(-hops/k)`` with hops = infinity).
    """

    def neighbors(self, node_id: str) -> Iterable[GraphEdge]:
        return ()

    def anchors_for_tags(self, tags: Iterable[str]) -> Iterable[str]:
        return ()


def _short_item_slug(item_id: str) -> str:
    """Extract the first 8 hex chars of a Whirlpool item content hash.

    Tolerates both ``"sha256:<hex>"`` and bare ``<hex>`` forms.
    """
    if ":" in item_id:
        item_id = item_id.split(":", 1)[1]
    return item_id[:8]


class CompositeGraphView(GraphView):
    """GraphView stitched over a Librarian and zero or more Whirlpools.

    Edge materialization (day 1):

      - ``SUPERSEDES``, ``REVOKES``     from
        ``Librarian.supersedes_slugs`` / ``.revokes_slugs`` (β bridge:
        slug-translation lives in the Librarian).
      - ``SHARED_TAG``                  from ``manifest.domain_tags``
        on the Cartridge side and ``item.domain_tags`` on the
        Whirlpool side.
      - ``SHARED_CORROBORATOR``         from
        ``item.provenance.source_id`` ↔ ``Whirlpool.items_with_source``.
      - ``SHARED_CLAIM``                deferred. Cartridge body
        canonicalization parity with Whirlpool item canonicalization
        is not yet established; the enum entry stays so callers do
        not need to be re-touched when the edge type lights up.

    Caching: lazy + per-call memoized. Every ``neighbors(node_id)``
    call materializes once, caches the result, and serves subsequent
    calls from the cache. ``invalidate()`` clears the cache and
    rebuilds the known-tags set; callers (Librarian on commit /
    revocation, Whirlpool on promotion / decay tick) are responsible
    for invoking it. Surgical per-node invalidation is a future
    optimization; bidirectional edge handling makes it tricky.

    Anchor resolution: ``anchors_for_tags`` does OSPF-style
    longest-prefix fallback on dotted tags via the precomputed
    ``_known_tags`` set. Flat tags without an exact anchor are
    silently omitted.

    The class accepts a ``None`` Librarian so unit tests can build a
    Whirlpool-only graph; a real deployment always wires a Librarian.
    """

    def __init__(self, librarian, whirlpools):
        self._lib = librarian
        self._whirlpools = list(whirlpools)
        self._wp_by_id = {wp.whirlpool_id: wp for wp in self._whirlpools}
        self._known_tags: set = set()
        self._neighbors_cache: dict = {}
        self._rebuild_known_tags()

    # ---- public surface ----

    def invalidate(self):
        """Clear the neighbors cache and rebuild the known-tags index.

        Callers: Librarian after commit / revocation, Whirlpool after
        promotion or decay tick.
        """
        self._neighbors_cache.clear()
        self._rebuild_known_tags()

    def neighbors(self, node_id: str) -> Iterable[GraphEdge]:
        cached = self._neighbors_cache.get(node_id)
        if cached is not None:
            return cached
        edges = list(self._materialize_neighbors(node_id))
        self._neighbors_cache[node_id] = edges
        return edges

    def anchors_for_tags(self, tags: Iterable[str]) -> Iterable[str]:
        seen: set = set()
        for tag in tags:
            anchor = self._anchor_for_tag(tag)
            if anchor is not None and anchor not in seen:
                seen.add(anchor)
                yield anchor

    # ---- helpers ----

    def _rebuild_known_tags(self):
        tags: set = set()
        if self._lib is not None:
            tags.update(self._lib.known_tags())
        for wp in self._whirlpools:
            tags.update(wp.known_tags())
        self._known_tags = tags

    def _anchor_for_tag(self, tag: str):
        """Return ``"TAG:<tag>"`` if known, else longest-prefix
        fallback for dotted tags, else ``None``.
        """
        if tag in self._known_tags:
            return f"TAG:{tag}"
        if "." not in tag:
            return None
        parts = tag.split(".")
        for i in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in self._known_tags:
                return f"TAG:{prefix}"
        return None

    def _materialize_neighbors(self, node_id: str):
        if node_id.startswith("CART:"):
            yield from self._cartridge_neighbors(node_id)
        elif node_id.startswith("WP:"):
            yield from self._whirlpool_item_neighbors(node_id)
        elif node_id.startswith("TAG:"):
            yield from self._tag_neighbors(node_id)
        # unknown prefix -> empty

    def _cartridge_neighbors(self, slug: str):
        if self._lib is None:
            return
        manifest = self._lib.get_by_slug(slug)
        if manifest is None:
            return
        for target_slug in self._lib.supersedes_slugs(slug):
            yield GraphEdge(slug, target_slug, EdgeType.SUPERSEDES)
        for target_slug in self._lib.revokes_slugs(slug):
            yield GraphEdge(slug, target_slug, EdgeType.REVOKES)
        for tag in manifest.domain_tags:
            yield GraphEdge(slug, f"TAG:{tag}", EdgeType.SHARED_TAG)
        # SHARED_CLAIM deferred; see class docstring.

    def _whirlpool_item_neighbors(self, slug: str):
        wp_id, short = self._parse_wp_slug(slug)
        wp = self._wp_by_id.get(wp_id)
        if wp is None:
            return
        item = wp.get_by_slug(short)
        if item is None:
            return
        for tag in item.domain_tags:
            yield GraphEdge(slug, f"TAG:{tag}", EdgeType.SHARED_TAG)
        seen_partners: set = {slug}
        for prov in item.provenance:
            for partner in wp.items_with_source(prov.source_id):
                partner_slug = self._wp_item_slug(wp.whirlpool_id, partner)
                if partner_slug in seen_partners:
                    continue
                seen_partners.add(partner_slug)
                yield GraphEdge(
                    slug, partner_slug, EdgeType.SHARED_CORROBORATOR,
                )
        # SHARED_CLAIM deferred.

    def _tag_neighbors(self, slug: str):
        tag = slug[len("TAG:"):]
        if self._lib is not None:
            for ref in self._lib.cartridges_with_tag(tag):
                yield GraphEdge(
                    slug, self._cartridge_slug(ref), EdgeType.SHARED_TAG,
                )
        for wp in self._whirlpools:
            for item in wp.items_with_tag(tag):
                yield GraphEdge(
                    slug,
                    self._wp_item_slug(wp.whirlpool_id, item),
                    EdgeType.SHARED_TAG,
                )

    @staticmethod
    def _parse_wp_slug(slug: str):
        """Parse ``"WP:<wp_id>:<short>"`` into ``(wp_id, short)``.

        Uses ``rpartition`` to be robust against ``wp_id`` strings
        containing hyphens or underscores; the short form is hex-only
        and never contains ``":"``.
        """
        rest = slug[len("WP:"):]
        wp_id, _, short = rest.rpartition(":")
        return wp_id, short

    @staticmethod
    def _wp_item_slug(wp_id: str, item) -> str:
        return f"WP:{wp_id}:{_short_item_slug(item.item_id)}"

    @staticmethod
    def _cartridge_slug(ref) -> str:
        return f"CART:{ref.cartridge_id}@{ref.version}"
