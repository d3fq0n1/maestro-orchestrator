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
