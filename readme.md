
# Maestro-Orchestrator

![Version](https://img.shields.io/badge/version-v0.2--webui-blue)
![License](https://img.shields.io/badge/license-Custom%20Open%20Use-orange)
![Python](https://img.shields.io/badge/python-3.8%2B-green)
![Docker](https://img.shields.io/badge/docker-supported-blue)

**Status:** Stable, containerized, live orchestration system

Maestro-Orchestrator is a lightweight, container-ready orchestration engine that unifies multiple AI agents under a structured system of synthetic consensus and dissent. It enables real-time prompt routing through a rotating council of large language models, each with distinct capabilities, and synthesizes their output with quorum logic.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Orchestrator Engine](#orchestrator-engine-latest-version)
- [Agent Council](#agent-council-v02-roles)
- [Consensus Model](#consensus-model)
- [API Reference](#api-example)
- [CLI Mode](#cli-mode)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)
- [Future Work](#future-work)

---

## Features

- **FastAPI Backend** — Live orchestration logic via `/api/ask`
- **Multi-Agent Council** — Models: Sol (OpenAI), Aria (Claude), Prism (Gemini), TempAgent (OpenRouter)
- **Quorum Consensus** — 66% agreement logic with dissent logging
- **React/Vite Frontend** — Simple, modular web UI (containerized)
- **Docker Support** — One-step spin-up of both frontend and backend
- **CLI Option** — Standalone session runner via `orchestration_livefire.py`

---

## Prerequisites

- Python 3.8+
- Node.js 18+ (for frontend)
- Docker & Docker Compose (for containerized setup)
- API keys for at least one provider (OpenAI, Anthropic, Google, or OpenRouter)

---

## Setup

### 1. Local (dev)
```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn api:app --reload
```

Frontend lives in the `frontend/` folder. To run manually:
```bash
cd frontend
npm install
npm run dev
```

### 2. Containerized (recommended)
```bash
docker-compose up --build
```

Frontend will be served at: [http://localhost:5173](http://localhost:5173)
Backend endpoint: [http://localhost:8000/api/ask](http://localhost:8000/api/ask)

---

## Orchestrator Engine (Latest Version)

The core logic for multi-agent prompt orchestration lives in [`scripts/orchestrator.py`](scripts/orchestrator.py). It supports the following agents and features:

### Supported Agents
- **Sol** – OpenAI (GPT-4 / GPT-4o) via OpenAI API
- **Aria** – Claude (Opus / Sonnet) via Anthropic API
- **Prism** – Gemini (Pro) via Google Generative AI
- **OpenRouter** – Abstracted multi-model backend (e.g., Mistral, GPT-4, Claude) via OpenRouter API

API keys are loaded from a `.env` file:

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
```

### Batch & Session Features
- **CSV Input File Support** – Run batch orchestrations from a CSV file with `Question` or `Prompt` columns
- **Quorum-Based Voting** – Agents answer each prompt and vote on which response is best
- **Session Persistence** – Every round is saved to `maestro_session.json` with prompt, responses, votes, and timestamp
- **Modular Agent Architecture** – Easy to add new LLM backends or swap existing models
- **Dissent Preservation** – All responses are logged, even if they don't win the vote

### Example Usage
```bash
python scripts/orchestrator.py --input-file path/to/questions.csv
```

### CSV Format
Your CSV must contain a column named `Question` or `Prompt`:

```csv
Category,Question
Philosophy,Can consciousness emerge from recursive symbol manipulation alone?
Science,Could spacetime arise from error-correcting codes?
```

---

## Agent Council (v0.2 Roles)

| Agent       | Model Source       | Description                                   |
|-------------|--------------------|-----------------------------------------------|
| **Sol**     | OpenAI (GPT-4)     | Natural language programmer and scribe        |
| **Aria**    | Claude (Anthropic) | Reflective moral and abstract reasoning agent |
| **Prism**   | Gemini (Google)    | Analytical and pattern-driven                 |
| **TempAgent** | OpenRouter       | Rotating agent for external model testing     |

Each session rotates agent roles randomly to reduce echo chamber effects.

---

## Consensus Model

Maestro requires a **66% quorum** for a response to be marked as agreed. Dissenting responses are preserved for transparency and future analysis.

---

## API Example

### `POST /api/ask`
```json
{
  "prompt": "What are the ethical concerns of deploying autonomous drones?"
}
```

Returns:
```json
{
  "responses": {
    "sol": "...",
    "aria": "...",
    "prism": "...",
    "tempagent": "..."
  },
  "consensus": {
    "agreement_ratio": 0.75,
    "agreed": true,
    "summary": "Consensus reached on ethical concerns."
  }
}
```

---

## CLI Mode

For local dev or testing without the UI:
```bash
python orchestration_livefire.py
```

---

## Documentation

- [`agents.md`](./docs/agents.md)
- [`roadmap.md`](./docs/roadmap.md)
- [`quorum_logic.md`](./docs/quorum_logic.md)

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

**defcon** — autodidact sysadmin, father, builder of consensus AI systems
Follow: [substack.com/@defqon1](https://substack.com/@defqon1)

---

## Future Work

- Add dissent analysis module
- Launch public demo endpoint
- Reinforcement training pipeline
- Extend to decentralized quorum network
