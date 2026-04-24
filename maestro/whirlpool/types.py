"""
Whirlpool type definitions.

See docs/architecture/whirlpool.md for the vortex data model.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


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

    Day 1 supports HTTP/RSS polling only. A future pluggable
    IngestAdapter interface is out of scope (Q8 = a).
    """

    whirlpool_id: str
    domain_tags: list = field(default_factory=list)    # authoritative namespaces
    feed_urls: list = field(default_factory=list)      # HTTPS RSS/Atom only
    poll_interval_seconds: int = 900                   # 15 minutes
    max_items_per_cycle: int = 200
    require_feed_signature: bool = False               # elevate signed publishers
    # per-source cap on items contributing to the rejected partition
    # (see vortex-threat-model.md §T-6)
    per_source_partition_cap: float = 0.05


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
