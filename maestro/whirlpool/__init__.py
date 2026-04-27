"""
Whirlpool — Tier 2 live-ingesting vortex of fresh decaying context.

Material enters at the periphery as raw feed, spirals inward as it
accumulates corroboration and structure, and is either promoted
toward Cartridge candidacy (Librarian nomination) or flung out via
centrifugal decay. See docs/architecture/whirlpool.md.

A Whirlpool is NOT a Maestro Agent. It does not answer prompts.
It maintains a ranked, decaying store that the Router queries.

This package is a scaffold. Nothing in it is wired into the
orchestration runtime.
"""

from maestro.whirlpool.adapter import (
    CycleStats,
    InMemoryIngestAdapter,
    IngestAdapter,
    IngestFailure,
    IngestFailureReason,
    NullIngestAdapter,
)
from maestro.whirlpool.factory import build_adapters
from maestro.whirlpool.ingest import (
    HttpRssAdapter,
    HttpRssAdapterConfig,
)
from maestro.whirlpool.types import (
    IngestPolicy,
    DecayProfile,
    VortexItem,
    RingId,
    QueryResult,
)

__all__ = [
    "CycleStats",
    "DecayProfile",
    "HttpRssAdapter",
    "HttpRssAdapterConfig",
    "InMemoryIngestAdapter",
    "IngestAdapter",
    "IngestFailure",
    "IngestFailureReason",
    "IngestPolicy",
    "NullIngestAdapter",
    "QueryResult",
    "RingId",
    "VortexItem",
    "build_adapters",
]
