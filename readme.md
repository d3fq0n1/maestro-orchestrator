
# Maestro-Orchestrator

![Version](https://img.shields.io/badge/version-v0.3-blue)
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
- **Multi-Agent Council** -- Models: Sol (OpenAI), Aria (Claude), Prism (Gemini), TempAgent (OpenRouter)
- **Semantic Quorum Consensus** -- 66% similarity-cluster agreement with dissent preservation
- **NCG (Novel Content Generation)** -- Headless baseline track that detects silent model collapse and RLHF conformity drift
- **Dissent Analysis** -- Pairwise semantic distance between agents, outlier detection, and cross-session trend tracking
- **R2 Engine (Rapid Recursion)** -- Session scoring, consensus ledger indexing, and structured improvement signals for MAGI
- **MAGI (Meta-Agent Governance)** -- Cross-session pattern analysis with human-reviewable recommendations
- **API Key Management** -- In-app key configuration, validation, and secure `.env` persistence
- **Session History** -- Persistent JSON logging of every orchestration session
- **React/Vite Frontend** -- Full analysis dashboard (R2 grade, quorum bar, dissent, NCG drift, session browser)
- **Docker Support** -- Single-container deployment serving both UI and API

---

## Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend development only)
- Docker & Docker Compose (for containerized setup)
- API keys for at least one provider (OpenAI, Anthropic, Google, or OpenRouter)

---

## Setup

### 1. Docker (recommended)
```bash
cp .env.example .env   # add your API keys
docker-compose up --build
```

Application (UI + API): [http://localhost:8000](http://localhost:8000)

### 2. Local development
```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env      # add your API keys
uvicorn backend.main:app --reload --port 8000
```

Frontend (separate terminal):
```bash
cd frontend
npm install
npm run dev
```

Backend API: `http://localhost:8000/api/ask`
Frontend dev server: `http://localhost:5173`

---

## Agent Council

| Agent         | Provider           | Description                                   |
|---------------|--------------------|-----------------------------------------------|
| **Sol**       | OpenAI (GPT-4)     | Natural language programmer and scribe        |
| **Aria**      | Claude (Anthropic) | Reflective moral and abstract reasoning agent |
| **Prism**     | Gemini (Google)    | Analytical and pattern-driven                 |
| **TempAgent** | OpenRouter         | Rotating agent for external model testing     |

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

In parallel with the conversational agent track, Maestro runs a **Novel Content Generation (NCG)** headless baseline. A model generates content for the same prompt without any system prompt, personality framing, or RLHF-aligned assistant scaffolding. The drift detector then measures how far each conversational agent's output has drifted from this unconstrained baseline.

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

---

## Documentation

- [`architecture.md`](./docs/architecture.md) -- System architecture and data flow
- [`agents.md`](./docs/agents.md) -- Agent layer and adding new agents
- [`ncg.md`](./docs/ncg.md) -- Novel Content Generation and drift detection
- [`r2-engine.md`](./docs/r2-engine.md) -- Rapid Recursion & Reinforcement Engine
- [`magi.md`](./docs/magi.md) -- Meta-Agent Governance and Insight
- [`quorum_logic.md`](./docs/quorum_logic.md) -- Semantic quorum consensus
- [`deployment.md`](./docs/deployment.md) -- Deployment guide
- [`quickstart.md`](./docs/quickstart.md) -- Quick start guide

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
- MAGI automation layer (opt-in auto-apply for low-risk recommendations)
- Local model agent support (e.g., llamacpp)
- Launch public demo endpoint
- Extend to decentralized quorum network
