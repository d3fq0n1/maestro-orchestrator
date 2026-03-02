# System Architecture - Maestro-Orchestrator

Maestro-Orchestrator is a modular, lightweight orchestration framework designed to coordinate synthetic agents (AI models) via quorum-based consensus. It separates backend logic, agent control, and UI rendering for flexibility and clarity.

---

## Core Components

### Orchestrator (Python / FastAPI)
- Receives user prompts via RESTful POST `/api/ask`
- Loads active agent configurations (Sol, Aria, Prism, etc.)
- Sends prompts to agents either via live API or placeholder logic
- Collects responses and executes quorum consensus logic
- Returns structured JSON with:
  - Raw agent responses
  - Consensus result (if quorum met)
  - Dissent logs

### Agent Layer
- Each agent is an abstraction wrapping an API model
- Agents respond based on assigned roles (Initiator, Responder, Arbiter)
- Role assignment is randomized per session unless overridden

### Quorum Logic Module
- Requires 66% agreement among agents to form consensus
- If consensus fails, dissent is included and preserved in output
- Role-based weighting and dissent propagation are planned future features

### NCG Module (Novel Content Generation)
- Runs a parallel headless generation track alongside conversational agents
- Headless generators produce content without system prompts, personality framing, or RLHF scaffolding
- Drift detector measures semantic distance between headless baseline and each agent's output
- Flags **silent collapse** when agents agree but have drifted from unconstrained baseline
- Two analysis tiers:
  - Semantic drift (embedding distance, available for all models)
  - Token-level drift (logprob analysis, available for models that expose logprobs)
- Output feeds into the aggregator as `ncg_benchmark` data

### Frontend UI (React + Vite)
- Calls backend API at `/api/ask`
- Displays:
  - Individual agent responses
  - Consensus or dissent state
  - Prompt/response history
- Live-reloads via Vite dev server
- Designed for deployment as static assets via Docker

### Docker
- Multi-stage Dockerfile: Stage 1 builds the Vite frontend, Stage 2 sets up Python with `backend/` and `maestro/` packages, then copies the built frontend as static assets served by FastAPI
- Single service via `docker-compose.yml` — both UI and API are served on port 8000
- `.env` support for API keys and runtime configuration
- Named volumes for persistent session and R2 data

---

## File Structure (Simplified)

```
/backend
  └── main.py              # FastAPI app
  └── orchestrator_foundry.py
  └── maestro_cli.py
/maestro                   # Core orchestration package
  └── orchestrator.py      # Async orchestration engine
  └── aggregator.py        # Response aggregation
  └── dissent.py           # Dissent analysis
  └── r2.py                # R2 Engine (scoring, ledger, signals)
  └── session.py           # Session persistence
  └── agents/              # Agent wrappers (base, sol, aria, prism, tempagent)
  └── ncg/                 # Novel Content Generation (generator, drift)
/frontend
  └── index.html
  └── src/
      └── maestroUI.tsx
      └── app.tsx
/docs
  └── agents.md
  └── architecture.md
  └── quorum_logic.md
  └── ncg.md
  └── r2-engine.md
/data
  └── sessions/            # Persisted session JSON logs
  └── r2/                  # R2 Engine ledger entries
Dockerfile
docker-compose.yml
.env.example
```

---

## Data Flow

```text
User → UI → /api/ask → Orchestrator
                           │
                           ├── Conversational Track: [Sol, Aria, Prism, TempAgent]
                           │         │
                           │         └── R2: Internal dissent detection
                           │
                           ├── NCG Track: [Headless Generator]
                           │         │
                           │         └── Drift Detector: Compare against conversational outputs
                           │
                           └── Aggregator (Quorum Logic + NCG Benchmark)
                                  │
                                  └── Response (Consensus + Dissent + Drift Report) → UI Render
```

---

## Planned Extensions

- Token-level NCG drift analysis via logprobs across all supported models
- NCG feedback loops that reshape prompts based on detected drift
- Cross-session NCG baselines tracking what "normal" output looks like over time
- MAGI loop — meta-agent governance reading R2 ledger to propose code-level improvements
- Local model agent support (e.g., llamacpp)
- Real-time debate log and public-facing consensus ledger

---

For orchestration logic details, see [`quorum_logic.md`](./quorum_logic.md)
