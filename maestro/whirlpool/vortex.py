"""
Vortex — the ring-structured decaying store of Whirlpool items.

See docs/architecture/whirlpool.md §Vortex Data Model.

Rings 0 (periphery) through 4 (core). Items move inward when they
accumulate sufficient corroborators for their ring; outward (toward
expiry) by decay. The core ring (4) is the promotion candidate
pool for MAGI nominations.

Bounded-rate climbing: an item cannot jump more than one ring per
decay quartile (see vortex-threat-model.md §W-1). Jumps beyond
that threshold are pinned and logged as rapid_promotion_suspect.

This module is pure data management — no ingestion, no query-side
scoring. Ingest lives in ``ingest.py``; query serving lives on the
``Whirlpool`` class in ``whirlpool.py``.
"""

from dataclasses import dataclass
from typing import Optional

from maestro.whirlpool.types import (
    DecayProfile,
    RingId,
    VortexItem,
)


@dataclass
class VortexStats:
    """Summary of the vortex at a point in time.

    The topology itself is a signal (see whirlpool.md §Vortex as
    Signal). Density clusters indicate "hot" topics the Router
    weights toward admission.
    """

    item_count_by_ring: dict          # {RingId: int}
    mean_corroborators_by_ring: dict  # {RingId: float}
    density_hotspots: list            # top-k domain_tag clusters
    total_items: int


class Vortex:
    """In-memory + disk-persisted ring store.

    Backing store:
        data/whirlpool/{whirlpool_id}/items/{item_id}.json

    Every item's ring, corroborators, and expires_at are persisted
    on every transition. Reads serve from in-memory; writes go
    through to disk.
    """

    def __init__(self, whirlpool_id: str, decay: DecayProfile):
        self._whirlpool_id = whirlpool_id
        self._decay = decay

    # ---- mutation ----

    def insert(self, item: VortexItem) -> VortexItem:
        """Insert a fresh item at ring PERIPHERY.

        Sets ``entered_at``, ``last_moved_at``, ``expires_at`` per the
        decay profile. Refuses duplicate ``item_id`` (dedup is the
        ingest layer's job; this is a safety net).
        """
        # TODO
        raise NotImplementedError

    def corroborate(self, item_id: str, publisher_id: str) -> Optional[VortexItem]:
        """Record a corroborator observation and advance ring if eligible.

        Honors the rate-limit: one ring per decay quartile. A request
        that would jump more than one ring pins the item at its
        current ring and returns it with a ``rapid_promotion_suspect``
        flag in its provenance metadata (the caller logs the threat).

        Returns None if item_id is unknown.
        """
        # TODO
        raise NotImplementedError

    def tick(self) -> list:
        """Advance time: apply decay and expire items past ``expires_at``.

        Returns the list of VortexItems that were expired this tick.
        Called on a background timer (see whirlpool.Whirlpool.run).
        """
        # TODO
        raise NotImplementedError

    # ---- read ----

    def get(self, item_id: str) -> Optional[VortexItem]:
        """Exact-lookup an item by id."""
        # TODO
        raise NotImplementedError

    def iter_ring(self, ring: RingId):
        """Iterate items in a given ring in insertion order."""
        # TODO
        raise NotImplementedError

    def core_items(self) -> list:
        """Return items at ring CORE — the promotion candidate pool."""
        # TODO: yield from iter_ring(RingId.CORE)
        raise NotImplementedError

    # ---- stats / topology ----

    def stats(self, hotspot_k: int = 5) -> VortexStats:
        """Compute density clusters and per-ring counts."""
        # TODO
        raise NotImplementedError
