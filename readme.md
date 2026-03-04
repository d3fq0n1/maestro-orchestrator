
# Maestro-Orchestrator

![Version](https://img.shields.io/badge/version-v0.4-blue)
![License](https://img.shields.io/badge/license-Custom%20Open%20Use-orange)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Docker](https://img.shields.io/badge/docker-supported-blue)

**Status:** Stable, containerized, live orchestration system

Maestro-Orchestrator is a lightweight, container-ready orchestration engine that unifies multiple AI agents under a structured system of synthetic consensus and dissent. It enables real-time prompt routing through a rotating council of large language models, each with distinct capabilities, and synthesizes their output with quorum logic.

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
- [Future Work](#future-work)

---

## Features

- **FastAPI Backend** -- Live orchestration logic via `/api/ask`
- **Multi-Agent Council** -- Models: Sol (GPT-4o), Aria (Claude Sonnet 4.6), Prism (Gemini 2.0 Flash), TempAgent (Llama 3.3 70B via OpenRouter)
- **Semantic Quorum Consensus** -- 66% similarity-cluster agreement with dissent preservation
- **NCG (Novel Content Generation)** -- Headless baseline track that detects silent model collapse and RLHF conformity drift
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
- **React/Vite Frontend** -- Full analysis dashboard (R2 grade, quorum bar, dissent, NCG drift, session browser)
- **Unified Startup Wrapper** -- Single Docker entrypoint with a GUI that lets you choose Web-UI or CLI mode
- **Interactive CLI** -- Full orchestration pipeline in the terminal (REPL with agent responses, consensus, dissent, NCG, R2)
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
make setup
```

That's it. The setup script builds the container, waits for the health check to pass, and opens your browser to `http://localhost:8000`. On first launch the API Key settings panel opens automatically -- paste at least one provider key and you're ready to go.

No `.env` file is required. Keys are saved through the Web-UI and persist across container restarts.

### Common commands

| Command | What it does |
|---------|-------------|
| `make setup` | First-time build + start + open browser |
| `make up` | Start the container (detached) |
| `make down` | Stop the container |
| `make logs` | Tail container logs |
| `make status` | Show container and health status |
| `make clean` | Stop and remove all data volumes |
| `make dev` | Start local dev servers (no Docker) |

> **CLI mode:** Set `MAESTRO_MODE=cli` in a `.env` file or pass it as an environment variable to use the interactive terminal REPL instead.

### Local development (no Docker)
```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env      # add your API keys
make dev                   # starts backend + frontend together
```

Or start services individually:

```bash
uvicorn backend.main:app --reload --port 8000   # backend
cd frontend && npm install && npm run dev        # frontend (separate terminal)
python -m maestro.cli                            # CLI mode (no web)
```

Backend API: `http://localhost:8000/api/ask`
Frontend dev server: `http://localhost:5173`

---

## Agent Council

| Agent         | Provider                          | Model                           | Description                                   |
|---------------|-----------------------------------|---------------------------------|-----------------------------------------------|
| **Sol**       | OpenAI                            | `gpt-4o`                        | Natural language programmer and scribe        |
| **Aria**      | Anthropic                         | `claude-sonnet-4-6`             | Reflective moral and abstract reasoning agent |
| **Prism**     | Google                            | `models/gemini-2.0-flash`       | Analytical and pattern-driven                 |
| **TempAgent** | OpenRouter                        | `meta-llama/llama-3.3-70b-instruct` | Rotating agent for external model testing |

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

### `POST /api/ask`
```json
{ "prompt": "What are the ethical concerns of deploying autonomous drones?" }
```

Returns:
```json
{
  "responses": { "Sol": "...", "Aria": "...", "Prism": "...", "TempAgent": "..." },
  "session_id": "b04e41f8-...",
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

### `GET /api/sessions`
List stored sessions (most recent first). Supports `limit` and `offset` query params.

### `GET /api/sessions/{session_id}`
Retrieve a full session record including all agent responses, consensus output, and NCG benchmark data.

### `GET /api/magi`
Run MAGI cross-session analysis. Returns confidence trends, agent health, collapse frequency, and structured recommendations.

### `GET /api/keys`
List configured API key status (masked values, never exposes raw keys).

### `POST /api/keys/{provider}`
Set or update an API key for a provider.

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

---

## Documentation

- [`architecture.md`](./docs/architecture.md) -- System architecture and data flow
- [`agents.md`](./docs/agents.md) -- Agent layer and adding new agents
- [`ncg.md`](./docs/ncg.md) -- Novel Content Generation and drift detection
- [`r2-engine.md`](./docs/r2-engine.md) -- Rapid Recursion & Reinforcement Engine
- [`magi.md`](./docs/magi.md) -- Meta-Agent Governance and Insight
- [`self-improvement-pipeline.md`](./docs/self-improvement-pipeline.md) -- Self-improvement pipeline (introspection, proposals, VIR validation, code injection)
- [`quorum_logic.md`](./docs/quorum_logic.md) -- Semantic quorum consensus
- [`quickstart.md`](./docs/quickstart.md) -- Quick start guide
- [`deployment.md`](./docs/deployment.md) -- Deployment guide
- [`setup_guide.md`](./docs/setup_guide.md) -- Setup guide
- [`troubleshooting.md`](./docs/troubleshooting.md) -- Troubleshooting
- [`ui-guide.md`](./docs/ui-guide.md) -- UI guide

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

## Future Work

- Token-level drift analysis via logprobs (OpenAI bridge available now, others pending)
- NCG feedback loops -- reshape prompts based on where drift is detected
- Cross-session NCG baselines that track what "normal" looks like over time
- Remote compute node MAGI_VIR validation (distributed testing across Maestro nodes)
- Web-UI integration for self-improvement cycle monitoring, proposal review, and injection controls
- Local model agent support (e.g., llamacpp)
- Launch public demo endpoint
- Extend to decentralized quorum network
