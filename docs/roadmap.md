# Maestro-Orchestrator Roadmap

**Current Version:** v7.4.0
**Last Updated:** 2026-03-19
**Maintainer:** defcon

---

## North Star

**Distributed Perpetual Weight Orchestration** — a network of persistent AI weight hosts
coordinated by a sovereign control plane, capable of epistemic consensus, dissent analysis,
and self-improvement without centralized inference dependency.

The thesis: **route queries to persistent weights, not weights to queries.** Every phase
of this roadmap advances toward a world where inference is a distributed resource held by
many, not a monopoly service rented from few.

The canonical articulation of this thesis lives in [`ARCHITECTURE.md`](../ARCHITECTURE.md).

---

## Phase 1: Foundation (Complete)

*Build the epistemic core — multi-agent consensus with quality measurement.*

- [x] **Core Orchestration** — Quorum-based multi-agent orchestration with parallel agent queries, semantic similarity clustering, 66% supermajority consensus
- [x] **Agent Council** — Four council agents (GPT-4o, Claude Sonnet 4.6, Gemini 2.5 Flash, Llama 3.3 70B) with shared async interface and swappable module isolation
- [x] **Deliberation Engine** — Multi-round peer-aware refinement before analysis; configurable rounds (1-5), non-fatal, all downstream analysis operates on deliberated positions
- [x] **Dissent Analysis** — Pairwise semantic distance, outlier detection, internal agreement scoring, cross-session trend analysis
- [x] **NCG Module** — Novel Content Generation with headless baseline, drift detection, silent collapse prevention, compression alerts
- [x] **R2 Engine** — Session scoring (strong/acceptable/weak/suspicious), consensus ledger indexing, structured improvement signal generation
- [x] **MAGI Module** — Cross-session pattern analysis, confidence trends, collapse frequency tracking, structured recommendations
- [x] **Self-Improvement Pipeline** — MAGI analysis -> code introspection (AST, signal-to-code) -> optimization proposals -> MAGI_VIR sandboxed validation -> promote/reject -> optional injection with InjectionGuard, rollback, and smoke testing
- [x] **Session History** — Persistent JSON-based session and ledger records with unified data layer
- [x] **FastAPI Backend** — Full analysis pipeline on every request; SSE streaming; REST API for sessions, MAGI, storage, self-improvement, plugins, keys
- [x] **React Web UI** — R2 grades, quorum bar, dissent visualization, NCG drift, session browser, storage network topology, LAN discovery
- [x] **TUI Dashboard** — Textual-based terminal UI optimized for SoC devices; mainframe-style navigation, shard network monitor, LAN discovery, cluster instance management
- [x] **Interactive CLI** — Full orchestration pipeline in the terminal with self-improvement commands
- [x] **Docker Containerization** — One-step deployment of backend + frontend; multi-service compose with orchestrator + shard workers + Redis + Postgres
- [x] **Auto-Updater** — Background polling with configurable intervals, SSE notifications, auto-apply option, Docker rebuild support

*Detailed version history: v0.1 through v7.4.0 — see git log for granular changelog.*

---

## Phase 2: Distributed Runtime (In Progress)

*Make the weight persistence thesis mechanically real across multiple hosts.*

- [x] **WeightHost Abstraction** — `WeightHost` dataclass with capability manifests (domain affinity, warmth state, hardware class), replacing generic "storage node" terminology throughout the codebase
- [x] **Weight Locality Routing** — `weight_locality_score()` function computing routing preference (0.25-1.0) based on warmth and domain affinity; load-bearing in pipeline construction
- [x] **WeightHostRegistry** — Topology-aware registry with pipeline construction, redundancy maps, heartbeat tracking, reputation integration, shard-level capability declarations
- [x] **Proof-of-Storage** — Cryptographic challenge-response verification (PoRep, PoRes, PoI); reputation scoring integrated with R2; automatic eviction below 0.3 reputation
- [x] **ShardAgent** — Distributed inference agent with failover; standalone node server for weight host participation
- [x] **Cluster Instance Spawning** — TUI-driven cluster formation with auto-assigned names/IPs/shard indices, shared Docker network and Redis
- [x] **LAN Peer Discovery** — Automatic discovery of adjacent Maestro nodes on the local network
- [x] **Plugin Architecture** — Modular plugin lifecycle with 8 pipeline hook points, event bus, PluginContext, hook ownership tracking
- [ ] **Interactive Sessions** — Human agent participates in deliberations alongside AI agents in real time
- [ ] **Token-Level NCG** — Logprob-level drift measurement across all providers (OpenAI built, pending Anthropic/Google)
- [ ] **NCG Feedback Loops** — Reshape prompts based on drift signals before they reach conversational agents
- [ ] **WeightHost Clustering** — Multi-orchestrator coordination: multiple Maestro instances sharing a WeightHost mesh with consensus on routing decisions
- [ ] **Docker Compose Sharding** — Configuration-driven shard topology: define model layer assignments per container in compose config rather than manual registration
- [ ] **Plugin Marketplace** — Curated plugin registry with versioning, dependency resolution, one-click install
- [ ] **Local Model Support** — Agent wrappers for llamacpp, Ollama, and other local inference runtimes as first-class WeightHosts
- [ ] **ESP32 SoC Support** — Lightweight node agent for microcontrollers as edge WeightHosts

---

## Phase 3: Orchestra (Planned)

*Make the distributed weight thesis visible and verifiable to the outside world.*

Orchestra is a live, public-facing dashboard and leaderboard that visualizes AI model
performance across the Maestro distributed network in real time. It is both a developer
monitoring tool and a public proof of concept for the weight persistence model.

See [`ORCHESTRA.md`](../ORCHESTRA.md) for the full feature specification.

- [ ] **Orchestra Service** — Lightweight FastAPI sidecar collecting WeightHost metrics, consensus data, and routing decisions into a SQLite time-series store
- [ ] **Live Leaderboard** — WeightHosts ranked by accuracy, consensus rate, dissent quality, latency, uptime, and weight persistence; filterable by hardware class
- [ ] **Real-Time Dashboard** — WebSocket-driven live view of network health, R2 grades, MAGI analysis, and active weight host count
- [ ] **Routing Feed** — Anonymized live stream of query routing decisions showing pipeline composition, locality scores, and multi-hop inference paths
- [ ] **Per-Host Detail Views** — Time-series charts of individual WeightHost metrics: latency, throughput, reputation, warmth duration
- [ ] **Thesis Visualization** — Dedicated UI elements making weight persistence tangible: cold start counts, warmth duration, query-to-weight routing paths, edge vs cloud comparison
- [ ] **Public Deployment** — Static export for GitHub Pages / Cloudflare Pages with rate-limited public API; SEO metadata
- [ ] **Orchestra API** — New endpoints on Maestro Core: `/api/orchestra/hosts`, `/api/orchestra/leaderboard`, `/api/orchestra/feed`, `/api/orchestra/ws`

---

## Phase 4: Perpetual Network (Future)

*Persistent weight hosts operating as autonomous infrastructure, self-improving
through continuous epistemic measurement.*

- [ ] **Persistent WeightHosts** — Hosts that maintain warm weights across reboots via checkpoint-resume; weight state survives process lifecycle
- [ ] **Proof-of-Storage Inference** — Extend PoI challenges to continuous background verification; hosts prove ongoing inference capability, not just data possession
- [ ] **Cross-Session NCG Baselines** — Track "normal" headless output profiles over time to detect gradual model drift and RLHF pressure shifts
- [ ] **Autonomous Self-Improvement (MAGI_VIR)** — Graduate from opt-in injection to autonomous threshold tuning within validated safety bounds; MAGI proposes, validates, and applies low-risk optimizations without human intervention
- [ ] **Decentralized Consensus Layer** — Cross-host quorum: WeightHosts participate directly in epistemic consensus, not just as inference backends
- [ ] **Multilingual Agent Specialization** — Language-specialized agents as WeightHosts with domain affinity for specific language families
- [ ] **Reinforcement Loop** — Feed consensus outcomes and R2 quality data into fine-tuning pipelines; the network improves the models it hosts
- [ ] **Public Demo Endpoint** — Limited-use hosted Maestro instance with transparent logging, backed by Orchestra dashboard
- [ ] **Contributor Onboarding** — Expand `CONTRIBUTING.md` with architecture walkthrough, task tags, and first-contribution guides

---

## Guiding Principles

- **Preserve dissent** — the 66% supermajority ensures 33% dissent is always recorded and visible
- **Prevent stagnation** — continuous measurement (R2, MAGI, NCG) catches degradation before it compounds
- **Embrace disagreement as structure** — outlier detection is not suppression; it is classification
- **Always show your work** — every orchestration session produces a legible epistemic record
- **Weights are infrastructure** — treat model weights as persistent resources, not ephemeral allocations

---

## Community & Contributions

Contributors who align with the principles of transparency and structured dissent are welcome. See `CONTRIBUTING.md` for details, or follow project essays at [substack.com/@defqon1](https://substack.com/@defqon1).
