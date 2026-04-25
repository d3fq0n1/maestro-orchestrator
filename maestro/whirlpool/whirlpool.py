"""
Whirlpool — the assembled ingest + vortex + query daemon.

One Whirlpool per domain scope. Multiple Whirlpools run side-by-side;
the Router selects which Whirlpools to query based on tag overlap
with the query (see router-distance.md §Bundle-Composition
Algorithm).

A Whirlpool is a first-class module, not a plugin (Q9 = a). The
core ships one reference Whirlpool; additional Whirlpools are
sibling subclasses or separate instances with different
``IngestPolicy`` configs.

See docs/architecture/whirlpool.md.
"""

from dataclasses import dataclass
from typing import Optional

from maestro.whirlpool.ingest import FeedFetcher, TagFilter, Dedup
from maestro.whirlpool.types import (
    DecayProfile,
    IngestPolicy,
    QueryResult,
    VortexItem,
)
from maestro.whirlpool.vortex import Vortex, VortexStats


@dataclass
class PromotionNomination:
    """A Whirlpool → Librarian nomination emitted from a core-ring item.

    Consumed by MAGI which produces a Recommendation (see
    librarian.md §Canonicalization Pipeline). MAGI, not the
    Whirlpool, writes to data/librarian/pending/.
    """

    item: VortexItem
    whirlpool_id: str
    nominated_at: str                # ISO8601 UTC
    corroborator_count: int
    time_in_core_seconds: int


class Whirlpool:
    """Domain-scoped live-ingesting context agent.

    Owns its Vortex, its ingest pipeline, and its query-answer loop.
    Does NOT own cross-Whirlpool coordination — that is the Router's
    responsibility.
    """

    def __init__(
        self,
        policy: IngestPolicy,
        decay: DecayProfile,
    ):
        self._policy = policy
        self._vortex = Vortex(policy.whirlpool_id, decay)
        self._fetcher = FeedFetcher(policy)
        self._tag_filter = TagFilter(policy)
        self._dedup = Dedup()

    # ---- public identity ----

    @property
    def whirlpool_id(self) -> str:
        return self._policy.whirlpool_id

    @property
    def domain_tags(self) -> list:
        """Authoritative namespaces. Used by the Router for selection."""
        return list(self._policy.domain_tags)

    # ---- ingest loop ----

    async def run_ingest_cycle(self) -> dict:
        """Fetch → filter → dedup → insert. Returns a summary dict.

        Called on a background timer per ``policy.poll_interval_seconds``.
        """
        # TODO
        raise NotImplementedError

    async def run(self) -> None:
        """Background loop: alternate ingest and tick.

        Blocks. Intended to run under asyncio.create_task or inside a
        dedicated daemon process. Not yet wired into the orchestrator.
        """
        # TODO
        raise NotImplementedError

    # ---- query path ----

    def query(
        self,
        query_embedding: list,
        query_tags: list,
        k: int = 50,
    ) -> list:
        """Return candidate items ranked for the Router's admission pass.

        Returns list[QueryResult]. The Router applies its composite
        distance metric and admission function; this method only
        provides a candidate pool filtered by tag overlap and
        embedding-nearest-neighbor pre-screen.
        """
        # TODO: cheap pre-filter by tag, then top-k by cosine
        raise NotImplementedError

    # ---- promotion pipeline ----

    def emit_promotion_nominations(self) -> list:
        """Walk the core ring and emit nominations for items that meet the policy.

        MAGI consumes these via data/librarian/pending/. The Whirlpool
        does not write to pending/; it returns the nominations and a
        caller wires them to MAGI's review input.

        Default policy: an item remains in CORE for at least
        ``core_dwell_seconds`` (default 3600) with ≥
        ``promotion_corroborator_min`` (default 5) corroborators.
        These thresholds are per-Whirlpool via policy.metadata.
        """
        # TODO
        raise NotImplementedError

    # ---- telemetry ----

    def stats(self) -> VortexStats:
        """Current vortex stats — used by MAGI for domain-monoculture detection."""
        return self._vortex.stats()

    # ---- enumeration / graph-layer support ----

    def known_tags(self) -> set:
        """Set of every ``domain_tag`` declared by any current vortex item.

        Used by ``CompositeGraphView`` for longest-prefix anchor
        lookup.
        """
        # TODO
        raise NotImplementedError

    def iter_items(self):
        """Iterate every VortexItem currently resident in the vortex."""
        # TODO
        raise NotImplementedError

    def get_by_slug(self, short_item_slug: str):
        """Fetch a VortexItem by its short-form slug (first 8 hex chars).

        ``short_item_slug`` is the part after ``WP:<whirlpool_id>:``.
        Collisions inside one Whirlpool are vanishingly rare; if one
        occurs, returns the most recently inserted item.
        """
        # TODO
        raise NotImplementedError

    def items_with_tag(self, tag: str):
        """Iterate VortexItems whose ``domain_tags`` contain ``tag``.

        Exact match only.
        """
        # TODO
        raise NotImplementedError

    def items_with_source(self, source_id: str):
        """Iterate VortexItems whose ``provenance`` includes ``source_id``.

        Used to materialize ``SHARED_CORROBORATOR`` edges.
        """
        # TODO
        raise NotImplementedError
