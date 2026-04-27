"""
Smoke tests for maestro/whirlpool/adapter.py.

Step I-1 of the ingest-adapter pluggability track. Pins the
streaming + side-channel-stats contract, the IngestFailure /
CycleStats shapes, and NullIngestAdapter behavior.
"""

import asyncio
from typing import AsyncIterator

import pytest

from maestro.whirlpool.adapter import (
    CycleStats,
    IngestAdapter,
    IngestFailure,
    IngestFailureReason,
    NullIngestAdapter,
)
from maestro.whirlpool.types import RingId, VortexItem


# ---- ABC contract ----


def test_ingest_adapter_is_abstract():
    with pytest.raises(TypeError):
        IngestAdapter()


def test_null_ingest_adapter_is_subclass():
    null = NullIngestAdapter()
    assert isinstance(null, IngestAdapter)


# ---- IngestFailureReason ----


def test_failure_reason_values_stable():
    """External code (MAGI signals, threat-model exports) keys off
    these strings; if you rename them, audit pre-admit and signal
    consumers first.
    """
    assert IngestFailureReason.NETWORK_ERROR.value == "network_error"
    assert IngestFailureReason.HTTP_ERROR.value == "http_error"
    assert IngestFailureReason.PARSE_ERROR.value == "parse_error"
    assert IngestFailureReason.SIGNATURE_INVALID.value == "signature_invalid"
    assert IngestFailureReason.TIMEOUT.value == "timeout"
    assert IngestFailureReason.RATE_LIMITED.value == "rate_limited"
    assert IngestFailureReason.REFUSED_BY_POLICY.value == "refused_by_policy"
    assert IngestFailureReason.OTHER.value == "other"


def test_ingest_failure_is_frozen():
    f = IngestFailure(
        source_id="example.com",
        reason=IngestFailureReason.HTTP_ERROR,
        detail="503 Service Unavailable",
    )
    with pytest.raises(Exception):
        f.detail = "tampered"


# ---- CycleStats ----


def test_cycle_stats_default_is_empty():
    cs = CycleStats()
    assert cs.started_at == ""
    assert cs.completed_at is None
    assert cs.items_yielded == 0
    assert cs.per_source_counts == {}
    assert cs.failures == []


def test_cycle_stats_is_frozen():
    cs = CycleStats(started_at="2024-01-01T00:00:00+00:00", items_yielded=5)
    with pytest.raises(Exception):
        cs.items_yielded = 10


def test_cycle_stats_carries_failures():
    failures = [
        IngestFailure("a.com", IngestFailureReason.TIMEOUT, "30s"),
        IngestFailure("b.com", IngestFailureReason.PARSE_ERROR, "malformed feed"),
    ]
    cs = CycleStats(
        started_at="2024-01-01T00:00:00+00:00",
        completed_at="2024-01-01T00:00:30+00:00",
        items_yielded=12,
        per_source_counts={"a.com": 0, "b.com": 0, "c.com": 12},
        failures=failures,
    )
    assert cs.items_yielded == 12
    assert len(cs.failures) == 2
    assert cs.failures[0].reason == IngestFailureReason.TIMEOUT
    assert cs.per_source_counts["c.com"] == 12


# ---- NullIngestAdapter ----


def test_null_adapter_yields_nothing():
    """async for over NullIngestAdapter.items() iterates zero times."""
    null = NullIngestAdapter()
    collected = []

    async def consume():
        async for item in null.items():
            collected.append(item)

    asyncio.run(consume())
    assert collected == []


def test_null_adapter_cycle_stats_is_empty():
    null = NullIngestAdapter()
    cs = null.cycle_stats()
    assert cs == CycleStats()
    assert cs.started_at == ""
    assert cs.completed_at is None
    assert cs.items_yielded == 0


def test_null_adapter_cycle_stats_safe_to_call_repeatedly():
    """Calling cycle_stats() before any items() invocation must
    not raise — silent no-op is the safest test default (Q-I6=a).
    """
    null = NullIngestAdapter()
    a = null.cycle_stats()
    b = null.cycle_stats()
    assert a == b


# ---- Concrete subclass demonstration ----


class _DemoAdapter(IngestAdapter):
    """Tiny in-test adapter to exercise the streaming + stats
    contract end-to-end. Yields a fixed list of VortexItems and
    records per-source counts.
    """

    def __init__(self, items_to_yield, source_id="demo.com", failure=None):
        self._items_to_yield = list(items_to_yield)
        self._source_id = source_id
        self._failure = failure
        self._started_at = ""
        self._completed_at = None
        self._items_yielded = 0
        self._per_source_counts = {}
        self._failures = []

    async def items(self):
        from datetime import datetime, timezone
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._completed_at = None
        self._items_yielded = 0
        self._per_source_counts = {self._source_id: 0}
        self._failures = []
        try:
            for item in self._items_to_yield:
                # Increment BEFORE yield so cycle_stats() taken
                # mid-iteration reflects "items handed to consumer
                # so far" rather than "items the producer has
                # finished handing back to itself".
                self._items_yielded += 1
                self._per_source_counts[self._source_id] += 1
                yield item
            if self._failure is not None:
                self._failures.append(self._failure)
        finally:
            self._completed_at = datetime.now(timezone.utc).isoformat()

    def cycle_stats(self) -> CycleStats:
        return CycleStats(
            started_at=self._started_at,
            completed_at=self._completed_at,
            items_yielded=self._items_yielded,
            per_source_counts=dict(self._per_source_counts),
            failures=list(self._failures),
        )


def _vi(item_id_hex: str, tag: str = "test.tag") -> VortexItem:
    return VortexItem(
        item_id=f"sha256:{item_id_hex.ljust(16, '0')}",
        whirlpool_id="test-wp",
        claim_summary="claim",
        body_excerpt="body",
        domain_tags=[tag],
        ring=RingId.PERIPHERY,
    )


def test_demo_adapter_streams_items_in_order():
    """Verifies the streaming contract: caller receives items
    one at a time via async for; order matches the producer.
    """
    a = _DemoAdapter([_vi("aa"), _vi("bb"), _vi("cc")])
    collected = []

    async def consume():
        async for item in a.items():
            collected.append(item)

    asyncio.run(consume())
    assert [it.item_id[-2:] for it in collected] == ["00", "00", "00"]
    # Items are the actual three we pushed in
    assert len(collected) == 3
    assert collected[0].item_id.endswith("aa" + "0" * 14)
    assert collected[1].item_id.endswith("bb" + "0" * 14)
    assert collected[2].item_id.endswith("cc" + "0" * 14)


def test_demo_adapter_cycle_stats_after_iteration():
    a = _DemoAdapter([_vi("11"), _vi("22"), _vi("33")])

    async def consume():
        async for _ in a.items():
            pass

    asyncio.run(consume())
    cs = a.cycle_stats()
    assert cs.items_yielded == 3
    assert cs.per_source_counts == {"demo.com": 3}
    assert cs.failures == []
    assert cs.started_at != ""
    assert cs.completed_at is not None


def test_demo_adapter_cycle_stats_during_iteration():
    """cycle_stats() called mid-iteration returns in-progress
    state with completed_at=None.
    """
    a = _DemoAdapter([_vi("11"), _vi("22"), _vi("33"), _vi("44")])
    snapshots = []

    async def consume():
        idx = 0
        async for _ in a.items():
            idx += 1
            if idx == 2:
                snapshots.append(a.cycle_stats())

    asyncio.run(consume())
    assert len(snapshots) == 1
    mid = snapshots[0]
    assert mid.items_yielded == 2
    assert mid.completed_at is None
    assert mid.started_at != ""


def test_demo_adapter_failure_recorded_in_stats():
    failure = IngestFailure(
        "demo.com",
        IngestFailureReason.SIGNATURE_INVALID,
        "atom signature did not verify",
    )
    a = _DemoAdapter([_vi("aa")], failure=failure)

    async def consume():
        async for _ in a.items():
            pass

    asyncio.run(consume())
    cs = a.cycle_stats()
    assert len(cs.failures) == 1
    assert cs.failures[0].reason == IngestFailureReason.SIGNATURE_INVALID
    assert cs.failures[0].source_id == "demo.com"


def test_demo_adapter_cycle_stats_snapshot_isolated():
    """The dict + list inside CycleStats are copied at snapshot
    time, so a caller mutating them must not affect the
    adapter's internal state.
    """
    a = _DemoAdapter([_vi("aa")])

    async def consume():
        async for _ in a.items():
            pass

    asyncio.run(consume())
    cs1 = a.cycle_stats()
    cs1.per_source_counts.clear()      # caller mutates snapshot
    cs1.failures.append("garbage")     # caller mutates snapshot
    cs2 = a.cycle_stats()
    # Adapter's stats are untouched
    assert cs2.per_source_counts == {"demo.com": 1}
    assert cs2.failures == []
