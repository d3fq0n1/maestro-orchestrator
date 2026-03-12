
# Maestro-Orchestrator

![Version](https://img.shields.io/badge/version-v7.1.6-blue)
![License](https://img.shields.io/badge/license-Custom%20Open%20Use-orange)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Docker](https://img.shields.io/badge/docker-supported-blue)

**Status:** Stable, containerized, live orchestration system

Maestro-Orchestrator is a lightweight, container-ready orchestration engine that unifies multiple AI agents under a structured system of model deliberation, synthetic consensus, and dissent. It enables real-time prompt routing through a rotating council of large language models — each agent reads its peers' responses and produces a refined reply before consensus analysis runs — then synthesizes their output with quorum logic.

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

- **FastAPI Backend** -- Live orchestration logic via `/api/ask`
- **Multi-Agent Council** -- Models: GPT-4o (OpenAI), Claude Sonnet 4.6 (Anthropic), Gemini 2.5 Flash (Google), Llama 3.3 70B (OpenRouter)
- **Model Deliberation** -- After initial response collection, each agent reads its peers' answers and produces a refined reply before any analysis runs. Default on, configurable rounds (1–5), non-fatal, full API exposure (`deliberation_enabled`, `deliberation_rounds`)
- **SSE Response Streaming** -- Progressive rendering via Server-Sent Events: agent responses appear as they arrive, deliberation rounds stream as they complete, analysis sections render as each pipeline stage finishes
- **Semantic Quorum Consensus** -- 66% similarity-cluster agreement with dissent preservation; operates on post-deliberation responses
- **NCG (Novel Content Generation)** -- Headless baseline track that detects silent model collapse and RLHF conformity drift; operates on post-deliberation responses
- **Dissent Analysis** -- Pairwise semantic distance between agents, outlier detection, and cross-session trend tracking
- **R2 Engine (Rapid Recursion)** -- Session scoring, consensus ledger indexing, and structured improvement signals for MAGI
- **MAGI (Meta-Agent Governance)** -- Cross-session pattern analysis with human-reviewable recommendations
- **Self-Improvement Pipeline** -- MAGI/R2-driven code optimization: introspection, proposal generation, MAGI_VIR sandboxed validation, and promote/reject lifecycle
- **MAGI_VIR (Virtual Instance Runtime)** -- Isolated sandbox for testing optimization proposals before promotion
- **Code Injection Engine** -- Opt-in live code injection: runtime parameter mutation, AST-based source patching, and config overlay writes with full rollback support
- **Injection Safety Guards** -- Category whitelist, bounds enforcement, rate limiting, post-injection smoke tests, and automatic rollback on degradation
- **Rollback System** -- Append-only ledger with snapshots for every injected change; single-call rollback per injection or per cycle
- **API Key Management** -- In-app key configuration, validation, and secure `.env` persistence
- **Session History** -- Persistent JSON logging of every orchestration session
- **Proof-of-Storage Network** -- Distributed inference across storage nodes with cryptographic challenge-response verification (PoRep, PoRes, PoI) and reputation-based routing
- **ShardAgent** -- Distributed inference agent that constructs pipelines across storage nodes; same `fetch(prompt) -> str` interface as centralized agents
- **Modular Plugin Architecture (Mod Manager)** -- Full plugin lifecycle (discover/validate/load/enable/disable/unload/reload) with 8 pipeline hook points, event bus, and controlled access to Maestro internals
- **Weight State Snapshots** -- Save, restore, diff, and delete system configuration snapshots (plugins, agents, thresholds, runtime config)
- **React/Vite Frontend** -- Full analysis dashboard (R2 grade, quorum bar, dissent, NCG drift, session browser)
- **TUI Dashboard** -- Textual-based terminal dashboard optimized for SoC devices (Raspberry Pi 5). Mainframe-style single-keypress navigation, first-run API key setup wizard, BTOP-style shard network monitor with animated indicators, LAN shard discovery panel. Supports direct import and HTTP client modes
- **Interactive Mode Selector** -- Arrow-key selector on startup and after Docker setup when no graphical browser is detected; choose TUI, CLI, or Web-UI without memorizing commands
- **Unified Startup Wrapper** -- Single Docker entrypoint with a GUI that lets you choose Web-UI, CLI, or TUI mode
- **Interactive CLI** -- Full orchestration pipeline in the terminal (REPL with agent responses, consensus, dissent, NCG, R2)
- **Automatic Background Updater** -- Background git polling with configurable interval (10s–3600s), optional auto-apply for iterative development workflows, SSE stream for real-time notifications, WebUI live banner and controls, TUI event-driven notifications
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

That's it. The setup script builds the container, waits for the health check to pass, and opens your browser to `http://localhost:8000`. On first launch the API Key settings panel opens automatically -- paste at least one provider key and you're ready to go.

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

> **CLI mode:** Set `MAESTRO_MODE=cli` in a `.env` file or pass it as an environment variable to use the interactive terminal REPL instead.
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

Agent implementations live in `maestro/agents/`. Each agent extends the shared base class in `maestro/agents/base.py` and implements an async `fetch(prompt) -> str` interface.

API keys are loaded from environment variables (`.env` file):
```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
```

---

## Consensus Model

Maestro uses **semantic similarity clustering** to determine agreement. Agents whose responses fall within a pairwise distance threshold are grouped into clusters. A **66% supermajority** of agents must agree for quorum to be met.

### NCG Diversity Benchmark

Alongside the conversational agent track, Maestro runs a **Novel Content Generation (NCG)** headless baseline. A model generates content for the same prompt without any system prompt, personality framing, or RLHF-aligned assistant scaffolding. The drift detector then measures how far each conversational agent's output has drifted from this unconstrained baseline.

This catches **silent collapse** -- when all agents agree, but their agreement reflects conformity pressure rather than genuine reasoning. R2 detects when agents disagree with each other. NCG detects when they all drift together.

See [`docs/ncg.md`](./docs/ncg.md) for the full technical specification.

---

## API Reference

### `GET /api/health`
Returns `{"status": "ok"}` when the API is ready. Used by Docker HEALTHCHECK and external monitors.

### `POST /api/ask`

**Request body:**
```json
{
  "prompt": "What are the ethical concerns of deploying autonomous drones?",
  "deliberation_enabled": true,
  "deliberation_rounds": 1
}
```

`deliberation_enabled` (default `true`) and `deliberation_rounds` (default `1`, max `5`) are optional. Omitting them keeps the default deliberation-on behaviour.

**Returns:**
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

### `POST /api/ask/stream`
Same request body as `/api/ask` (including `deliberation_enabled` and `deliberation_rounds`). Returns a **Server-Sent Events** stream with progressive results:

| Event | Description |
|-------|-------------|
| `stage` | Pipeline stage update (name + status message) |
| `agent_response` | Individual agent response as it arrives |
| `agents_done` | All agents complete |
| `deliberation_start` | Deliberation phase beginning |
| `deliberation_round` | One deliberation round complete (all per-agent deliberated responses) |
| `deliberation_done` | All deliberation rounds finished |
| `dissent` | Dissent analysis results |
| `ncg` | NCG benchmark results |
| `consensus` | Quorum/consensus results |
| `r2` | R2 scoring results |
| `done` | Complete response (same shape as `/api/ask`) |
| `error` | Error occurred |

The Web-UI uses this endpoint by default for progressive rendering.

### `GET /api/sessions`
List stored sessions (most recent first). Supports `limit` and `offset` query params.

### `GET /api/sessions/{session_id}`
Retrieve a full session record including all agent responses, consensus output, and NCG benchmark data.

### `GET /api/magi`
Run MAGI cross-session analysis. Returns confidence trends, agent health, collapse frequency, and structured recommendations.

### `GET /api/keys`
List configured API key status (masked values, never exposes raw keys).

### `PUT /api/keys/{provider}`
Set or update an API key for a provider.

### `DELETE /api/keys/{provider}`
Remove a provider's API key.

### `POST /api/keys/{provider}/validate`
Validate a single provider's API key against its service endpoint.

### `POST /api/keys/validate`
Validate all configured API keys against their respective endpoints.

### `GET /api/self-improve`
Self-improvement status and recent cycles.

### `POST /api/self-improve/cycle`
Trigger a full self-improvement cycle (MAGI → Introspect → Propose → Validate → Promote/Reject → Inject).

### `POST /api/self-improve/analyze`
Run analysis + introspection without VIR validation.

### `GET /api/self-improve/cycle/{id}`
Load a specific improvement cycle record.

### `GET /api/self-improve/introspect`
MAGI analysis with code introspection targets and optimization proposals.

### `GET /api/self-improve/nodes`
List available compute nodes for distributed MAGI_VIR validation.

### `POST /api/self-improve/nodes`
Register a new compute node.

### `POST /api/self-improve/inject/{cycle_id}`
Manually inject proposals from a previously validated cycle (human-in-the-loop path).

### `POST /api/self-improve/rollback/{rollback_id}`
Roll back a single injection.

### `POST /api/self-improve/rollback-cycle/{cycle_id}`
Roll back all active injections from a given improvement cycle.

### `GET /api/self-improve/injections`
List all active (non-rolled-back) injections.

### `GET /api/self-improve/rollbacks`
Full rollback history.

### Storage Network

### `POST /api/storage/nodes/register`
Register a storage node.

### `DELETE /api/storage/nodes/{node_id}`
Unregister a storage node.

### `GET /api/storage/nodes`
List all storage nodes with status and reputation.

### `GET /api/storage/nodes/{node_id}`
Detailed node info with reputation breakdown.

### `POST /api/storage/challenge/{node_id}`
Trigger a proof-of-storage challenge.

### `GET /api/storage/pipeline/{model_id}`
View the inference pipeline for a model.

### `GET /api/storage/redundancy/{model_id}`
Redundancy map (which nodes hold which layers).

### `GET /api/storage/reputation`
All node reputations.

### `GET /api/storage/network/topology`
Full network state: all nodes with reputation details, per-model layer coverage, gaps, mirror status, inference pipeline, redundancy map, and node contributions.

### `GET /api/storage/shards/models`
List all models with local shards.

### `GET /api/storage/shards/status/{model_id}`
Detailed shard status for a model (coverage, files, size, download state).

### `POST /api/storage/shards/download`
Start downloading shards for a model from HuggingFace Hub (runs in background).

### `GET /api/storage/shards/download-status/{model_id}`
Check download progress for a model.

### `DELETE /api/storage/shards/download-status/{model_id}`
Clear a completed or errored download status entry.

### `POST /api/storage/shards/verify/{model_id}`
Verify integrity of all local shards for a model against manifest checksums.

### `GET /api/storage/shards/disk-usage`
Total disk usage across all local shards.

### `DELETE /api/storage/shards/{model_id}`
Remove all local shards for a model.

### `POST /api/storage/shards/generate-config`
Generate a `node_shards.json` config from local shards (optionally filtered to a layer range).

### Plugin System

### `GET /api/plugins`
List all plugins with state.

### `POST /api/plugins/discover`
Scan for new plugins.

### `POST /api/plugins/{plugin_id}/enable`
Load and enable a plugin.

### `POST /api/plugins/{plugin_id}/disable`
Disable a plugin.

### `POST /api/plugins/{plugin_id}/reload`
Hot-reload a plugin.

### `GET /api/plugins/{plugin_id}`
Detailed plugin info with health check.

### `PUT /api/plugins/{plugin_id}/config`
Update plugin configuration.

### `GET /api/plugins/health`
Health check all enabled plugins.

### Weight State Snapshots

### `GET /api/snapshots`
List saved snapshots.

### `POST /api/snapshots`
Create a new snapshot.

### `POST /api/snapshots/{id}/restore`
Restore a snapshot.

### `GET /api/snapshots/{id}`
Load full snapshot data.

### `DELETE /api/snapshots/{id}`
Delete a snapshot.

### `GET /api/snapshots/diff/{a}/{b}`
Compare two snapshots.

### Auto-Updater

### `GET /api/update/check`
Check if updates are available from the configured remote.

### `POST /api/update/apply`
Pull latest changes from the remote.

### `GET /api/update/remote`
Get the configured update remote URL.

### `PUT /api/update/remote`
Set the update remote URL.

### `GET /api/update/auto`
Get auto-updater status (enabled, running, poll_interval, auto_apply, updates_applied, last_check_info).

### `PUT /api/update/auto`
Configure auto-updater settings on the fly (enabled, poll_interval, auto_apply). Persisted to `.env`.

### `GET /api/update/stream`
Server-Sent Events stream of real-time update notifications. Events: `status`, `check`, `available`, `applying`, `applied`, `up_to_date`, `error`. 15s keepalive.

### `POST /api/update/restart`
Restart the server process (sends SIGTERM to trigger Docker restart policy).

---

## Documentation

- [`architecture.md`](./docs/architecture.md) -- System architecture and data flow
- [`agents.md`](./docs/agents.md) -- Agent layer and adding new agents
- [`ncg.md`](./docs/ncg.md) -- Novel Content Generation and drift detection
- [`r2-engine.md`](./docs/r2-engine.md) -- Rapid Recursion & Reinforcement Engine
- [`magi.md`](./docs/magi.md) -- Meta-Agent Governance and Insight
- [`self-improvement-pipeline.md`](./docs/self-improvement-pipeline.md) -- Self-improvement pipeline (introspection, proposals, VIR validation, code injection)
- [`storage-network.md`](./docs/storage-network.md) -- Proof-of-storage distributed inference
- [`mod-manager.md`](./docs/mod-manager.md) -- Modular plugin architecture
- [`quorum_logic.md`](./docs/quorum_logic.md) -- Semantic quorum consensus
- [`deployment.md`](./docs/deployment.md) -- Setup & deployment guide
- [`troubleshooting.md`](./docs/troubleshooting.md) -- Troubleshooting
- [`ui-guide.md`](./docs/ui-guide.md) -- UI guide
- [`logging.md`](./docs/logging.md) -- Session logging and persistence
- [`vision.md`](./docs/vision.md) -- Project vision and design philosophy

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
