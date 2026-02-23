# Maestro-Orchestrator

> *Pluralising synthetic intelligence through structured consensus and preserved dissent.*

Maestro-Orchestrator is a multi-agent AI orchestration framework that routes prompts through multiple large language models simultaneously, evaluates their responses using a 66% quorum threshold, and returns a structured result that includes both consensus and dissent. No single model acts as the oracle.

**Current version:** v0.2-webui

---

## How It Works

1. A prompt is submitted via the web UI or API
2. The orchestrator dispatches the prompt to all configured agents in parallel
3. Agent responses are evaluated for semantic agreement
4. If 66% or more of agents align, consensus is declared — dissenting views are preserved and displayed
5. The full response object (including all agent outputs, agreement ratio, and consensus summary) is returned

```
User → UI → /api/ask → [Sol, Aria, Prism, TempAgent] → Quorum Logic → Response
```

---

## Agent Council

| Codename   | Model Backend       | Role                                           |
|------------|---------------------|------------------------------------------------|
| Sol        | OpenAI (GPT-4)      | Language-first anchor and orchestrator         |
| Aria       | Anthropic (Claude)  | Moral and philosophical lens                   |
| Prism      | Google (Gemini)     | Analytical and pattern-focused perspective     |
| TempAgent  | OpenRouter (varied) | Rotating slot for external model injection     |

Roles are randomized per session to prevent static alignment and reduce echo chamber effects.

---

## Quorum Logic

Maestro uses a **66% supermajority** threshold to form consensus:

- 3 out of 4 agents agreeing → consensus reached
- Dissenting responses are never discarded — they are logged and surfaced in the UI
- Agreement is evaluated using semantic similarity, intent convergence, and tone normalization

See [`docs/quorum_logic.md`](docs/quorum_logic.md) for full details.

---

## Getting Started

### Prerequisites

- Python 3.8+
- Node.js + npm (for the frontend)
- Docker + Docker Compose (optional, recommended)
- API keys for OpenAI, Anthropic, and/or Google

### Option 1: Docker (recommended)

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
cp .env.example .env
# Edit .env and add your API keys
docker-compose up --build
```

The system will be available at `http://localhost:8000`.

### Option 2: Manual Setup

**Backend:**

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`.

---

## Environment Variables

Copy `.env.example` to `.env` and populate:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
```

---

## API

### `POST /api/ask`

Submit a prompt to the full agent council.

**Request:**
```json
{
  "prompt": "What are the societal risks of autonomous policing?"
}
```

**Response:**
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

## Project Structure

```
├── backend/
│   ├── main.py                        # FastAPI application
│   ├── orchestrator_foundry.py        # Orchestration core
│   ├── orchestration_livefire.py      # CLI session runner
│   └── requirements.txt
├── agents/
│   ├── sol.py                         # OpenAI agent
│   ├── aria.py                        # Anthropic agent
│   ├── prism.py                       # Gemini agent
│   └── openrouter_temporaryagent.py   # OpenRouter agent
├── frontend/
│   ├── index.html
│   └── src/
├── docs/                              # Full documentation
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

---

## Documentation

| Doc | Description |
|-----|-------------|
| [`docs/architecture.md`](docs/architecture.md) | System design and data flow |
| [`docs/agents.md`](docs/agents.md) | Agent roles and configuration |
| [`docs/quorum_logic.md`](docs/quorum_logic.md) | Consensus mechanics |
| [`docs/deployment.md`](docs/deployment.md) | Deployment options (local, Docker, cloud) |
| [`docs/roadmap.md`](docs/roadmap.md) | Current and planned milestones |
| [`docs/maestro-whitepaper.md`](docs/maestro-whitepaper.md) | Theoretical foundation |

---

## Roadmap Highlights

**v0.3 (in progress):**
- Dissent analysis and visualization
- Session history logging and replay
- Drift detection via meta-agent layer
- UI enhancements (loading states, error handling)

**Planned:**
- Decentralized consensus layer
- Multilingual agent support
- Public demo endpoint with transparent logging

See [`docs/roadmap.md`](docs/roadmap.md) for the full roadmap.

---

## Contributing

Contributions are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup instructions, coding standards, and how to submit changes.

Core principles:
- Preserve dissent
- Prevent stagnation
- Embrace disagreement as structure
- Always show your work

---

## License

This project uses a custom license. See [`LICENSE.md`](LICENSE.md) for open-use terms and [`commercial_license.md`](commercial_license.md) for commercial use terms.

---

Built by [defcon](https://substack.com/@defqon1) · [GitHub](https://github.com/d3fq0n1/maestro-orchestrator)
