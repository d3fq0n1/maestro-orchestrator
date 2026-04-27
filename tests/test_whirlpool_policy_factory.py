"""
Smoke tests for the IngestPolicy refactor + factory.build_adapters.

Step I-3 of the ingest-adapter pluggability track. Verifies:

  * IngestPolicy no longer carries adapter-specific fields
    (feed_urls, require_feed_signature) — those moved to
    HttpRssAdapterConfig in step I-2.
  * IngestPolicy carries a typed slot ``http_rss: list[
    HttpRssAdapterConfig]`` for declarative configuration.
  * ``build_adapters(policy)`` walks the slots and returns one
    IngestAdapter per config, bound to the policy's
    whirlpool_id.
"""

import pytest

from maestro.whirlpool import (
    HttpRssAdapter,
    HttpRssAdapterConfig,
    IngestAdapter,
    IngestPolicy,
    build_adapters,
)


# ---- IngestPolicy field surface ----


def test_ingest_policy_no_longer_has_adapter_specific_fields():
    """feed_urls and require_feed_signature moved to
    HttpRssAdapterConfig. IngestPolicy must not carry them.
    """
    fields = {f.name for f in IngestPolicy.__dataclass_fields__.values()}
    assert "feed_urls" not in fields
    assert "require_feed_signature" not in fields


def test_ingest_policy_keeps_adapter_agnostic_fields():
    fields = {f.name for f in IngestPolicy.__dataclass_fields__.values()}
    assert "whirlpool_id" in fields
    assert "domain_tags" in fields
    assert "poll_interval_seconds" in fields
    assert "max_items_per_cycle" in fields
    assert "per_source_partition_cap" in fields


def test_ingest_policy_has_typed_http_rss_slot():
    fields = {f.name for f in IngestPolicy.__dataclass_fields__.values()}
    assert "http_rss" in fields
    p = IngestPolicy(whirlpool_id="x")
    assert p.http_rss == []  # default empty


def test_ingest_policy_accepts_http_rss_configs():
    cfg_a = HttpRssAdapterConfig(feed_urls=["https://a.example/feed"])
    cfg_b = HttpRssAdapterConfig(feed_urls=["https://b.example/feed"])
    p = IngestPolicy(whirlpool_id="x", http_rss=[cfg_a, cfg_b])
    assert p.http_rss == [cfg_a, cfg_b]


# ---- build_adapters ----


def test_build_adapters_empty_policy_returns_empty_list():
    p = IngestPolicy(whirlpool_id="empty-wp")
    assert build_adapters(p) == []


def test_build_adapters_one_http_rss_config_returns_one_adapter():
    cfg = HttpRssAdapterConfig(feed_urls=["https://a.example/feed"])
    p = IngestPolicy(whirlpool_id="single-wp", http_rss=[cfg])
    adapters = build_adapters(p)

    assert len(adapters) == 1
    assert isinstance(adapters[0], IngestAdapter)
    assert isinstance(adapters[0], HttpRssAdapter)


def test_build_adapters_multiple_http_rss_configs_returns_multiple_adapters():
    """Q-I11 = b: multiple HttpRssAdapter instances under one
    Whirlpool is legitimate. Each config in the slot yields one
    adapter.
    """
    cfgs = [
        HttpRssAdapterConfig(feed_urls=["https://legal.example/rss"]),
        HttpRssAdapterConfig(feed_urls=["https://medical.example/rss"]),
        HttpRssAdapterConfig(feed_urls=["https://policy.example/rss"]),
    ]
    p = IngestPolicy(whirlpool_id="multi-wp", http_rss=cfgs)
    adapters = build_adapters(p)

    assert len(adapters) == 3
    assert all(isinstance(a, HttpRssAdapter) for a in adapters)


def test_build_adapters_propagates_whirlpool_id():
    """All adapters returned share the policy's whirlpool_id, so
    items they yield are stamped consistently.
    """
    cfgs = [
        HttpRssAdapterConfig(feed_urls=["https://a.example/feed"]),
        HttpRssAdapterConfig(feed_urls=["https://b.example/feed"]),
    ]
    p = IngestPolicy(whirlpool_id="my-wp", http_rss=cfgs)
    adapters = build_adapters(p)
    for adapter in adapters:
        # Internal attribute access; not part of the public API
        # but the bound id is what matters for the contract.
        assert adapter._whirlpool_id == "my-wp"


def test_build_adapters_preserves_per_config_settings():
    """Each adapter wraps its own config, so per-instance settings
    (timeout, max items, etc.) don't bleed across.
    """
    cfg_a = HttpRssAdapterConfig(
        feed_urls=["https://a.example/feed"],
        timeout_seconds=10.0,
        max_items_per_feed=5,
    )
    cfg_b = HttpRssAdapterConfig(
        feed_urls=["https://b.example/feed"],
        timeout_seconds=60.0,
        max_items_per_feed=200,
    )
    p = IngestPolicy(whirlpool_id="x", http_rss=[cfg_a, cfg_b])
    adapters = build_adapters(p)
    assert adapters[0]._config is cfg_a
    assert adapters[1]._config is cfg_b
    assert adapters[0]._config.timeout_seconds == 10.0
    assert adapters[1]._config.timeout_seconds == 60.0


def test_build_adapters_returns_distinct_instances():
    """Two adapters built from one policy must be distinct
    objects so per-cycle stats track separately.
    """
    cfgs = [
        HttpRssAdapterConfig(feed_urls=["https://a.example/feed"]),
        HttpRssAdapterConfig(feed_urls=["https://b.example/feed"]),
    ]
    p = IngestPolicy(whirlpool_id="x", http_rss=cfgs)
    adapters = build_adapters(p)
    assert adapters[0] is not adapters[1]


def test_build_adapters_called_twice_returns_fresh_instances():
    """Repeated calls to build_adapters with the same policy
    produce fresh adapter instances. The policy is data; it
    doesn't memoize adapter construction.
    """
    cfg = HttpRssAdapterConfig(feed_urls=["https://a.example/feed"])
    p = IngestPolicy(whirlpool_id="x", http_rss=[cfg])
    a = build_adapters(p)
    b = build_adapters(p)
    assert a[0] is not b[0]
