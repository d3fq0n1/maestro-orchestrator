# Maestro Orchestra — Live Leaderboard & Public Dashboard

**Status:** Planning
**Version Target:** v0.9
**Last Updated:** 2026-03-19

---

## Purpose

Orchestra is Maestro's public-facing proof of concept. It makes the distributed weight
orchestration thesis *visible and verifiable* by exposing real-time metrics from the
WeightHost mesh to a live dashboard and leaderboard.

The goal is twofold:

1. **Developer tool** — monitor WeightHost health, routing decisions, consensus quality,
   and MAGI analysis outcomes across the distributed network in real time.
2. **Public artifact** — demonstrate to the outside world that models are *hosted
   persistently* and *routed to*, not spun up cold per-request. Every metric on the
   dashboard reinforces this distinction.

---

## Architecture

```
                          +---------------------+
                          |   Orchestra Web UI  |
                          |  (SvelteKit / SSR)  |
                          +----------+----------+
                                     |
                              WebSocket + REST
                                     |
                          +----------+----------+
                          |  Orchestra Service  |
                          |  (Python / FastAPI)  |
                          +----------+----------+
                                     |
                     +---------------+---------------+
                     |               |               |
              +------+------+ +-----+-----+ +-------+-------+
              | Maestro Core| |  R2 Ledger | | WeightHost    |
              | Orchestrator| |  (data/r2) | | Registry      |
              | API         | |            | | (shard_registry)|
              +--------------+ +-----------+ +---------------+
```

### Components

**Orchestra Service** (`services/orchestra/service.py`)
A lightweight FastAPI process that:
- Subscribes to Maestro's SSE stream for real-time orchestration events
- Polls the R2 ledger and WeightHost registry at configurable intervals
- Maintains a rolling window of time-series metrics in SQLite
- Exposes WebSocket endpoints for live dashboard updates
- Serves pre-aggregated leaderboard data via REST

**Orchestra Web UI** (`services/orchestra/web/`)
A SvelteKit application (SSR for SEO, hydrated for interactivity) that:
- Connects to Orchestra Service via WebSocket for live updates
- Renders the leaderboard, live feed, and per-host detail views
- Operates as a static export for zero-dependency hosting, or as a
  server-rendered app for dynamic SEO

### Tech Stack Recommendation

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Frontend | **SvelteKit** | Smaller bundle than Next.js, native SSR, excellent WebSocket ergonomics. Solo developer context — less boilerplate. |
| Live transport | **WebSocket** (with SSE fallback) | Bidirectional not strictly needed, but WebSocket gives lower overhead for high-frequency metric pushes. SSE fallback for restricted environments. |
| Time-series store | **SQLite + WAL mode** | No external dependency. WAL mode handles concurrent reads from the web layer while the service writes. Sufficient for single-node metric volumes. Upgrade path to TimescaleDB if needed. |
| Metrics collection | **In-process polling + SSE subscription** | Orchestra Service runs alongside Maestro Core. Direct import for R2/registry reads, SSE subscription for live orchestration events. |
| Deployment | **Docker Compose sidecar** | Added as a service in the existing `docker-compose.yml`. Shares the `data/` volume for direct ledger access. |

---

## Data Model

### WeightHost Metrics (per host, per interval)

```python
@dataclass
class WeightHostMetric:
    host_id: str
    timestamp: datetime
    # Availability
    status: str                    # available, busy, offline, probation, evicted
    uptime_seconds: int            # cumulative since last offline transition
    warm: bool                     # weights hot in memory
    # Performance
    mean_latency_ms: float         # rolling mean response latency
    p95_latency_ms: float          # 95th percentile latency
    queries_served: int            # total queries routed to this host
    queries_last_hour: int         # throughput indicator
    # Quality
    reputation_score: float        # from proof-of-storage engine (0.0-1.0)
    proof_pass_rate: float         # PoRep + PoRes + PoI combined pass rate
    r2_contribution_score: float   # quality of consensus contributions
    # Weight locality
    hardware_class: str            # cloud_api, local_gpu, edge_node
    domain_affinities: list[str]   # declared domain strengths
    shard_count: int               # number of layer ranges held
    layer_coverage: str            # e.g. "0-15/80" — layers held vs model total
    # Thesis visibility
    weight_locality_score: float   # current routing preference (0.25-1.0)
    cold_starts: int               # times this host went cold and was re-warmed
```

### Consensus Metrics (per session)

```python
@dataclass
class ConsensusMetric:
    session_id: str
    timestamp: datetime
    # Consensus quality
    r2_grade: str                  # strong, acceptable, weak, suspicious
    confidence_score: float        # 0.0-1.0
    agreement_ratio: float         # fraction of agents in majority cluster
    quorum_met: bool
    # Dissent
    dissent_level: str             # none, low, moderate, high
    outlier_agents: list[str]
    mean_pairwise_distance: float
    # NCG
    ncg_mean_drift: float          # distance from headless baseline
    silent_collapse: bool
    compression_detected: bool
    # Deliberation
    deliberation_rounds: int
    deliberation_enabled: bool
    # Routing (thesis visibility)
    hosts_used: list[str]          # which WeightHosts served this query
    pipeline_hops: int             # number of hosts in the inference pipeline
    routing_strategy: str          # locality, failover, load_balance
```

### Leaderboard Entry (aggregated)

```python
@dataclass
class LeaderboardEntry:
    host_id: str
    rank: int
    # Composite score (weighted blend of all factors)
    composite_score: float
    # Individual dimensions
    accuracy_score: float          # r2_contribution_score aggregate
    consensus_rate: float          # fraction of sessions where host was in majority
    dissent_quality: float         # when host dissented, how often was dissent validated
    mean_latency_ms: float
    uptime_ratio: float            # available_seconds / total_seconds
    weight_persistence: float      # fraction of time weights stayed warm
    # Metadata
    hardware_class: str
    domain_affinities: list[str]
    layer_coverage: str
    last_active: datetime
```

---

## Proposed Directory Structure

```
services/
  orchestra/
    __init__.py
    service.py               # FastAPI app — metrics collection, WebSocket, REST
    config.py                # Orchestra-specific configuration
    models.py                # Data models (WeightHostMetric, ConsensusMetric, etc.)
    collectors/
      __init__.py
      weighthost.py          # Polls WeightHostRegistry, computes per-host metrics
      consensus.py           # Subscribes to orchestration events, extracts consensus metrics
      magi.py                # Polls MAGI reports for cross-session health data
    store.py                 # SQLite time-series store (write, query, retention)
    leaderboard.py           # Aggregation logic for leaderboard computation
    feed.py                  # Live feed formatter (anonymized routing decisions)
    web/
      package.json
      svelte.config.js
      src/
        routes/
          +page.svelte       # Landing — live overview + thesis statement
          +layout.svelte     # Shared chrome, WebSocket provider
          leaderboard/
            +page.svelte     # Sortable, filterable leaderboard table
          host/
            [id]/
              +page.svelte   # Per-host detail view (metrics over time)
          feed/
            +page.svelte     # Live anonymized routing feed
          about/
            +page.svelte     # Thesis explanation, link to ARCHITECTURE.md
        lib/
          ws.ts              # WebSocket client wrapper
          types.ts           # TypeScript interfaces matching Python models
          stores.ts          # Svelte stores for reactive metric state
          charts.ts          # Chart helpers (lightweight — Chart.js or uPlot)
        components/
          LeaderboardTable.svelte
          MetricCard.svelte
          HostDetailChart.svelte
          LiveFeed.svelte
          QuorumGauge.svelte
          ThesisCallout.svelte   # Visual element reinforcing weight persistence
```

---

## API Endpoints — Maestro Core Must Expose

Orchestra needs the following data from Maestro Core. Endpoints marked with `*` already
exist. New endpoints are listed with their proposed shape.

### Existing (usable as-is)

| Endpoint | Source | Data |
|----------|--------|------|
| `GET /api/sessions` * | `api_sessions.py` | Recent session list with R2 grades |
| `GET /api/sessions/{id}` * | `api_sessions.py` | Full session record (agents, consensus, dissent, NCG) |
| `GET /api/magi` * | `api_magi.py` | Cross-session MAGI analysis |
| `GET /api/storage/network/topology` * | `api_storage.py` | Full WeightHost mesh state |
| `GET /api/stream` * | SSE | Real-time orchestration events |

### New Endpoints Needed

```
GET /api/orchestra/hosts
  Returns: List of WeightHostMetric for all registered hosts
  Includes computed weight_locality_score, uptime, throughput

GET /api/orchestra/hosts/{host_id}/history
  Query: ?window=1h|6h|24h|7d (default 24h)
  Returns: Time-series of WeightHostMetric snapshots for a single host

GET /api/orchestra/leaderboard
  Query: ?sort_by=composite|accuracy|latency|uptime|consensus_rate
         &hardware_class=all|cloud_api|local_gpu|edge_node
  Returns: Ranked list of LeaderboardEntry

GET /api/orchestra/feed
  Query: ?limit=50 (default 50)
  Returns: Recent anonymized routing decisions with pipeline composition

GET /api/orchestra/consensus/summary
  Query: ?window=1h|6h|24h|7d
  Returns: Aggregate consensus stats (grade distribution, mean confidence,
           collapse frequency, dissent trend)

WebSocket /api/orchestra/ws
  Pushes: Real-time metric updates, new session results, host status changes
  Frame format: { "type": "host_metric"|"session_result"|"status_change",
                  "data": {...} }
```

---

## Metrics Orchestra Should Track Per WeightHost/WeightNode

### Availability & Persistence
- **Uptime ratio** — `available_seconds / total_registered_seconds`
- **Weight persistence** — fraction of uptime where `warm == True` (weights hot in memory)
- **Cold start count** — number of warm-to-cold transitions (lower is better)
- **Heartbeat regularity** — standard deviation of heartbeat intervals
- **Status history** — timeline of status transitions (available/busy/offline/probation)

### Performance
- **Mean response latency** — rolling average across served queries
- **P95 latency** — tail latency indicator
- **Throughput** — queries served per hour
- **Pipeline position frequency** — how often this host is first/middle/last in pipeline

### Quality & Trust
- **Reputation score** — from proof-of-storage engine
- **Proof pass rate** — PoRep + PoRes + PoI combined
- **R2 contribution score** — quality grade of sessions this host participated in
- **Consensus participation rate** — fraction of sessions where host was in majority cluster
- **Dissent quality** — when host's agent dissented, how often was it "healthy dissent" vs outlier

### Weight Locality (Thesis Metrics)
- **Weight locality score** — current routing preference (0.25-1.0)
- **Domain affinity utilization** — fraction of queries that matched declared affinities
- **Shard coverage** — layers held vs model total
- **Routing preference rank** — where this host ranks among all hosts for a typical query
- **Query travel distance** — network hops from query origin to this host (when measurable)

### Network Topology
- **Peer count** — number of adjacent hosts in the mesh
- **Redundancy factor** — number of other hosts holding the same layer ranges
- **Pipeline participation** — number of distinct inference pipelines this host appears in

---

## Thesis Visibility — How Orchestra Reinforces the Core Thesis

Orchestra is not just a monitoring tool. It is a *public argument* for the weight
persistence model. Every design choice should make the following points visually obvious:

### 1. Weights Are Persistent, Not Ephemeral
- The **weight persistence** metric (fraction of time warm) is displayed prominently
  on every host card. A host that stays warm for hours or days is visually distinct
  from one that cold-starts on every query.
- **Cold start count** is displayed as a negative indicator — fewer cold starts = better.
- The landing page shows a real-time count of "weights currently hot across the network."

### 2. Queries Travel to Weights
- The **live feed** shows anonymized routing decisions: "Query → Host A (warm, affinity
  match, locality 1.0)" makes the routing logic legible.
- **Pipeline visualization** shows multi-hop inference: "Query → Host A (layers 0-15) →
  Host B (layers 16-31) → Response" — this cannot happen in a centralized architecture.
- **Query travel distance** metric (when available) makes the physical routing tangible.

### 3. Distributed Inference Is Viable
- The **leaderboard** ranks edge nodes alongside cloud APIs. If a Raspberry Pi cluster
  achieves comparable consensus quality to a cloud API, the leaderboard makes that visible.
- **Hardware class filter** on the leaderboard lets visitors compare edge vs cloud directly.
- **Uptime ratio** for edge nodes demonstrates that commodity hardware can be reliable.

### 4. Quality Is Measurable
- **R2 grades** and **MAGI analysis** are surfaced in real time. The system doesn't just
  claim quality — it proves it with continuous measurement.
- **Dissent quality** shows that the system values structured disagreement, not just agreement.
- **Silent collapse detection** is displayed as a live indicator — visitors can see when
  the system catches conformity pressure in real time.

### Thesis Callout Component
A persistent UI element on every page:

> **Maestro routes queries to persistent weights.**
> Every model on this dashboard holds its weights in memory continuously.
> Queries travel to where weights already live — not the other way around.
> [Read the architecture →](./ARCHITECTURE.md)

---

## Implementation Notes

### Phase 1 — Backend & Data Collection
- Implement `services/orchestra/` Python package
- SQLite store with 7-day default retention, configurable
- Collectors for WeightHost registry, R2 ledger, orchestration SSE
- REST endpoints for leaderboard and host metrics
- WebSocket endpoint for live updates
- Add as Docker Compose sidecar service

### Phase 2 — Frontend & Visualization
- SvelteKit scaffold with WebSocket integration
- Landing page with live network overview
- Leaderboard with sort/filter
- Per-host detail view with time-series charts
- Live routing feed

### Phase 3 — Public Deployment
- Static export option for GitHub Pages / Cloudflare Pages
- Rate limiting on public API
- Anonymization rules for query content (already planned — feed shows routing
  decisions, never query content)
- SEO metadata for discoverability

### Constraints
- No external time-series database — SQLite WAL is sufficient at single-node scale
- No authentication for read-only public dashboard (write APIs remain behind existing auth)
- Orchestra Service must not import Maestro internals at module level — use REST/SSE
  for decoupling, with optional direct import for co-located deployments
- All metrics must be derivable from data Maestro already collects — no new
  instrumentation burden on the core pipeline
