"""
Smoke tests for InMemoryIngestAdapter (step I-5/5, part 1 of 2).

Verifies the queue model: feed_items + record_failure populate
the next cycle, queues drain per-cycle, empty cycles produce
valid empty stats.

The multi-adapter integration test (HttpRssAdapter alongside
InMemoryIngestAdapter under one Whirlpool) lives in
test_whirlpool_multi_adapter_integration.py.
"""

import asyncio

import pytest

from maestro.whirlpool.adapter import (
    CycleStats,
    IngestAdapter,
    IngestFailure,
    IngestFailureReason,
    InMemoryIngestAdapter,
)
from maestro.whirlpool.types import RingId, VortexItem


def _vi(item_id_hex: str) -> VortexItem:
    return VortexItem(
        item_id=f"sha256:{item_id_hex.ljust(16, '0')}",
        whirlpool_id="test-wp",
        claim_summary=f"claim-{item_id_hex}",
        body_excerpt="body",
        domain_tags=["test.tag"],
        ring=RingId.PERIPHERY,
    )


def _collect(adapter):
    items = []

    async def consume():
        async for item in adapter.items():
            items.append(item)

    asyncio.run(consume())
    return items


# ---- ABC compliance ----


def test_in_memory_adapter_is_an_ingest_adapter():
    a = InMemoryIngestAdapter()
    assert isinstance(a, IngestAdapter)


def test_default_state_yields_nothing():
    a = InMemoryIngestAdapter()
    assert _collect(a) == []
    cs = a.cycle_stats()
    assert cs.items_yielded == 0
    assert cs.failures == []


def test_default_cycle_stats_after_empty_cycle_has_timestamps():
    """Even an empty cycle produces a valid CycleStats with the
    started_at and completed_at fields populated.
    """
    a = InMemoryIngestAdapter()
    _collect(a)
    cs = a.cycle_stats()
    assert cs.started_at != ""
    assert cs.completed_at is not None


# ---- feed_items ----


def test_feed_items_queues_for_next_cycle():
    a = InMemoryIngestAdapter()
    a.feed_items([_vi("aa"), _vi("bb")])
    assert a.pending_item_count() == 2

    items = _collect(a)
    assert len(items) == 2
    assert a.pending_item_count() == 0   # drained


def test_feed_items_yields_in_insertion_order():
    a = InMemoryIngestAdapter()
    a.feed_items([_vi("aa")])
    a.feed_items([_vi("bb"), _vi("cc")])
    items = _collect(a)
    prefixes = [it.item_id.split(":", 1)[1][:2] for it in items]
    assert prefixes == ["aa", "bb", "cc"]


def test_per_source_counts_match_yielded():
    a = InMemoryIngestAdapter(source_id="seed.test")
    a.feed_items([_vi("11"), _vi("22"), _vi("33")])
    _collect(a)
    cs = a.cycle_stats()
    assert cs.items_yielded == 3
    assert cs.per_source_counts == {"seed.test": 3}


# ---- record_failure ----


def test_record_failure_appears_in_next_cycle_stats():
    a = InMemoryIngestAdapter()
    fail = IngestFailure(
        source_id="seed.test",
        reason=IngestFailureReason.NETWORK_ERROR,
        detail="simulated",
    )
    a.record_failure(fail)
    _collect(a)
    cs = a.cycle_stats()
    assert len(cs.failures) == 1
    assert cs.failures[0] == fail


def test_record_failure_drains_after_cycle():
    a = InMemoryIngestAdapter()
    a.record_failure(
        IngestFailure("x", IngestFailureReason.TIMEOUT, "1s"),
    )
    _collect(a)
    # Second cycle has no queued failure
    _collect(a)
    cs = a.cycle_stats()
    assert cs.failures == []


def test_items_and_failures_combine_in_one_cycle():
    a = InMemoryIngestAdapter(source_id="combo.test")
    a.feed_items([_vi("aa")])
    a.record_failure(
        IngestFailure("combo.test", IngestFailureReason.PARSE_ERROR, "bad XML"),
    )
    items = _collect(a)
    cs = a.cycle_stats()

    assert len(items) == 1
    assert cs.items_yielded == 1
    assert len(cs.failures) == 1
    assert cs.per_source_counts == {"combo.test": 1}


# ---- cycle isolation ----


def test_second_cycle_yields_only_what_was_fed_between():
    a = InMemoryIngestAdapter()
    a.feed_items([_vi("11"), _vi("22")])
    first = _collect(a)
    assert len(first) == 2

    a.feed_items([_vi("33")])
    second = _collect(a)
    assert len(second) == 1
    assert second[0].item_id.split(":", 1)[1].startswith("33")


def test_empty_second_cycle_yields_nothing():
    a = InMemoryIngestAdapter()
    a.feed_items([_vi("aa")])
    _collect(a)
    second = _collect(a)
    assert second == []
    cs = a.cycle_stats()
    assert cs.items_yielded == 0


def test_cycle_stats_resets_per_cycle():
    """items_yielded and failures count only the most recent
    cycle, not cumulative across the adapter's lifetime.
    """
    a = InMemoryIngestAdapter(source_id="cycle.test")
    a.feed_items([_vi("11"), _vi("22"), _vi("33")])
    _collect(a)
    cs1 = a.cycle_stats()

    a.feed_items([_vi("44")])
    _collect(a)
    cs2 = a.cycle_stats()

    assert cs1.items_yielded == 3
    assert cs2.items_yielded == 1
    assert cs1.per_source_counts == {"cycle.test": 3}
    assert cs2.per_source_counts == {"cycle.test": 1}


# ---- mid-iteration feed lands in next cycle ----


def test_feed_items_mid_iteration_lands_in_next_cycle():
    """The queue is drained at the start of items(); calls to
    feed_items during iteration must land in the *next* cycle,
    not extend the current one.
    """
    a = InMemoryIngestAdapter()
    a.feed_items([_vi("aa")])
    seen = []

    async def consume():
        async for item in a.items():
            seen.append(item)
            # Feed during iteration; must NOT show up in this cycle
            a.feed_items([_vi("bb")])

    asyncio.run(consume())
    assert len(seen) == 1   # only the originally-queued item

    # Next cycle picks up the item fed during iteration
    second = _collect(a)
    assert len(second) == 1
