"""
Smoke tests for maestro/whirlpool/ingest.HttpRssAdapter.

Step I-2 of the ingest-adapter pluggability track. Uses
``httpx.MockTransport`` (Q-I9=a) to intercept HTTP requests so
the adapter is exercised end-to-end without real network.
"""

import asyncio

import httpx
import pytest

from maestro.whirlpool.adapter import (
    CycleStats,
    IngestAdapter,
    IngestFailureReason,
)
from maestro.whirlpool.ingest import (
    HttpRssAdapter,
    HttpRssAdapterConfig,
    _source_id_from_url,
)
from maestro.whirlpool.types import RingId, VortexItem


# ---- helpers ----


def _rss(*items_xml) -> bytes:
    """Wrap item XML fragments in an RSS 2.0 channel."""
    items = "\n".join(items_xml)
    return f"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    {items}
  </channel>
</rss>""".encode("utf-8")


_SAMPLE_RSS = _rss(
    """<item>
        <title>First Article</title>
        <description>This is the first article body.</description>
        <link>https://example.com/article1</link>
    </item>""",
    """<item>
        <title>Second Article</title>
        <description>This is the second.</description>
        <link>https://example.com/article2</link>
    </item>""",
)


_SAMPLE_ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Test</title>
  <entry>
    <title>Atom First</title>
    <summary>Atom summary one.</summary>
    <link href="https://atom.example/entry1"/>
  </entry>
  <entry>
    <title>Atom Second</title>
    <summary>Atom summary two.</summary>
    <link href="https://atom.example/entry2"/>
  </entry>
</feed>"""


def _build(transport, *, urls=None, whirlpool_id="test-wp", **cfg_kwargs) -> HttpRssAdapter:
    feed_urls = urls if urls is not None else ["https://example.com/feed.xml"]
    config = HttpRssAdapterConfig(feed_urls=feed_urls, **cfg_kwargs)
    return HttpRssAdapter(config=config, whirlpool_id=whirlpool_id, transport=transport)


def _collect(adapter):
    items = []

    async def consume():
        async for item in adapter.items():
            items.append(item)

    asyncio.run(consume())
    return items


# ---- ABC compliance ----


def test_http_rss_adapter_is_an_ingest_adapter():
    cfg = HttpRssAdapterConfig(feed_urls=[])
    adapter = HttpRssAdapter(cfg, whirlpool_id="x")
    assert isinstance(adapter, IngestAdapter)


def test_http_rss_adapter_cycle_stats_empty_before_iteration():
    cfg = HttpRssAdapterConfig(feed_urls=[])
    adapter = HttpRssAdapter(cfg, whirlpool_id="x")
    assert adapter.cycle_stats() == CycleStats()


# ---- happy path: RSS ----


def test_rss_feed_yields_one_vortex_item_per_entry():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport)
    items = _collect(adapter)
    assert len(items) == 2
    assert all(isinstance(it, VortexItem) for it in items)
    assert items[0].claim_summary == "First Article"
    assert items[1].claim_summary == "Second Article"


def test_rss_items_carry_provenance():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport)
    items = _collect(adapter)
    p = items[0].provenance[0]
    assert p.source_id == "example.com"
    assert p.source_url == "https://example.com/article1"
    assert p.fetched_at != ""


def test_rss_items_have_content_addressed_id():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport)
    items = _collect(adapter)
    for it in items:
        assert it.item_id.startswith("sha256:")
        assert len(it.item_id) == len("sha256:") + 64


def test_rss_items_id_deterministic():
    """Two iterations of the same content produce the same item_id."""
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    a = _collect(_build(transport))
    b = _collect(_build(transport))
    assert a[0].item_id == b[0].item_id
    assert a[1].item_id == b[1].item_id


def test_rss_items_at_periphery_with_whirlpool_id():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport, whirlpool_id="my-wp")
    items = _collect(adapter)
    for it in items:
        assert it.whirlpool_id == "my-wp"
        assert it.ring == RingId.PERIPHERY


def test_rss_items_body_excerpt_capped_at_1kib():
    long_body = "x" * 5000
    feed = _rss(f"""<item>
        <title>Long</title>
        <description>{long_body}</description>
        <link>https://example.com/l</link>
    </item>""")
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=feed))
    adapter = _build(transport)
    items = _collect(adapter)
    assert len(items[0].body_excerpt) == 1024


# ---- happy path: Atom ----


def test_atom_feed_yields_entries():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_ATOM))
    adapter = _build(transport, urls=["https://atom.example/feed.xml"])
    items = _collect(adapter)
    assert len(items) == 2
    assert items[0].claim_summary == "Atom First"
    assert items[1].claim_summary == "Atom Second"
    # Provenance source_id should be the feed host
    assert items[0].provenance[0].source_id == "atom.example"
    # link href is captured in source_url
    assert items[0].provenance[0].source_url == "https://atom.example/entry1"


# ---- HTTPS-only enforcement (W-3) ----


def test_plain_http_url_is_refused():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport, urls=["http://insecure.example/feed.xml"])
    items = _collect(adapter)
    assert items == []
    cs = adapter.cycle_stats()
    assert len(cs.failures) == 1
    assert cs.failures[0].reason == IngestFailureReason.REFUSED_BY_POLICY
    assert cs.failures[0].source_id == "insecure.example"
    assert "non-HTTPS" in cs.failures[0].detail


def test_https_and_http_mixed_only_https_succeeds():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport, urls=[
        "https://example.com/feed.xml",
        "http://insecure.example/feed.xml",
    ])
    items = _collect(adapter)
    # Only the HTTPS feed produced items
    assert len(items) == 2
    cs = adapter.cycle_stats()
    # One refusal recorded
    assert len(cs.failures) == 1
    assert cs.failures[0].reason == IngestFailureReason.REFUSED_BY_POLICY


# ---- failure modes ----


def test_http_500_recorded_as_http_error_failure():
    transport = httpx.MockTransport(lambda req: httpx.Response(500, content=b""))
    adapter = _build(transport)
    items = _collect(adapter)
    assert items == []
    cs = adapter.cycle_stats()
    assert len(cs.failures) == 1
    assert cs.failures[0].reason == IngestFailureReason.HTTP_ERROR


def test_malformed_xml_recorded_as_parse_error():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"<rss><channel"))
    adapter = _build(transport)
    items = _collect(adapter)
    assert items == []
    cs = adapter.cycle_stats()
    assert len(cs.failures) == 1
    assert cs.failures[0].reason == IngestFailureReason.PARSE_ERROR


def test_unknown_root_element_recorded_as_parse_error():
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, content=b"<?xml version='1.0'?><something/>",
    ))
    adapter = _build(transport)
    items = _collect(adapter)
    assert items == []
    cs = adapter.cycle_stats()
    assert len(cs.failures) == 1
    assert cs.failures[0].reason == IngestFailureReason.PARSE_ERROR
    assert "unrecognized" in cs.failures[0].detail.lower() or "root" in cs.failures[0].detail.lower()


def test_one_failing_url_does_not_abort_other_urls():
    """First URL returns 500; second returns valid RSS. The good
    one yields items; the bad one is recorded as a failure.
    """
    state = {"hits": 0}

    def handler(request):
        state["hits"] += 1
        if state["hits"] == 1:
            return httpx.Response(500, content=b"")
        return httpx.Response(200, content=_SAMPLE_RSS)

    transport = httpx.MockTransport(handler)
    adapter = _build(transport, urls=[
        "https://broken.example/feed.xml",
        "https://example.com/feed.xml",
    ])
    items = _collect(adapter)
    assert len(items) == 2
    cs = adapter.cycle_stats()
    assert cs.items_yielded == 2
    assert len(cs.failures) == 1
    assert cs.failures[0].source_id == "broken.example"


def test_signature_required_currently_refuses_all():
    """require_feed_signature=True is accepted by config but no
    verification is implemented yet; document via
    SIGNATURE_INVALID failure code so a future hookup is additive.
    """
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport, require_feed_signature=True)
    items = _collect(adapter)
    assert items == []
    cs = adapter.cycle_stats()
    assert len(cs.failures) == 1
    assert cs.failures[0].reason == IngestFailureReason.SIGNATURE_INVALID


# ---- per-feed cap ----


def test_max_items_per_feed_truncates():
    items_xml = "\n".join(
        f"""<item>
            <title>Item {i}</title>
            <description>body {i}</description>
            <link>https://example.com/i{i}</link>
        </item>"""
        for i in range(20)
    )
    feed = f"""<?xml version="1.0"?>
<rss version="2.0"><channel>{items_xml}</channel></rss>""".encode("utf-8")
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=feed))
    adapter = _build(transport, max_items_per_feed=5)
    items = _collect(adapter)
    assert len(items) == 5


# ---- cycle stats ----


def test_cycle_stats_per_source_counts():
    """Two URLs from the same host should aggregate under one
    source_id; counts should reflect items yielded per source.
    """
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport, urls=[
        "https://example.com/feed1.xml",
        "https://example.com/feed2.xml",
    ])
    _collect(adapter)
    cs = adapter.cycle_stats()
    # Both feeds returned 2 items each, all under example.com
    assert cs.per_source_counts == {"example.com": 4}
    assert cs.items_yielded == 4
    assert cs.failures == []


def test_cycle_stats_records_completed_at_after_iteration():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport)
    _collect(adapter)
    cs = adapter.cycle_stats()
    assert cs.started_at != ""
    assert cs.completed_at is not None


def test_cycle_state_resets_each_iteration():
    """Calling items() a second time starts a fresh cycle: stats
    don't accumulate across cycles.
    """
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_SAMPLE_RSS))
    adapter = _build(transport)
    _collect(adapter)
    first = adapter.cycle_stats()
    _collect(adapter)
    second = adapter.cycle_stats()
    assert first.items_yielded == second.items_yielded == 2
    # per_source_counts likewise stable, not accumulated
    assert second.per_source_counts == {"example.com": 2}


# ---- helper sanity ----


def test_source_id_from_url_extracts_hostname():
    assert _source_id_from_url("https://example.com/path") == "example.com"
    assert _source_id_from_url("https://sub.example.co.uk/feed") == "sub.example.co.uk"
