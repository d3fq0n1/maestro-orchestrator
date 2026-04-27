"""
Whirlpool ingest — the HTTP/RSS reference IngestAdapter.

Step I-2 of the ingest-adapter pluggability track. Renames the
prior ``FeedFetcher`` stub to ``HttpRssAdapter``, implements it
against the ``IngestAdapter`` ABC from ``adapter.py``, and pulls
HTTP-specific config out of ``IngestPolicy`` into a dedicated
``HttpRssAdapterConfig`` dataclass.

Day 1 implementation:

* HTTPS-only ingest. Plain ``http://`` URLs are refused with
  ``IngestFailureReason.REFUSED_BY_POLICY`` (vortex-threat-model.md
  §W-3 mitigation).
* Real HTTP via ``httpx.AsyncClient`` (already a project dep).
* RSS 2.0 and Atom parsing via ``xml.etree`` (stdlib, no new dep).
  RDF / RSS 1.0 not handled day 1.
* Per-feed item cap so a single misbehaving source can't drown
  the cycle.
* Per-cycle stats accumulated in instance state and snapshotted
  by ``cycle_stats()`` (Q-I5=c shape).
* ``require_feed_signature=True`` currently refuses every feed
  (no signature verification implemented). The hook is in place
  so a future signed-feed implementation is additive.

``TagFilter`` and ``Dedup`` are adapter-agnostic and stay in this
module — they apply to items regardless of which adapter produced
them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from maestro.whirlpool.adapter import (
    CycleStats,
    IngestAdapter,
    IngestFailure,
    IngestFailureReason,
)
from maestro.whirlpool.types import (
    IngestPolicy,
    Provenance,
    RingId,
    VortexItem,
)


_ATOM_NS = "http://www.w3.org/2005/Atom"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_id_from_url(url: str) -> str:
    """Return the host part of a URL as the source_id.

    Day 1 uses the bare hostname; a future hardening step uses
    the public-suffix list to roll up subdomains (e.g.,
    ``foo.bar.example.co.uk`` -> ``example.co.uk``) so a
    publisher running multiple subdomains is corroborated as one
    source. See vortex-threat-model.md §W-1.
    """
    parsed = urlparse(url)
    return parsed.hostname or url


def _classify_http_exception(exc: Exception) -> IngestFailureReason:
    """Map httpx / xml.etree exceptions to IngestFailureReason."""
    if isinstance(exc, httpx.TimeoutException):
        return IngestFailureReason.TIMEOUT
    if isinstance(exc, httpx.HTTPStatusError):
        return IngestFailureReason.HTTP_ERROR
    if isinstance(exc, httpx.NetworkError):
        return IngestFailureReason.NETWORK_ERROR
    if isinstance(exc, ET.ParseError):
        return IngestFailureReason.PARSE_ERROR
    return IngestFailureReason.OTHER


@dataclass
class HttpRssAdapterConfig:
    """Configuration specific to the HTTP/RSS adapter.

    Adapter-agnostic fields (whirlpool_id, domain_tags,
    poll_interval_seconds, etc.) live on ``IngestPolicy`` (see
    step I-3 of this track). Only fields the HTTP/RSS adapter
    interprets belong here.
    """

    feed_urls: list = field(default_factory=list)
    require_feed_signature: bool = False
    timeout_seconds: float = 30.0
    user_agent: str = "Maestro-Whirlpool/1.0"
    max_items_per_feed: int = 100


class HttpRssAdapter(IngestAdapter):
    """Reference IngestAdapter for HTTP/RSS feeds.

    Implements ``IngestAdapter``. Iterates the configured
    ``feed_urls``, fetches each over HTTPS, parses RSS 2.0 or
    Atom, and yields one ``VortexItem`` per entry. Per-source
    stats and failures accumulate as the cycle runs and are
    snapshotted by ``cycle_stats()``.

    Construction:

      adapter = HttpRssAdapter(
          config=HttpRssAdapterConfig(feed_urls=[...]),
          whirlpool_id="law-feed",
      )

    The optional ``transport`` keyword is for testing — pass a
    ``httpx.MockTransport`` to intercept the network layer.
    """

    def __init__(
        self,
        config: HttpRssAdapterConfig,
        whirlpool_id: str,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self._config = config
        self._whirlpool_id = whirlpool_id
        self._transport = transport
        self._reset_cycle_state()

    def _reset_cycle_state(self):
        self._started_at = ""
        self._completed_at: Optional[str] = None
        self._items_yielded = 0
        self._per_source_counts: dict = {}
        self._failures: list = []

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict = {
            "timeout": self._config.timeout_seconds,
            "headers": {"User-Agent": self._config.user_agent},
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    # ---- IngestAdapter implementation ----

    async def items(self) -> AsyncIterator[VortexItem]:
        self._reset_cycle_state()
        self._started_at = _now_iso()
        try:
            async with self._build_client() as client:
                for url in self._config.feed_urls:
                    async for item in self._fetch_one(client, url):
                        yield item
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

    # ---- per-feed pipeline ----

    async def _fetch_one(self, client: httpx.AsyncClient, url: str):
        """Fetch + parse one feed URL. Records failures into
        ``self._failures`` and yields VortexItems for successful
        items. Failures do not abort the cycle.
        """
        source_id = _source_id_from_url(url)
        self._per_source_counts.setdefault(source_id, 0)

        # HTTPS-only enforcement (W-3 mitigation)
        parsed = urlparse(url)
        if parsed.scheme != "https":
            self._failures.append(IngestFailure(
                source_id=source_id,
                reason=IngestFailureReason.REFUSED_BY_POLICY,
                detail=f"non-HTTPS scheme: {parsed.scheme!r}",
            ))
            return

        # Signature requirement (placeholder — no verification yet)
        if self._config.require_feed_signature:
            self._failures.append(IngestFailure(
                source_id=source_id,
                reason=IngestFailureReason.SIGNATURE_INVALID,
                detail="require_feed_signature=True but verification not implemented",
            ))
            return

        try:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content
        except Exception as exc:
            self._failures.append(IngestFailure(
                source_id=source_id,
                reason=_classify_http_exception(exc),
                detail=f"{type(exc).__name__}: {exc}",
            ))
            return

        try:
            entries = list(self._parse_feed(content))
        except ET.ParseError as exc:
            self._failures.append(IngestFailure(
                source_id=source_id,
                reason=IngestFailureReason.PARSE_ERROR,
                detail=f"{type(exc).__name__}: {exc}",
            ))
            return
        except Exception as exc:
            self._failures.append(IngestFailure(
                source_id=source_id,
                reason=IngestFailureReason.OTHER,
                detail=f"{type(exc).__name__}: {exc}",
            ))
            return

        # Per-feed cap enforcement
        for entry in entries[: self._config.max_items_per_feed]:
            item = self._build_vortex_item(entry, source_id, url)
            self._items_yielded += 1
            self._per_source_counts[source_id] += 1
            yield item

    # ---- parsing helpers ----

    def _parse_feed(self, content: bytes):
        """Parse RSS 2.0 or Atom XML; yield ``(title, body, link)``
        triples. Caller wraps each into a VortexItem.
        """
        root = ET.fromstring(content)

        # RSS 2.0: <rss><channel><item>...
        if root.tag == "rss":
            channel = root.find("channel")
            if channel is None:
                return
            for entry in channel.findall("item"):
                title = (entry.findtext("title") or "").strip()
                body = (entry.findtext("description") or "").strip()
                link = (entry.findtext("link") or "").strip()
                yield (title, body, link)
            return

        # Atom: <feed><entry>...  (with namespace)
        if root.tag in ("feed", f"{{{_ATOM_NS}}}feed"):
            ns = {"atom": _ATOM_NS}
            # Try with namespace first, then without
            entries = root.findall("atom:entry", ns) or root.findall("entry")
            for entry in entries:
                title = (
                    entry.findtext("atom:title", default="", namespaces=ns)
                    or entry.findtext("title")
                    or ""
                ).strip()
                body = (
                    entry.findtext("atom:summary", default="", namespaces=ns)
                    or entry.findtext("atom:content", default="", namespaces=ns)
                    or entry.findtext("summary")
                    or entry.findtext("content")
                    or ""
                ).strip()
                # Element objects with no children are falsy in
                # Python, so ``a or b`` would skip a found-but-childless
                # link element. Use explicit None checks.
                link_elem = entry.find("atom:link", ns)
                if link_elem is None:
                    link_elem = entry.find("link")
                link = link_elem.get("href", "") if link_elem is not None else ""
                yield (title, body, link)
            return

        # Unknown root — treat as parse error to be conservative
        raise ET.ParseError(
            f"unrecognized feed root element: {root.tag!r} "
            f"(expected 'rss' or 'feed')"
        )

    def _build_vortex_item(
        self,
        entry: tuple,
        source_id: str,
        feed_url: str,
    ) -> VortexItem:
        title, body, link = entry
        # Content hash over title + body. Deterministic per claim.
        content = f"{title}\n\n{body}".encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        item_id = f"sha256:{digest}"

        # body_excerpt cap mirrors the preamble cap of 1 KiB
        excerpt = body[:1024]
        summary = title or body[:200]

        provenance = [Provenance(
            source_id=source_id,
            source_url=link or feed_url,
            fetched_at=_now_iso(),
            publisher_signature=None,
            publisher_age_days=0,
        )]

        return VortexItem(
            item_id=item_id,
            whirlpool_id=self._whirlpool_id,
            claim_summary=summary,
            body_excerpt=excerpt,
            domain_tags=[],     # Whirlpool's TagFilter assigns these
            provenance=provenance,
            ring=RingId.PERIPHERY,
            corroborators=1,
            entered_at=_now_iso(),
            last_moved_at=_now_iso(),
            expires_at="",     # Vortex sets this on insert
            trust=0.0,         # Router computes
            embedding=None,
        )


# ---- adapter-agnostic stages (unchanged from prior scaffold) ----


class TagFilter:
    """Hard-enforces the Whirlpool's declared ``domain_tags`` namespace.

    Items carrying tags outside the namespace are stripped, not
    demoted. See vortex-threat-model.md §W-4.
    """

    def __init__(self, policy: IngestPolicy):
        self._policy = policy

    def filter(self, item: VortexItem) -> VortexItem:
        """Return the item with undeclared tags stripped."""
        # TODO (out of scope for I-2; Whirlpool integration in I-4).
        raise NotImplementedError


class Dedup:
    """Syndication-aware deduplication.

    Corroboration counts distinct publishers, not distinct URLs.
    See vortex-threat-model.md §W-1 and whirlpool.md §Dedup.
    """

    def __init__(self):
        # TODO (out of scope for I-2; Whirlpool integration in I-4).
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
