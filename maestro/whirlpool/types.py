"""
Whirlpool type definitions.

See docs/architecture/whirlpool.md for the vortex data model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # Imported only for type-checker visibility; at runtime
    # IngestPolicy holds plain lists and the factory module
    # interprets them. This avoids a circular import (ingest.py
    # already imports from this module).
    from maestro.whirlpool.ingest import HttpRssAdapterConfig


class RingId(IntEnum):
    """Vortex ring depth.

    0 = periphery (just ingested, unverified).
    4 = innermost (promotion-candidate).

    Items move inward as corroboration accumulates and outward by
    decay. Promotion to Cartridge nominates from ring 4 only.
    """

    PERIPHERY = 0
    OUTER = 1
    MID = 2
    INNER = 3
    CORE = 4


@dataclass
class DecayProfile:
    """Time-to-expiry as a function of ring depth and corroboration count.

    See whirlpool.md §Vortex Data Model.

    The profile is deterministic for a given ``(kind, domain_tags)``
    tuple — adversaries cannot slow decay by ingestion pattern (see
    vortex-threat-model.md §W-5).
    """

    # base decay in seconds per ring; lower ring (periphery) decays fastest
    decay_seconds_by_ring: dict = field(default_factory=dict)
    # corroboration count required to advance from each ring to the next
    corroborators_to_advance_by_ring: dict = field(default_factory=dict)
    # fractional weight assigned to fresh publishers (< age_threshold_days old)
    fresh_publisher_weight: float = 0.3
    age_threshold_days: int = 30


@dataclass
class IngestPolicy:
    """Per-Whirlpool ingest configuration.

    Adapter-agnostic fields live here. Adapter-specific
    configuration (HTTP feed URLs, signature requirements, etc.)
    lives on per-adapter dataclasses such as
    ``HttpRssAdapterConfig`` and travels via the typed slots
    below (Q-I2 = c). The ``factory.build_adapters(policy)``
    helper walks these slots and instantiates the configured
    adapters with ``whirlpool_id`` from this policy.

    Adding a new adapter type means adding a new typed slot here
    and registering the slot-to-class mapping in
    ``maestro/whirlpool/factory.py``. No churn for existing
    callers; new fields default to empty.
    """

    whirlpool_id: str
    domain_tags: list = field(default_factory=list)    # authoritative namespaces
    poll_interval_seconds: int = 900                   # 15 minutes
    max_items_per_cycle: int = 200
    # per-source cap on items contributing to the rejected partition
    # (see vortex-threat-model.md §T-6)
    per_source_partition_cap: float = 0.05

    # ---- typed adapter slots ----
    # Each slot carries zero or more adapter configs (Q-I11 = b:
    # multiple HttpRssAdapter instances under one Whirlpool is
    # legitimate — different feeds, different rate limits).
    #
    # Runtime type is plain `list` to keep this module's imports
    # adapter-free; the typing annotation is deferred via
    # ``from __future__ import annotations`` so type checkers
    # still see the precise element type.
    http_rss: list[HttpRssAdapterConfig] = field(default_factory=list)


@dataclass
class Provenance:
    """Immutable record of how an item reached the vortex."""

    source_id: str                   # registrable domain of the publisher
    source_url: str                  # actual URL fetched
    fetched_at: str                  # ISO8601 UTC
    publisher_signature: Optional[str] = None   # HTTP Sig / Atom sig if present
    publisher_age_days: int = 0


@dataclass
class VortexItem:
    """One piece of material in the vortex.

    Immutable once ingested except for ``ring``, ``corroborators``,
    ``expires_at``, and the embedding vector (which may be recomputed
    if the embedder is upgraded).
    """

    item_id: str                     # content hash of the claim body
    whirlpool_id: str
    claim_summary: str               # the canonical short-form claim
    body_excerpt: str
    domain_tags: list = field(default_factory=list)
    provenance: list = field(default_factory=list)     # list[Provenance]
    ring: RingId = RingId.PERIPHERY
    corroborators: int = 0           # distinct publishers corroborating
    entered_at: str = ""
    last_moved_at: str = ""
    expires_at: str = ""
    trust: float = 0.0               # computed per router-distance.md §trust(C)
    embedding: Optional[list] = None # present once embedder has run


@dataclass
class QueryResult:
    """One item returned by ``Whirlpool.query`` for the Router."""

    item: VortexItem
    relevance: float                 # per router-distance.md §relevance(Q, C)
    distance: float                  # composite distance to the query
