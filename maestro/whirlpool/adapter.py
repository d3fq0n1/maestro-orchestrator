"""
IngestAdapter ABC, CycleStats, IngestFailure, NullIngestAdapter.

The Whirlpool's source layer is pluggable: each Whirlpool runs one
or more ``IngestAdapter`` instances per cycle. The reference HTTP/
RSS adapter lives in ``ingest.py`` (renamed from FeedFetcher in
step I-2 of the ingest-adapter track); this module defines the
interface every adapter implements.

Streaming model (Q-I1=c): adapters yield ``VortexItem`` instances
one at a time via an async generator. The Whirlpool ``async for``s
through the items and inserts each into the vortex. Streaming
avoids materializing whole-cycle item lists in memory.

Stats side-channel: per-cycle instrumentation
(``items_yielded``, ``per_source_counts``, ``failures``) lives
behind a separate ``cycle_stats() -> CycleStats`` call. The
adapter is stateful — it tracks the cycle while iterating and
returns a snapshot from ``cycle_stats()``. This keeps the items
generator clean while preserving the observability surface the
threat-model signals (publisher_drift, rapid_promotion_suspect,
etc.) need.

See docs/architecture/whirlpool.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Optional

from maestro.whirlpool.types import VortexItem


class IngestFailureReason(str, Enum):
    """Reason codes for an ``IngestFailure``.

    These map onto the threat-model signal categories so a future
    MAGI integration can correlate ingest failures with cross-
    session patterns. The Enum is open to extension; new reason
    codes are additive.
    """

    NETWORK_ERROR = "network_error"
    HTTP_ERROR = "http_error"
    PARSE_ERROR = "parse_error"
    SIGNATURE_INVALID = "signature_invalid"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    REFUSED_BY_POLICY = "refused_by_policy"
    OTHER = "other"


@dataclass(frozen=True)
class IngestFailure:
    """One failed source fetch within an ingest cycle.

    ``source_id`` is the registrable-domain identifier the adapter
    uses for dedup and corroboration; ``detail`` carries human-
    readable context for the operator (HTTP status code, exception
    name, etc.) and is not parsed downstream.
    """

    source_id: str
    reason: IngestFailureReason
    detail: str = ""


@dataclass(frozen=True)
class CycleStats:
    """Per-cycle instrumentation snapshot.

    Returned by ``IngestAdapter.cycle_stats()``. Frozen because
    callers receive a snapshot — the adapter holds the live
    state internally and constructs a fresh CycleStats on each
    call.

    Fields:
      - ``started_at`` ISO 8601 UTC of cycle start, or empty
        string if no cycle has run yet.
      - ``completed_at`` None while the cycle is in progress;
        ISO timestamp once iteration has terminated (whether
        normally or via cancellation).
      - ``items_yielded`` total items the adapter produced this
        cycle. Items rejected downstream by the Whirlpool's tag
        filter or dedup are not subtracted; the adapter reports
        what it produced.
      - ``per_source_counts`` ``{source_id: int}`` so MAGI can
        spot publisher_drift (a source that suddenly produces 10x
        its historical average).
      - ``failures`` list of structured ``IngestFailure``
        records. Reason codes drive the threat-model signals.
    """

    started_at: str = ""
    completed_at: Optional[str] = None
    items_yielded: int = 0
    per_source_counts: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)


class IngestAdapter(ABC):
    """Source-agnostic interface for Whirlpool ingest.

    Adapters produce ``VortexItem`` instances via an async
    generator. The Whirlpool drives them with ``async for item in
    adapter.items():``, then calls ``adapter.cycle_stats()`` to
    record instrumentation.

    Implementation contract:

    * ``items()`` is an async generator. Each call starts a fresh
      cycle. The adapter resets its internal cycle stats at the
      start of each call. Per-source counts and failures
      accumulate as items yield.
    * ``cycle_stats()`` returns a snapshot of the current or
      most-recently-completed cycle. Safe to call before the
      first cycle (returns an empty CycleStats), during iteration
      (returns in-progress counts with ``completed_at=None``), or
      after iteration (returns the final stats).
    * The Whirlpool guarantees serial iteration on a given adapter
      (one ``items()`` consumer at a time). Adapters do not need
      to be re-entrant.
    """

    @abstractmethod
    def items(self) -> AsyncIterator[VortexItem]:
        """Async generator yielding ``VortexItem`` instances.

        Implementations override this with ``async def items(self):
        yield ...``. The return-type annotation is the generator's
        produced type (``AsyncIterator[VortexItem]`` is correct for
        an async generator).

        Resource cleanup (open HTTP connections, file handles,
        etc.) belongs in a ``finally`` clause inside the generator
        so cancellation triggers it.
        """

    @abstractmethod
    def cycle_stats(self) -> CycleStats:
        """Snapshot of the most-recent (or in-progress) cycle.

        Returns an empty ``CycleStats`` before any cycle has run.
        """


class NullIngestAdapter(IngestAdapter):
    """Inert adapter. Yields nothing, returns empty stats.

    Safe default for tests and for Whirlpools that haven't been
    wired with a real adapter yet. Mirrors the
    ``NullGraphView`` precedent in maestro/router/graph.py:
    silent no-op is the safest test default. A deployment that
    forgot to plug in a real adapter notices via zero items
    over many cycles, not via noise from the adapter itself.
    """

    async def items(self) -> AsyncIterator[VortexItem]:
        if False:
            # Make the function an async generator that yields
            # nothing. The unreachable yield is the standard
            # Python idiom for "empty async generator".
            yield  # pragma: no cover

    def cycle_stats(self) -> CycleStats:
        return CycleStats()


def _now_iso() -> str:
    """ISO 8601 UTC timestamp. Inlined to keep adapter.py
    dependency-free; ``ingest.py`` has its own copy.
    """
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class InMemoryIngestAdapter(IngestAdapter):
    """In-memory adapter for tests and scripted ingestion.

    Reference second adapter (alongside ``NullIngestAdapter``) so
    pluggability is demonstrably real — not all adapters need to
    speak HTTP. Co-located with ``NullIngestAdapter`` because both
    are dependency-free reference adapters; the HTTP/RSS
    implementation brings httpx + xml.etree and lives in
    ``ingest.py``.

    Queue model (option I-13=c): the caller seeds items via
    ``feed_items(...)`` and failures via ``record_failure(...)``.
    Each ``items()`` call drains the queue at the start of the
    cycle and yields the captured items in order. Subsequent
    cycles see only what was fed *between* cycles (the queue is
    drained per-cycle, not lifetime).

    Empty cycles (no queued items) yield nothing but produce a
    valid CycleStats with ``started_at`` / ``completed_at`` set
    and ``items_yielded == 0``.
    """

    def __init__(self, source_id: str = "in-memory"):
        self._source_id = source_id
        self._pending_items: list = []
        self._pending_failures: list = []
        self._reset_cycle_state()

    def _reset_cycle_state(self):
        self._started_at = ""
        self._completed_at: Optional[str] = None
        self._items_yielded = 0
        self._per_source_counts: dict = {self._source_id: 0}
        self._failures: list = []

    # ---- queue management ----

    def feed_items(self, items) -> None:
        """Queue items to be yielded by the next ``items()`` call.

        Items are not validated here; the caller is responsible
        for shape correctness. The queue persists across multiple
        ``feed_items`` calls and drains all-at-once on the next
        cycle.
        """
        self._pending_items.extend(items)

    def record_failure(self, failure: IngestFailure) -> None:
        """Queue a failure to be reported in the next cycle's stats.

        Failures appear in ``cycle_stats().failures`` after the
        cycle completes. Multiple failures across multiple
        ``record_failure`` calls all surface in the next cycle.
        """
        self._pending_failures.append(failure)

    def pending_item_count(self) -> int:
        """Return how many items are queued for the next cycle.

        Test convenience; not used by the Whirlpool runtime.
        """
        return len(self._pending_items)

    # ---- IngestAdapter implementation ----

    async def items(self) -> AsyncIterator[VortexItem]:
        self._reset_cycle_state()
        self._started_at = _now_iso()
        try:
            # Snapshot + drain at start so feed_items() calls during
            # iteration land in the *next* cycle, not this one.
            queued_items = self._pending_items
            queued_failures = self._pending_failures
            self._pending_items = []
            self._pending_failures = []

            for item in queued_items:
                self._items_yielded += 1
                self._per_source_counts[self._source_id] += 1
                yield item

            self._failures.extend(queued_failures)
        finally:
            self._completed_at = _now_iso()

    def cycle_stats(self) -> CycleStats:
        return CycleStats(
            started_at=self._started_at,
            completed_at=self._completed_at,
            items_yielded=self._items_yielded,
            per_source_counts=dict(self._per_source_counts),
            failures=list(self._failures),
        )
