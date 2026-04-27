"""
Smoke tests for Whirlpool's adapter integration (step I-4/5).

Verifies that:

  * Whirlpool() with adapters=None derives adapters from the
    policy's typed slots via factory.build_adapters.
  * Whirlpool(adapters=[...]) uses the explicit list as-is.
  * Whirlpool(adapters=[]) is a valid zero-adapter Whirlpool.
  * run_ingest_cycle async-iterates each adapter, aggregates
    items, and snapshots per-adapter cycle_stats.
  * Failures from one adapter don't abort other adapters.
  * Items collected match the union of all adapters' streams.

Vortex insertion / TagFilter / Dedup wiring stays stubbed; the
test verifies the streaming + stats wiring only.
"""

import asyncio
from typing import AsyncIterator

import pytest

from maestro.whirlpool.adapter import (
    CycleStats,
    IngestAdapter,
    IngestFailure,
    IngestFailureReason,
)
from maestro.whirlpool.types import (
    DecayProfile,
    IngestPolicy,
    RingId,
    VortexItem,
)
from maestro.whirlpool.whirlpool import (
    IngestCycleSummary,
    Whirlpool,
)


# ---- helpers ----


def _vi(item_id_hex: str, tag: str = "test.tag") -> VortexItem:
    return VortexItem(
        item_id=f"sha256:{item_id_hex.ljust(16, '0')}",
        whirlpool_id="test-wp",
        claim_summary=f"claim-{item_id_hex}",
        body_excerpt="body",
        domain_tags=[tag],
        ring=RingId.PERIPHERY,
    )


class _FixedAdapter(IngestAdapter):
    """Adapter that yields a fixed list, optionally records a failure."""

    def __init__(self, items, source_id="fixed.test", failures=None):
        self._items = list(items)
        self._source_id = source_id
        self._failures = list(failures or [])
        self._items_yielded = 0
        self._per_source_counts = {source_id: 0}

    async def items(self):
        self._items_yielded = 0
        self._per_source_counts = {self._source_id: 0}
        for item in self._items:
            self._items_yielded += 1
            self._per_source_counts[self._source_id] += 1
            yield item

    def cycle_stats(self):
        return CycleStats(
            started_at="t0",
            completed_at="t1",
            items_yielded=self._items_yielded,
            per_source_counts=dict(self._per_source_counts),
            failures=list(self._failures),
        )


def _decay() -> DecayProfile:
    return DecayProfile(
        decay_seconds_by_ring={0: 60, 1: 600, 2: 3600, 3: 86400, 4: 604800},
        corroborators_to_advance_by_ring={0: 1, 1: 2, 2: 3, 3: 5},
    )


def _run(coro):
    return asyncio.run(coro)


# ---- adapter wiring ----


def test_default_adapters_derived_from_policy():
    """When the constructor's adapters arg is None, the Whirlpool
    builds adapters from the policy's typed slots.
    """
    from maestro.whirlpool import HttpRssAdapter, HttpRssAdapterConfig

    policy = IngestPolicy(
        whirlpool_id="wp",
        http_rss=[HttpRssAdapterConfig(feed_urls=["https://a.example/rss"])],
    )
    wp = Whirlpool(policy=policy, decay=_decay())
    assert len(wp.adapters) == 1
    assert isinstance(wp.adapters[0], HttpRssAdapter)
    assert wp.adapters[0]._whirlpool_id == "wp"


def test_explicit_adapters_used_as_is():
    """When adapters=[...] is passed, those are used regardless of
    policy slots.
    """
    policy = IngestPolicy(whirlpool_id="wp")
    a = _FixedAdapter([_vi("aa")])
    b = _FixedAdapter([_vi("bb")])
    wp = Whirlpool(policy=policy, decay=_decay(), adapters=[a, b])
    assert wp.adapters == [a, b]


def test_explicit_empty_adapter_list_is_valid():
    """adapters=[] is valid (zero-adapter Whirlpool)."""
    policy = IngestPolicy(whirlpool_id="wp")
    wp = Whirlpool(policy=policy, decay=_decay(), adapters=[])
    assert wp.adapters == []


def test_adapters_property_is_a_copy():
    """Mutating the returned list must not affect the Whirlpool's
    internal adapters.
    """
    policy = IngestPolicy(whirlpool_id="wp")
    a = _FixedAdapter([_vi("aa")])
    wp = Whirlpool(policy=policy, decay=_decay(), adapters=[a])
    snapshot = wp.adapters
    snapshot.append(_FixedAdapter([_vi("bb")]))
    assert len(wp.adapters) == 1   # internal still has just `a`


# ---- run_ingest_cycle ----


def test_run_ingest_cycle_with_zero_adapters_returns_empty_summary():
    policy = IngestPolicy(whirlpool_id="wp")
    wp = Whirlpool(policy=policy, decay=_decay(), adapters=[])
    summary = _run(wp.run_ingest_cycle())
    assert isinstance(summary, IngestCycleSummary)
    assert summary.total_items == 0
    assert summary.total_failures == 0
    assert summary.items == []
    assert summary.adapter_stats == []


def test_run_ingest_cycle_collects_items_from_one_adapter():
    a = _FixedAdapter([_vi("11"), _vi("22"), _vi("33")])
    wp = Whirlpool(
        policy=IngestPolicy(whirlpool_id="wp"),
        decay=_decay(),
        adapters=[a],
    )
    summary = _run(wp.run_ingest_cycle())
    assert summary.total_items == 3
    assert summary.total_failures == 0
    assert len(summary.items) == 3
    assert len(summary.adapter_stats) == 1
    assert summary.adapter_stats[0].items_yielded == 3


def test_run_ingest_cycle_collects_items_from_multiple_adapters():
    a = _FixedAdapter([_vi("aa"), _vi("bb")], source_id="a.test")
    b = _FixedAdapter([_vi("cc")], source_id="b.test")
    wp = Whirlpool(
        policy=IngestPolicy(whirlpool_id="wp"),
        decay=_decay(),
        adapters=[a, b],
    )
    summary = _run(wp.run_ingest_cycle())
    assert summary.total_items == 3
    assert len(summary.adapter_stats) == 2
    # Per-adapter counts preserved
    assert summary.adapter_stats[0].items_yielded == 2
    assert summary.adapter_stats[1].items_yielded == 1
    # Per-source counts preserved separately
    assert summary.adapter_stats[0].per_source_counts == {"a.test": 2}
    assert summary.adapter_stats[1].per_source_counts == {"b.test": 1}


def test_run_ingest_cycle_aggregates_failures_across_adapters():
    a_failures = [
        IngestFailure("a.test", IngestFailureReason.HTTP_ERROR, "503"),
    ]
    b_failures = [
        IngestFailure("b.test", IngestFailureReason.TIMEOUT, "30s"),
        IngestFailure("b.test", IngestFailureReason.PARSE_ERROR, "malformed"),
    ]
    a = _FixedAdapter([_vi("aa")], source_id="a.test", failures=a_failures)
    b = _FixedAdapter([_vi("bb"), _vi("cc")], source_id="b.test", failures=b_failures)
    wp = Whirlpool(
        policy=IngestPolicy(whirlpool_id="wp"),
        decay=_decay(),
        adapters=[a, b],
    )
    summary = _run(wp.run_ingest_cycle())
    assert summary.total_failures == 3   # 1 + 2
    # Per-adapter failures isolated
    assert len(summary.adapter_stats[0].failures) == 1
    assert len(summary.adapter_stats[1].failures) == 2


def test_run_ingest_cycle_one_failing_adapter_does_not_abort_others():
    """An adapter that records a failure but yields zero items
    must not stop subsequent adapters from running.
    """
    a = _FixedAdapter(
        [],   # no items
        source_id="a.test",
        failures=[IngestFailure("a.test", IngestFailureReason.HTTP_ERROR, "503")],
    )
    b = _FixedAdapter([_vi("bb"), _vi("cc")], source_id="b.test")
    wp = Whirlpool(
        policy=IngestPolicy(whirlpool_id="wp"),
        decay=_decay(),
        adapters=[a, b],
    )
    summary = _run(wp.run_ingest_cycle())
    assert summary.total_items == 2
    assert summary.total_failures == 1
    # Both adapters' stats are present
    assert len(summary.adapter_stats) == 2


def test_run_ingest_cycle_iterates_adapters_in_order():
    """Items appear in summary.items in the order they were
    pulled from adapters[0] first, then adapters[1], etc.
    """
    a = _FixedAdapter([_vi("aa"), _vi("ab")])
    b = _FixedAdapter([_vi("ba"), _vi("bb"), _vi("bc")])
    wp = Whirlpool(
        policy=IngestPolicy(whirlpool_id="wp"),
        decay=_decay(),
        adapters=[a, b],
    )
    summary = _run(wp.run_ingest_cycle())
    summaries_id_prefixes = [
        item.item_id.removeprefix("sha256:")[:2]
        for item in summary.items
    ]
    assert summaries_id_prefixes == ["aa", "ab", "ba", "bb", "bc"]


def test_run_ingest_cycle_repeated_calls_dont_accumulate():
    """Running the cycle twice gives two independent summaries;
    the second call's totals reflect only the second cycle.
    """
    a = _FixedAdapter([_vi("11"), _vi("22")])
    wp = Whirlpool(
        policy=IngestPolicy(whirlpool_id="wp"),
        decay=_decay(),
        adapters=[a],
    )
    s1 = _run(wp.run_ingest_cycle())
    s2 = _run(wp.run_ingest_cycle())
    assert s1.total_items == 2
    assert s2.total_items == 2
    # The two summaries are distinct objects
    assert s1 is not s2
