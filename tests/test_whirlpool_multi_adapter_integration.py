"""
Multi-adapter integration test (step I-5/5, part 2 of 2).

Two adapters running side-by-side under one Whirlpool: an
HttpRssAdapter intercepting via httpx.MockTransport, and an
InMemoryIngestAdapter with hand-fed items + failures. Verifies:

  * Items from both adapters reach the IngestCycleSummary.
  * Per-adapter cycle_stats stay isolated (different per-source
    counts, different failure lists).
  * A failing adapter does not abort other adapters in the
    cycle.
  * State isolation across cycles (Q-I14=b): a second cycle's
    stats reflect only that cycle, not the first.
  * Adapter pluggability is structurally real — a non-HTTP
    adapter coexists with HTTP/RSS in the same Whirlpool.
"""

import asyncio

import httpx
import pytest

from maestro.whirlpool.adapter import (
    IngestFailure,
    IngestFailureReason,
    InMemoryIngestAdapter,
)
from maestro.whirlpool.ingest import HttpRssAdapter, HttpRssAdapterConfig
from maestro.whirlpool.types import (
    DecayProfile,
    IngestPolicy,
    RingId,
    VortexItem,
)
from maestro.whirlpool.whirlpool import Whirlpool


# ---- helpers ----


_RSS_TWO_ITEMS = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Multi-Adapter Test Feed</title>
    <item>
      <title>RSS Item Alpha</title>
      <description>Alpha body.</description>
      <link>https://feed.example/alpha</link>
    </item>
    <item>
      <title>RSS Item Beta</title>
      <description>Beta body.</description>
      <link>https://feed.example/beta</link>
    </item>
  </channel>
</rss>"""


def _vi(item_id_hex: str, summary: str = "in-memory item") -> VortexItem:
    return VortexItem(
        item_id=f"sha256:{item_id_hex.ljust(16, '0')}",
        whirlpool_id="multi-wp",
        claim_summary=summary,
        body_excerpt="body",
        domain_tags=["test.tag"],
        ring=RingId.PERIPHERY,
    )


def _decay() -> DecayProfile:
    return DecayProfile(
        decay_seconds_by_ring={0: 60, 1: 600, 2: 3600, 3: 86400, 4: 604800},
        corroborators_to_advance_by_ring={0: 1, 1: 2, 2: 3, 3: 5},
    )


def _build_world(rss_handler=None):
    """Build a Whirlpool with HttpRssAdapter + InMemoryIngestAdapter."""
    if rss_handler is None:
        rss_handler = lambda req: httpx.Response(200, content=_RSS_TWO_ITEMS)
    transport = httpx.MockTransport(rss_handler)

    rss_adapter = HttpRssAdapter(
        config=HttpRssAdapterConfig(feed_urls=["https://feed.example/rss"]),
        whirlpool_id="multi-wp",
        transport=transport,
    )
    in_mem = InMemoryIngestAdapter(source_id="seed.test")

    wp = Whirlpool(
        policy=IngestPolicy(whirlpool_id="multi-wp"),
        decay=_decay(),
        adapters=[rss_adapter, in_mem],
    )
    return wp, rss_adapter, in_mem


# ---- happy path ----


def test_multi_adapter_cycle_collects_from_both():
    """One Whirlpool runs HttpRssAdapter + InMemoryIngestAdapter.
    Cycle yields the union of both adapters' items.
    """
    wp, rss, in_mem = _build_world()
    in_mem.feed_items([_vi("aa"), _vi("bb"), _vi("cc")])

    summary = asyncio.run(wp.run_ingest_cycle())

    # Cross-adapter aggregation
    assert summary.total_items == 5    # 2 RSS + 3 in-mem
    assert len(summary.adapter_stats) == 2

    # Per-adapter isolation
    rss_stats = summary.adapter_stats[0]
    mem_stats = summary.adapter_stats[1]
    assert rss_stats.items_yielded == 2
    assert mem_stats.items_yielded == 3

    # Per-source counts isolated to the adapter that produced them
    assert "feed.example" in rss_stats.per_source_counts
    assert rss_stats.per_source_counts["feed.example"] == 2
    assert mem_stats.per_source_counts == {"seed.test": 3}


def test_multi_adapter_cycle_items_in_adapter_order():
    """summary.items lists adapter[0]'s items first, then
    adapter[1]'s.
    """
    wp, rss, in_mem = _build_world()
    in_mem.feed_items([_vi("11"), _vi("22")])

    summary = asyncio.run(wp.run_ingest_cycle())
    summaries = [it.claim_summary for it in summary.items]
    # First two are RSS (in feed order); last two are in-memory
    assert summaries[0] == "RSS Item Alpha"
    assert summaries[1] == "RSS Item Beta"
    assert summaries[2] == "in-memory item"
    assert summaries[3] == "in-memory item"


# ---- failure isolation ----


def test_one_adapter_failure_doesnt_abort_other():
    """RSS adapter fails (HTTP 500); in-memory adapter still
    runs and produces items.
    """
    wp, rss, in_mem = _build_world(
        rss_handler=lambda req: httpx.Response(500, content=b""),
    )
    in_mem.feed_items([_vi("aa"), _vi("bb")])

    summary = asyncio.run(wp.run_ingest_cycle())

    # RSS yielded zero, in-mem yielded two
    assert summary.total_items == 2
    rss_stats = summary.adapter_stats[0]
    mem_stats = summary.adapter_stats[1]
    assert rss_stats.items_yielded == 0
    assert mem_stats.items_yielded == 2

    # Failure recorded against the RSS adapter only
    assert len(rss_stats.failures) == 1
    assert rss_stats.failures[0].reason == IngestFailureReason.HTTP_ERROR
    assert mem_stats.failures == []
    assert summary.total_failures == 1


def test_in_memory_adapter_failure_doesnt_block_rss():
    """The reverse: in-memory adapter records a failure but the
    RSS adapter still runs cleanly.
    """
    wp, rss, in_mem = _build_world()
    in_mem.feed_items([_vi("xx")])
    in_mem.record_failure(IngestFailure(
        source_id="seed.test",
        reason=IngestFailureReason.PARSE_ERROR,
        detail="simulated",
    ))

    summary = asyncio.run(wp.run_ingest_cycle())

    assert summary.total_items == 3   # 2 RSS + 1 in-mem
    assert summary.total_failures == 1
    rss_stats = summary.adapter_stats[0]
    mem_stats = summary.adapter_stats[1]
    assert rss_stats.failures == []
    assert len(mem_stats.failures) == 1


# ---- cycle isolation (Q-I14=b) ----


def test_two_cycles_state_isolation():
    """A second cycle's stats reflect only that cycle, not
    cumulative.

    Cycle 1: in-memory has 2 items. Cycle 2: in-memory has 1
    fresh item. Each cycle's RSS adapter re-fetches the same
    feed (mock returns the same content).

    Expected:
      cycle 1: rss=2, in_mem=2, total=4
      cycle 2: rss=2, in_mem=1, total=3
    """
    wp, rss, in_mem = _build_world()

    # Cycle 1
    in_mem.feed_items([_vi("11"), _vi("22")])
    s1 = asyncio.run(wp.run_ingest_cycle())
    assert s1.total_items == 4
    assert s1.adapter_stats[0].items_yielded == 2  # rss
    assert s1.adapter_stats[1].items_yielded == 2  # in-mem

    # Cycle 2: feed only one new item to in-memory
    in_mem.feed_items([_vi("33")])
    s2 = asyncio.run(wp.run_ingest_cycle())
    assert s2.total_items == 3
    assert s2.adapter_stats[0].items_yielded == 2  # rss re-fetched
    assert s2.adapter_stats[1].items_yielded == 1  # in-mem fresh


def test_two_cycles_dont_share_summary():
    """The two cycles return independent IngestCycleSummary
    instances; mutating one doesn't affect the other.
    """
    wp, rss, in_mem = _build_world()
    in_mem.feed_items([_vi("aa")])
    s1 = asyncio.run(wp.run_ingest_cycle())
    in_mem.feed_items([_vi("bb")])
    s2 = asyncio.run(wp.run_ingest_cycle())

    assert s1 is not s2
    assert s1.adapter_stats[0] is not s2.adapter_stats[0]
    # Items list is a fresh list per cycle
    s1.items.clear()
    assert len(s2.items) == 3   # untouched


def test_two_cycles_in_memory_queue_drains_per_cycle():
    """If the user feeds nothing between cycles, in-memory yields
    zero on cycle 2.
    """
    wp, rss, in_mem = _build_world()
    in_mem.feed_items([_vi("aa"), _vi("bb")])
    s1 = asyncio.run(wp.run_ingest_cycle())
    s2 = asyncio.run(wp.run_ingest_cycle())   # nothing fed between

    assert s1.adapter_stats[1].items_yielded == 2
    assert s2.adapter_stats[1].items_yielded == 0
    # But RSS still re-fetches its 2 items each cycle
    assert s1.adapter_stats[0].items_yielded == 2
    assert s2.adapter_stats[0].items_yielded == 2


# ---- adapter ordering ----


def test_adapter_ordering_preserved_across_cycles():
    """Adapter[0] always runs first and its stats appear first
    in summary.adapter_stats; the order doesn't drift across
    cycles.
    """
    wp, rss, in_mem = _build_world()
    in_mem.feed_items([_vi("aa")])
    s1 = asyncio.run(wp.run_ingest_cycle())
    in_mem.feed_items([_vi("bb")])
    s2 = asyncio.run(wp.run_ingest_cycle())

    # RSS is adapter[0] in both summaries
    assert s1.adapter_stats[0].per_source_counts == {"feed.example": 2}
    assert s2.adapter_stats[0].per_source_counts == {"feed.example": 2}
    # In-memory is adapter[1] in both
    assert "seed.test" in s1.adapter_stats[1].per_source_counts
    assert "seed.test" in s2.adapter_stats[1].per_source_counts


# ---- pluggability sanity ----


def test_three_adapters_all_run():
    """Pluggability scales beyond two: three adapters of mixed
    types all run in one cycle.
    """
    wp, rss, in_mem_a = _build_world()
    in_mem_b = InMemoryIngestAdapter(source_id="other.test")
    in_mem_b.feed_items([_vi("xx"), _vi("yy")])
    # Replace the Whirlpool's adapters with three
    wp = Whirlpool(
        policy=IngestPolicy(whirlpool_id="multi-wp"),
        decay=_decay(),
        adapters=[rss, in_mem_a, in_mem_b],
    )
    in_mem_a.feed_items([_vi("zz")])

    summary = asyncio.run(wp.run_ingest_cycle())
    assert summary.total_items == 5    # 2 RSS + 1 in_mem_a + 2 in_mem_b
    assert len(summary.adapter_stats) == 3
    assert summary.adapter_stats[0].items_yielded == 2
    assert summary.adapter_stats[1].items_yielded == 1
    assert summary.adapter_stats[2].items_yielded == 2
