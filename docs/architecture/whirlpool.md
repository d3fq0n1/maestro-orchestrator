# Whirlpool — Tier 2 Live-Context Vortex

A **Whirlpool** is the component that owns Tier 2 of the three-tier
context epistemology (see [`context-tiers.md`](./context-tiers.md)). It
maintains a live, decaying store of fresh material. Items enter at the
periphery, spiral inward as corroboration and structure accumulate, and
either promote toward Cartridge candidacy or are flung outward by
centrifugal decay.

A Whirlpool does not answer prompts. It is a daemon that maintains a
ranked, decaying vortex the Router queries during context admission.

This document specifies: the ingest policy interface, the vortex data
model (rings, velocity, decay, density), domain scoping across
multiple Whirlpools, the Router query interface, the promotion-to-
Cartridge pipeline, and a summary threat model (the full threat model
is in [`vortex-threat-model.md`](./vortex-threat-model.md)). No code.

---

## Conflicts with existing design

Three decisions were resolved before drafting.

1. **Ingest source scope.** The initial implementation supports only
   HTTP/RSS polling. A pluggable `IngestAdapter` interface is
   explicitly deferred; Slack, GitHub webhooks, agent-driven external
   queries, and operator-push endpoints are out of scope until HTTP/
   RSS shakes out. This constrains the threat model and keeps the
   reference Whirlpool narrow.

2. **Module placement.** A Whirlpool is a first-class module at
   `maestro/whirlpool/` (analogous to `maestro/ncg/`). It is *not* a
   plugin under `PluginCategory`. Rationale: Whirlpools run persistent
   workers with their own lifecycle, persisted state, and background
   HTTP clients; the existing plugin system
   (`maestro/plugins/manager.py`) is designed for hook-point
   callbacks, not long-lived daemons. A new `PluginCategory.WHIRLPOOL`
   is explicitly not introduced. Extra Whirlpools are sibling modules
   or subclasses of the reference `Whirlpool` class, not plugins.

3. **Naming collision.** The task brief calls Whirlpools "agents."
   Maestro already uses `Agent` for the `fetch(prompt) -> str`
   council-member ABC (`maestro/agents/base.py`). To avoid collision,
   this document uses **Whirlpool** for the class and **ingestor** for
   the internal ingest worker. A Whirlpool is not an `Agent` and does
   not inherit from `Agent`.

---

## Terminology

- **Whirlpool** — a named, domain-scoped vortex. A deployment runs one
  or more Whirlpools.
- **Ingestor** — the internal background worker that polls sources and
  pushes raw items into a Whirlpool's periphery.
- **Vortex** — the ranked, decaying store inside a Whirlpool,
  organized into rings.
- **Item** — a unit of material in the vortex. Each item has a hash,
  a claim summary, a provenance chain, a set of corroborators, and a
  current ring depth.
- **Ring** — a quantized depth band in the vortex. Ring 0 is the
  periphery (freshly ingested, uncorroborated). Ring N (innermost) is
  promotion-candidate.

---

## Ingest Policy

Each Whirlpool has an **ingest policy** declaring what it polls and
how often. The policy is a JSON document loaded at startup and
editable at runtime (writes trigger a re-plan of the polling
schedule).

### Schema

```
IngestPolicy {
  whirlpool_id: str                // unique within a deployment
  domain_tags: list[str]           // flat and/or dotted; see §Domain Scoping
  sources: list[IngestSource]
  poll_interval_seconds: int       // default 300; per-source override below
  max_items_per_cycle: int         // default 50; bounds ingest fan-in
  dedupe_window_seconds: int       // default 86400; same-hash suppression
}

IngestSource {
  source_id: str                   // stable slug (e.g. "federal-register-rss")
  kind: "http" | "rss"             // initial scope; see Q8 decision
  url: str
  poll_interval_seconds: int | null   // overrides whirlpool default
  etag_cache_enabled: bool         // default true for rss/http
  content_type_hint: str | null    // e.g. "application/rss+xml"
  extractor: str                   // name of the body-to-claim extractor
  max_content_bytes: int           // default 1 MiB; reject-and-log above
  tls_pin_fingerprint: str | null  // optional SPKI pin; see §Security
  auth: null                       // reserved; no auth in initial scope
}
```

### Extractors

An extractor transforms a source's raw bytes into zero or more
**candidate items**. Shipped extractors in the initial scope:

- `rss.v2.item` — one item per `<item>`; claim summary = `<title>`,
  body = `<description>`, provenance = `<link>` + `<pubDate>`.
- `atom.v1.entry` — one item per `<entry>`; claim summary = `<title>`,
  body = `<summary>` or `<content>`, provenance = `<link>` +
  `<updated>`.
- `http.text.paragraphs` — naive extractor for plain-text HTTP
  responses; one item per paragraph over a minimum length.

Adding new extractors is a code change in `maestro/whirlpool/`; a
pluggable extractor registry is deferred.

### Rate and size limits

Ingest is bounded at three layers. Every limit is enforced; violation
logs and discards the offending fetch:

- per-source: `max_content_bytes`, `poll_interval_seconds` floor of 30 s.
- per-whirlpool: `max_items_per_cycle`, total simultaneous pollers = 4.
- per-host: a single remote host may not be polled from more than two
  sources concurrently; additional pollers queue.

### Source-failure handling

A source that fails five consecutive polls (HTTP 4xx/5xx, TLS error,
extractor error) is placed on a cooldown (binary exponential backoff
up to 24 h). Cooldowns are persisted so a Whirlpool restart does not
thrash failing sources.

---

## Vortex Data Model

### Rings

A vortex is a quantized depth model with N rings (default N = 5).
An item's ring is a function of:

- its age since first ingest,
- its corroboration count (number of independent sources that have
  produced an item with the same claim hash),
- its structural completeness (how many of the expected claim fields
  are populated — extractor-specific).

### Item

```
VortexItem {
  item_id: str                     // sha256 of canonical claim form
  claim_summary: str               // short human-readable
  body_hash: str                   // sha256 of raw body bytes
  provenance: list[Provenance]     // ordered, oldest first
  corroborators: set[str]          // source_ids that have produced this item
  first_ingested_at: str           // ISO8601 UTC
  last_ingested_at: str            // ISO8601 UTC
  ring: int                        // 0..N-1; 0 = periphery
  velocity: float                  // signed ring-change rate, rings/hour
  decay_remaining: float           // seconds until centrifugal expiry
  density_score: float             // see §Density
  structural_completeness: float   // 0.0 .. 1.0
  domain_tags: list[str]           // inherited from source + extractor
  promotion_eligible: bool         // see §Promotion
  flagged: list[str]               // threat diagnostics; see §Adversarial
}

Provenance {
  source_id: str
  url: str
  fetched_at: str
  etag: str | null
  content_hash: str                // sha256 of the raw bytes we fetched
}
```

`item_id` is computed from a canonical form of the claim (normalized
whitespace, NFC, lowercased tokens) so two sources publishing the
"same" claim with trivial formatting differences increment the
corroborator set rather than creating distinct items.

### Velocity

**Velocity** is the signed rate of ring change for an item.

- Positive velocity = item is moving inward (gaining corroboration
  and structural completeness faster than decay is removing it).
- Negative velocity = item is moving outward (drifting toward
  periphery as decay outpaces reinforcement).

Velocity is recomputed on every ingest tick that touches the item
and on every decay-tick that recomputes depth. A sustained-positive
velocity for an item at ring ≥ N-1 is one of the promotion triggers
(see §Promotion).

### Decay

Items decay on a per-ring schedule. Deeper rings decay slower:

```
decay_half_life_seconds[ring] =
    base_half_life * (ring_multiplier ** ring)
```

Defaults: `base_half_life = 3600` (1 h at ring 0),
`ring_multiplier = 4` (4 h at ring 1, 16 h at ring 2, 64 h at ring
3, 256 h at ring 4). Every decay tick reduces `decay_remaining` by
the elapsed wall-clock interval; an item whose `decay_remaining`
reaches zero and whose ring is 0 is evicted. An item at ring > 0
with zero remaining decays to ring - 1 and its decay is reset on
the new ring's schedule.

An item whose corroborator set gains a new source has its
`decay_remaining` refreshed to the current ring's half-life; this
is the mechanism by which reinforcement counteracts decay.

### Density

**Density** measures how clustered an item is with its neighbors in
the vortex. The vortex maintains an approximate nearest-neighbor
index (embeddings; see §Integration) keyed by `item_id`.

`density_score(item)` is the mean pairwise cosine similarity between
this item and its k nearest neighbors (default k = 8) whose ring is
within ±1 of this item's ring. Items with high density and positive
velocity are the "hot" topics the Router weights toward admission
(see [`router-distance.md`](./router-distance.md)).

Density is not a promotion trigger on its own; high density can
indicate a genuine hot topic or a manipulation attempt (see
[`vortex-threat-model.md`](./vortex-threat-model.md)).

---

## Domain Scoping Across Whirlpools

A deployment runs one or more Whirlpools, each declaring
`domain_tags` in its IngestPolicy. Items inherit the Whirlpool's
tags plus any extractor-added tags.

### Tag shape

Two forms coexist:

- **Flat tag**: a single token, e.g. `"law"`, `"protocol"`,
  `"security-advisory"`. Matched by exact-string intersection.
- **Dotted tag**: a hierarchical path, e.g.
  `"law.us.federal.statute"`. Matched by exact-string intersection
  **or** by prefix-match when *both* sides use dotted form. A query
  tagged `"law.us.federal"` matches an item tagged
  `"law.us.federal.statute"` but not an item tagged
  `"law"` (that is flat; prefix-matching does not fire).

This lets simple deployments stay flat and richer deployments adopt
dotted hierarchy incrementally.

### Router selection

The Router, given a query's inferred domain tags, asks only those
Whirlpools whose `domain_tags` intersect (flat) or prefix-match
(dotted) the query tags. A Whirlpool with tags disjoint from the
query is not consulted.

If no Whirlpool matches, the Router falls back to an untagged
broadcast query subject to a much lower admission budget (see
[`router-distance.md`](./router-distance.md)).

### Cross-Whirlpool deduplication

Two Whirlpools can ingest the same `item_id` (same canonical claim)
from different sources. The Router deduplicates by `item_id` at
candidate assembly, but the corroborator sets remain per-Whirlpool
— an item corroborated in two Whirlpools carries a higher effective
trust than one corroborated only in one.

---

## Router Query Interface

The Router calls into a Whirlpool during bundle assembly:

```
Whirlpool.query(query_embedding, query_tags, k=50, min_ring=0)
    -> list[VortexItem]
```

Returned items are the top-k by a composite score:

```
score = (ring / (N-1))                    * w_depth
      + clip(velocity, 0, v_max) / v_max  * w_velocity
      + density_score                     * w_density
      + cosine(query_embedding, item_emb) * w_relevance
```

Defaults: `w_depth = 0.4`, `w_velocity = 0.2`, `w_density = 0.1`,
`w_relevance = 0.3`.

Items flagged by the threat model (see
[`vortex-threat-model.md`](./vortex-threat-model.md)) carry a
per-flag penalty that can drive score negative; negative-score items
are never returned.

The Router applies its own admission function to the returned items
alongside Cartridge candidates; see
[`router-distance.md`](./router-distance.md) §Admission.

---

## Promotion to Cartridge

Items at ring N-1 (innermost) with sustained positive velocity over
a configurable window and corroborator count above threshold become
**promotion candidates**. The default thresholds:

- ring = N-1 for at least 48 h,
- velocity > 0 averaged over the last 24 h,
- corroborators from at least 3 distinct sources,
- structural_completeness ≥ 0.8.

When all conditions are met, the Whirlpool emits a **nomination** to
the Librarian (see [`librarian.md`](./librarian.md) §Canonicalization
Pipeline, step 1). The nomination consists of:

- the item's canonical claim form (becomes the Cartridge body after
  the Scribe applies the kind's canonical-form serializer),
- every `Provenance` record,
- the corroborator set,
- the Whirlpool's `domain_tags`,
- a proposed `kind` (inferred from extractor; may be overridden by
  MAGI review).

Nomination does not remove the item from the vortex. If the Scribe
anchors a Cartridge, a subsequent ingest tick notices the
Cartridge-coverage and collapses the vortex item — replacing its
in-vortex representation with a `CartridgeRef` so Router queries
return the canonized reference instead of the decaying candidate.

If the Scribe or MAGI rejects the nomination, the item remains in
the vortex and may re-nominate after a cooldown (default 30 days)
if corroboration continues to grow. A rejected nomination does not
eject the item from the vortex; decay still applies.

---

## Adversarial Manipulation (Summary)

Full treatment in [`vortex-threat-model.md`](./vortex-threat-model.md).
The Whirlpool must be designed to resist:

- **Sybil corroboration** — many apparent "sources" that share an
  upstream origin and are really one actor. Mitigation: corroborator
  set counts *independent* sources; independence is declared in
  `IngestSource.source_id` and enforced by an operator-maintained
  independence graph.
- **Dry-ingest flooding** — spamming low-quality items at the
  periphery to exhaust `max_items_per_cycle` and suppress genuine
  signal. Mitigation: per-source item-quality score; repeated low-
  quality emitters are cooled down.
- **Hot-topic induction** — coordinated posting to inflate density
  scores and pull attacker items toward the center. Mitigation:
  density contributes only `w_density = 0.1` in the default scoring
  weights; density signals are audited via R2 cross-session trends.
- **Provenance laundering** — reposting attacker content through
  "trusted-looking" sources. Mitigation: provenance chains are
  preserved, not summarized; MAGI review at promotion time inspects
  the chain before the Scribe anchors.
- **Revocation evasion** — reintroducing material whose Cartridge
  representation was revoked. Mitigation: Whirlpools subscribe to
  the Librarian's revocation stream and reject inbound items whose
  canonical claim hash matches a revoked Cartridge's body hash.

Flagged items remain in the vortex with their `flagged` field
populated; the Router penalizes them. Outright eviction is reserved
for items that fail extractor-level validation.

---

## Integration with Existing Maestro

### Module layout

```
maestro/whirlpool/
  __init__.py
  core.py           # Whirlpool class, ring/decay math
  ingest.py         # Ingestor worker, polling loop
  extractors.py     # rss.v2.item, atom.v1.entry, http.text.paragraphs
  index.py          # ANN index wrapper for density queries
  nominate.py       # Promotion detection and Librarian hand-off
```

### Embeddings

Density and relevance require an embedding function. The Whirlpool
uses the same embedding source as the Router (to be specified in
[`router-distance.md`](./router-distance.md)). For the reference
implementation this is the provider-neutral embedder already used
by the dissent and drift modules (`maestro/dissent.py`,
`maestro/ncg/drift.py`). No new embedding client is introduced.

### Lifecycle

A Whirlpool is started by the orchestrator process (or by a
dedicated node server — see `maestro/node_server.py`) at boot and
stopped at shutdown. The ingest worker runs in its own asyncio
task. State is persisted at `data/whirlpool/{whirlpool_id}/` with a
JSON vortex snapshot every 60 s and on graceful shutdown.

### ModManager hooks

The Whirlpool consumes no hook points today. A future extension may
emit `whirlpool_nomination` and `whirlpool_decay_eviction` events
via `ModManager.emit_event` (the event bus already exists at
`maestro/plugins/manager.py`), but this is out of scope for the
initial specification.

### R2 linkage

Every Router query that pulls from a Whirlpool is recorded in the
session's pre-hoc admission ledger entry (see
[`context-tiers.md`](./context-tiers.md) §R2 pre-hoc role). The
ledger records the `whirlpool_id`, the queried tags, the returned
`item_id` set, and the per-item score. Cross-session analysis by
MAGI can then surface Whirlpools whose admitted items correlate
with low R2 session grades.

---

## Storage Layout

```
data/whirlpool/
  {whirlpool_id}/
    policy.json           # IngestPolicy (editable; hot-reloaded)
    cooldowns.json        # per-source cooldown state
    vortex.json           # snapshot of all items (atomic write via tmp+rename)
    index/                # ANN index files
    nominations/          # emitted but not-yet-resolved Cartridge nominations
    logs/
      ingest.log          # append-only per-cycle ingest summary
      flags.log           # append-only threat-flag record
```

Rotation of `vortex.json` is out of scope for this specification; a
single snapshot plus crash-recovery from the ingest log is the
reference approach.

---

## Open Questions (deferred)

- Pluggable `IngestAdapter` interface and source-kind registry
  (deferred; current scope is HTTP/RSS only).
- Cross-deployment Whirlpool federation — currently each deployment
  runs its own Whirlpools; a future extension could gossip items
  between peers analogously to the Librarian's federation.
- Operator UI for Whirlpool inspection — not specified here; the
  reference implementation exposes a read-only JSON API.

---

## See Also

- [`context-tiers.md`](./context-tiers.md) — Three-tier overview
- [`librarian.md`](./librarian.md) — Promotion destination for
  vortex items that survive to ring N-1
- [`router-distance.md`](./router-distance.md) — How the Router
  scores and admits Whirlpool candidates
- [`vortex-threat-model.md`](./vortex-threat-model.md) — Full threat
  model for adversarial ingest
- [`../ncg.md`](../ncg.md) — NCG (analogous module placement)
- [`../architecture.md`](../architecture.md) — System overview
