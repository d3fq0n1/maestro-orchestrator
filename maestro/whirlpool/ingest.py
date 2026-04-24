"""
Whirlpool ingest — HTTP/RSS polling.

See docs/architecture/whirlpool.md §Ingest Policy Interface.

Day 1 scope (Q8 = a): HTTP/RSS polling only. No Slack webhook, no
LLM-driven ingest, no pluggable adapter interface. A future
pluggable adapter spec is deferred.

Ingest is responsible for:
  - fetching feeds over HTTPS (plain HTTP refused, see
    vortex-threat-model.md §W-3)
  - normalizing publisher identity by registrable domain
  - deduplicating syndicated content
  - recording provenance (the observed URL / headers / signature,
    NOT content's self-declared provenance, see §T-4)
  - filtering tags against the Whirlpool's declared namespaces (§W-4)
  - emitting VortexItem objects into the vortex
"""

from dataclasses import dataclass
from typing import Optional

from maestro.whirlpool.types import IngestPolicy, VortexItem


@dataclass
class FeedFetchResult:
    """Outcome of a single feed fetch."""

    feed_url: str
    items_ingested: int
    items_rejected: int
    rejection_reasons: dict    # {reason: count}
    fetched_at: str


class FeedFetcher:
    """HTTP/RSS feed fetcher.

    Refuses plain HTTP. Verifies TLS. Records the observed HTTP
    signature or Atom signature if present; raises fresh-publisher
    weight only for signed feeds.
    """

    def __init__(self, policy: IngestPolicy):
        self._policy = policy

    async def fetch_once(self) -> list:
        """Run one ingest cycle across all configured feed_urls.

        Returns a list[FeedFetchResult], one per URL.
        """
        # TODO: httpx.AsyncClient, refuse non-https, concurrency-limited
        raise NotImplementedError

    async def fetch_feed(self, url: str) -> list:
        """Fetch and parse a single feed. Returns list[VortexItem]."""
        # TODO
        raise NotImplementedError


class TagFilter:
    """Hard-enforces the Whirlpool's declared domain_tags namespace.

    Items carrying tags outside the namespace are stripped, not
    demoted. See vortex-threat-model.md §W-4.
    """

    def __init__(self, policy: IngestPolicy):
        self._policy = policy

    def filter(self, item: VortexItem) -> VortexItem:
        """Return the item with undeclared tags stripped."""
        # TODO
        raise NotImplementedError


class Dedup:
    """Syndication-aware deduplication.

    Corroboration counts distinct publishers, not distinct URLs.
    See vortex-threat-model.md §W-1 and whirlpool.md §Dedup.
    """

    def __init__(self):
        # TODO: in-memory hash set keyed by item_id; periodically
        # spilled to data/whirlpool/{whirlpool_id}/seen_ids
        pass

    def observe(self, item: VortexItem, publisher_id: str) -> Optional[VortexItem]:
        """Record an observation of an item by a publisher.

        Returns:
          - None if this is a redundant observation (same publisher,
            same item)
          - a VortexItem with updated corroborators count if a new
            publisher corroborated a previously-seen item
          - the given item (with corroborators=1) if first observation
        """
        # TODO
        raise NotImplementedError
