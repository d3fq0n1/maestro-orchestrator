
# Maestro-Orchestrator

![Version](https://img.shields.io/badge/version-v7.2.4-blue)
![License](https://img.shields.io/badge/license-Custom%20Open%20Use-orange)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Docker](https://img.shields.io/badge/docker-supported-blue)

**Status:** Stable, containerized, live orchestration system

Maestro-Orchestrator is a lightweight, container-ready orchestration engine that unifies multiple AI agents under a structured system of model deliberation, synthetic consensus, and dissent. It routes prompts through a council of large language models — each agent reads its peers' responses and refines its reply before consensus analysis runs — then synthesizes output with quorum logic.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Agent Council](#agent-council)
- [Consensus Model](#consensus-model)
- [API Reference](#api-reference)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)
- [Roadmap](#roadmap)

---

## Features

- **FastAPI Backend** -- Live orchestration via `/api/ask`
- **Multi-Agent Council** -- GPT-4o, Claude Sonnet 4.6, Gemini 2.5 Flash, Llama 3.3 70B
- **Model Deliberation** -- Each agent reads peers' answers and refines its response before analysis. Configurable rounds (1–5), non-fatal, exposed via API (`deliberation_enabled`, `deliberation_rounds`)
- **SSE Response Streaming** -- Agent responses, deliberation rounds, and analysis stages stream progressively via Server-Sent Events
- **Semantic Quorum Consensus** -- 66% similarity-cluster supermajority with dissent preservation; runs on post-deliberation responses
- **NCG (Novel Content Generation)** -- Headless unconstrained baseline that detects silent model collapse and RLHF conformity drift
- **Dissent Analysis** -- Pairwise semantic distance, outlier detection, cross-session trend tracking
- **R2 Engine (Rapid Recursion)** -- Session scoring, consensus ledger indexing, improvement signals for MAGI
- **MAGI (Meta-Agent Governance)** -- Cross-session pattern analysis with human-reviewable recommendations
- **Self-Improvement Pipeline** -- MAGI/R2-driven: introspection, proposal generation, MAGI_VIR sandboxed validation, promote/reject lifecycle
- **MAGI_VIR (Virtual Instance Runtime)** -- Isolated sandbox for testing proposals before promotion
- **Code Injection Engine** -- Opt-in runtime parameter mutation, AST-based source patching, config overlay writes, full rollback
- **Injection Safety Guards** -- Category whitelist, bounds enforcement, rate limiting, smoke tests, auto-rollback on degradation
- **Rollback System** -- Append-only ledger; single-call rollback per injection or per cycle
- **API Key Management** -- In-app configuration, validation, secure `.env` persistence
- **Session History** -- Persistent JSON logging of every orchestration session
- **Proof-of-Storage Network** -- Distributed inference with cryptographic challenge-response (PoRep, PoRes, PoI) and reputation-based routing
- **ShardAgent** -- Distributed inference agent with the same `fetch(prompt) -> str` interface as centralized agents
- **Modular Plugin Architecture (Mod Manager)** -- Full lifecycle (discover/validate/load/enable/disable/reload) with 8 pipeline hook points and event bus
- **Weight State Snapshots** -- Save, restore, diff, and delete system configuration snapshots
- **React/Vite Frontend** -- Analysis dashboard: R2 grade, quorum bar, dissent, NCG drift, session browser
- **Cluster-Aware Instance Spawning** -- Press `+` in the TUI to spawn cluster members. First instance becomes orchestrator; subsequent instances auto-register as shard workers via shared Redis. Persistent instance registry tracks roles, names, ports, and container IPs across restarts
- **Live Cluster Dashboard** -- Always-visible TUI widget with health indicators, color-coded roles (orchestrator/shard), port/IP info. Auto-refreshes every 5s; press `C` to force-refresh
- **TUI Dashboard** -- Textual-based terminal UI optimized for SoC devices (Raspberry Pi 5). Keypress navigation, API key setup wizard, shard network monitor, LAN discovery panel, cluster dashboard, instance manager. Direct import and HTTP client modes
- **Interactive Mode Selector** -- Arrow-key selector on startup; choose TUI, CLI, or Web-UI without memorizing commands
- **Unified Startup Wrapper** -- Single Docker entrypoint; select Web-UI, CLI, or TUI at launch
- **Interactive CLI** -- Full orchestration pipeline in the terminal (agent responses, consensus, dissent, NCG, R2)
- **Automatic Background Updater** -- Git polling (10s–3600s), optional auto-apply, SSE stream, WebUI live banner, TUI notifications
- **Docker Support** -- Single-container deployment serving both UI and API

---

## Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend development only)
- Docker & Docker Compose (for containerized setup)
- API keys for at least one provider (OpenAI, Anthropic, Google, or OpenRouter)

---

## Setup

### Quick start (recommended)
```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python setup.py            # Windows, macOS, Linux — just needs Python + Docker
```

On macOS/Linux you can also use:
```bash
make setup
```

The setup script builds the container, waits for the health check to pass, and opens your browser to `http://localhost:8000`. On first launch the API Key settings panel opens automatically — paste at least one provider key and you're ready to go.

No `.env` file is required. Keys are saved through the Web-UI and persist across container restarts.

### Common commands

| Task | `make` (macOS/Linux) | Direct command (all platforms) |
|------|---------------------|-------------------------------|
| First-time setup | `make setup` | `python setup.py` |
| Start container | `make up` | `docker compose up -d --build` |
| Stop container | `make down` | `docker compose down` |
| Tail logs | `make logs` | `docker compose logs -f` |
| Container status | `make status` | `docker compose ps` |
| Remove all data | `make clean` | `docker compose down -v` |
| Local dev (no Docker) | `make dev` | `python setup.py --dev` |

> **CLI mode:** Set `MAESTRO_MODE=cli` in a `.env` file or as an environment variable.
>
> **TUI mode:** Set `MAESTRO_MODE=tui` for the Textual-based terminal dashboard (optimized for Raspberry Pi 5 and other SoC devices).

### Local development (no Docker)
```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python -m venv venv
source venv/bin/activate        # macOS/Linux
# .\venv\Scripts\activate       # Windows (PowerShell)
pip install -r requirements.txt
cp .env.example .env            # add your API keys
python setup.py --dev           # starts backend + frontend together
```

Or start services individually:

```bash
uvicorn backend.main:app --reload --port 8000   # backend
cd frontend && npm install && npm run dev        # frontend (separate terminal)
python -m maestro.cli                            # CLI mode (no web)
python -m maestro.tui                            # TUI dashboard (Raspi5 optimized)
python -m maestro.tui --mode http --url URL      # TUI connecting to remote server
```

Backend API: `http://localhost:8000/api/ask`
Frontend dev server: `http://localhost:5173`

---

## Agent Council

| Agent              | Provider   | Model                                | Notes                                    |
|--------------------|------------|--------------------------------------|------------------------------------------|
| **GPT-4o**         | OpenAI     | `gpt-4o`                             | Primary reasoning engine                 |
| **Claude Sonnet 4.6** | Anthropic  | `claude-sonnet-4-6`              | Contextual analysis                      |
| **Gemini 2.5 Flash** | Google   | `models/gemini-2.5-flash`            | Pattern-focused, low latency             |
| **Llama 3.3 70B** | OpenRouter | `meta-llama/llama-3.3-70b-instruct`  | Diversity anchor (open-weight model)     |
| **ShardNet**       | Distributed| `distributed`                         | Proof-of-storage distributed inference   |

Agent implementations live in `maestro/agents/`. Each agent extends `maestro/agents/base.py` and implements an async `fetch(prompt) -> str` interface.

API keys are loaded from environment variables (`.env` file):
```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
```

---

## Consensus Model

Maestro uses **semantic similarity clustering** to determine agreement. Agents whose responses fall within a pairwise distance threshold are grouped into clusters. A **66% supermajority** must agree for quorum to be met.

### NCG Diversity Benchmark

Alongside the conversational agent track, Maestro runs a **Novel Content Generation (NCG)** headless baseline. A model generates content without any system prompt, personality framing, or RLHF scaffolding. The drift detector measures how far each agent's output has drifted from this unconstrained baseline.

This catches **silent collapse** — when all agents agree, but their agreement reflects conformity pressure rather than genuine reasoning. R2 detects when agents disagree with each other. NCG detects when they all drift together.

See [`docs/ncg.md`](./docs/ncg.md) for the full technical specification.

---

## API Reference

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check; returns `{"status": "ok"}` |
| `POST` | `/api/ask` | Full pipeline; returns JSON (see below) |
| `POST` | `/api/ask/stream` | Same as `/api/ask` via SSE stream |
| `GET` | `/api/sessions` | List sessions (most recent first); `?limit=&offset=` |
| `GET` | `/api/sessions/{id}` | Full session record |
| `GET` | `/api/magi` | Cross-session MAGI analysis |

**`POST /api/ask` request:**
```json
{
  "prompt": "What are the ethical concerns of deploying autonomous drones?",
  "deliberation_enabled": true,
  "deliberation_rounds": 1
}
```
`deliberation_enabled` (default `true`) and `deliberation_rounds` (default `1`, max `5`) are optional.

**Response:**
```json
{
  "responses": { "GPT-4o": "...", "Claude Sonnet 4.6": "...", "Gemini 2.5 Flash": "...", "Llama 3.3 70B": "..." },
  "session_id": "b04e41f8-...",
  "deliberation": { "enabled": true, "rounds_requested": 1, "rounds_completed": 1, "agents_participated": [...], "skipped": false },
  "consensus": "Merged consensus view...",
  "confidence": "High",
  "agreement_ratio": 0.75,
  "quorum_met": true,
  "quorum_threshold": 0.66,
  "dissent": { "internal_agreement": 0.85, "dissent_level": "low", "outlier_agents": [], ... },
  "ncg_benchmark": { "ncg_model": "...", "mean_drift": 0.32, "silent_collapse": false, ... },
  "r2": { "grade": "strong", "confidence_score": 0.82, "flags": [], "signal_count": 0, ... }
}
```

**`POST /api/ask/stream` SSE events:**

| Event | Description |
|-------|-------------|
| `stage` | Pipeline stage update |
| `agent_response` | Individual agent response as it arrives |
| `agents_done` | All agents complete |
| `deliberation_start` | Deliberation phase beginning |
| `deliberation_round` | One round complete (all per-agent deliberated responses) |
| `deliberation_done` | All rounds finished |
| `dissent` | Dissent analysis results |
| `ncg` | NCG benchmark results |
| `consensus` | Quorum/consensus results |
| `r2` | R2 scoring results |
| `done` | Complete response (same shape as `/api/ask`) |
| `error` | Error occurred |

### API Keys

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/keys` | List keys (masked) |
| `PUT` | `/api/keys/{provider}` | Set or update a key |
| `DELETE` | `/api/keys/{provider}` | Remove a key |
| `POST` | `/api/keys/{provider}/validate` | Validate one key |
| `POST` | `/api/keys/validate` | Validate all keys |

### Self-Improvement

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/self-improve` | Status and recent cycles |
| `POST` | `/api/self-improve/cycle` | Full cycle (MAGI → Propose → Validate → Inject) |
| `POST` | `/api/self-improve/analyze` | Analysis + introspection without VIR validation |
| `GET` | `/api/self-improve/cycle/{id}` | Load cycle record |
| `GET` | `/api/self-improve/introspect` | MAGI analysis with optimization proposals |
| `GET` | `/api/self-improve/nodes` | List compute nodes |
| `POST` | `/api/self-improve/nodes` | Register compute node |
| `POST` | `/api/self-improve/inject/{cycle_id}` | Manual inject (human-in-the-loop) |
| `POST` | `/api/self-improve/rollback/{rollback_id}` | Roll back single injection |
| `POST` | `/api/self-improve/rollback-cycle/{cycle_id}` | Roll back all injections in a cycle |
| `GET` | `/api/self-improve/injections` | Active injections |
| `GET` | `/api/self-improve/rollbacks` | Rollback history |

### Storage Network

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/storage/nodes/register` | Register a node |
| `DELETE` | `/api/storage/nodes/{node_id}` | Unregister a node |
| `GET` | `/api/storage/nodes` | List nodes with status and reputation |
| `GET` | `/api/storage/nodes/{node_id}` | Node detail with reputation breakdown |
| `POST` | `/api/storage/challenge/{node_id}` | Trigger proof-of-storage challenge |
| `GET` | `/api/storage/pipeline/{model_id}` | Inference pipeline for a model |
| `GET` | `/api/storage/redundancy/{model_id}` | Layer redundancy map |
| `GET` | `/api/storage/reputation` | All node reputations |
| `GET` | `/api/storage/network/topology` | Full network state (nodes, coverage, gaps, pipelines) |
| `GET` | `/api/storage/shards/models` | List models with local shards |
| `GET` | `/api/storage/shards/status/{model_id}` | Shard status (coverage, files, size) |
| `POST` | `/api/storage/shards/download` | Download shards from HuggingFace (background) |
| `GET` | `/api/storage/shards/download-status/{model_id}` | Download progress |
| `DELETE` | `/api/storage/shards/download-status/{model_id}` | Clear download status entry |
| `POST` | `/api/storage/shards/verify/{model_id}` | Verify shard integrity against checksums |
| `GET` | `/api/storage/shards/disk-usage` | Total local shard disk usage |
| `DELETE` | `/api/storage/shards/{model_id}` | Remove local shards |
| `POST` | `/api/storage/shards/generate-config` | Generate `node_shards.json` from local shards |

### Plugins

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/plugins` | List plugins with state |
| `POST` | `/api/plugins/discover` | Scan for new plugins |
| `POST` | `/api/plugins/{id}/enable` | Load and enable |
| `POST` | `/api/plugins/{id}/disable` | Disable |
| `POST` | `/api/plugins/{id}/reload` | Hot-reload |
| `GET` | `/api/plugins/{id}` | Detail with health check |
| `PUT` | `/api/plugins/{id}/config` | Update plugin config |
| `GET` | `/api/plugins/health` | Health check all enabled plugins |

### Snapshots

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/snapshots` | List snapshots |
| `POST` | `/api/snapshots` | Create snapshot |
| `POST` | `/api/snapshots/{id}/restore` | Restore snapshot |
| `GET` | `/api/snapshots/{id}` | Load snapshot data |
| `DELETE` | `/api/snapshots/{id}` | Delete snapshot |
| `GET` | `/api/snapshots/diff/{a}/{b}` | Compare two snapshots |

### Auto-Updater

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/update/check` | Check for available updates |
| `POST` | `/api/update/apply` | Pull latest changes |
| `GET` | `/api/update/remote` | Get configured remote URL |
| `PUT` | `/api/update/remote` | Set remote URL |
| `GET` | `/api/update/auto` | Auto-updater status (enabled, interval, auto_apply, last check) |
| `PUT` | `/api/update/auto` | Configure auto-updater; persisted to `.env` |
| `GET` | `/api/update/stream` | SSE stream of update events (15s keepalive) |
| `POST` | `/api/update/restart` | Restart server (SIGTERM) |

---

## Documentation

- [`PROJECT_EXPLAINED.md`](./PROJECT_EXPLAINED.md) -- Plain-language project overview for non-technical readers
- [`CLUSTERING.md`](./CLUSTERING.md) -- Multi-node cluster setup and architecture
- [`architecture.md`](./docs/architecture.md) -- System architecture and data flow
- [`agents.md`](./docs/agents.md) -- Agent layer and adding new agents
- [`deliberation.md`](./docs/deliberation.md) -- Deliberation engine
- [`ncg.md`](./docs/ncg.md) -- Novel Content Generation and drift detection
- [`r2-engine.md`](./docs/r2-engine.md) -- Rapid Recursion & Reinforcement Engine
- [`magi.md`](./docs/magi.md) -- Meta-Agent Governance and Insight
- [`self-improvement-pipeline.md`](./docs/self-improvement-pipeline.md) -- Self-improvement pipeline
- [`storage-network.md`](./docs/storage-network.md) -- Proof-of-storage distributed inference
- [`mod-manager.md`](./docs/mod-manager.md) -- Modular plugin architecture
- [`quorum_logic.md`](./docs/quorum_logic.md) -- Semantic quorum consensus
- [`deployment.md`](./docs/deployment.md) -- Setup & deployment guide
- [`troubleshooting.md`](./docs/troubleshooting.md) -- Troubleshooting
- [`ui-guide.md`](./docs/ui-guide.md) -- UI guide
- [`logging.md`](./docs/logging.md) -- Session logging and persistence
- [`vision.md`](./docs/vision.md) -- Project vision and design philosophy
- [`maestro-whitepaper.md`](./docs/maestro-whitepaper.md) -- Technical whitepaper

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

---

## License

This project does not use the MIT license. It operates under a custom open-use license:

- [`LICENSE.md`](./LICENSE.md)
- [`commercial_license.md`](./commercial_license.md)

Use is permitted with attribution. Commercial use requires an agreement.

---

## Author

**defcon** -- autodidact sysadmin, father, builder of consensus AI systems
Follow: [substack.com/@defqon1](https://substack.com/@defqon1)

---

## Roadmap

See [`docs/roadmap.md`](./docs/roadmap.md) for planned milestones and future direction.
