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

### Frontend UI (React + Vite)
- Calls backend API at `/api/ask`
- Displays:
  - Individual agent responses
  - Consensus or dissent state
  - Prompt/response history
- Live-reloads via Vite dev server
- Designed for deployment as static assets via Docker

### Docker
- Multi-stage Dockerfile builds:
  - Python FastAPI backend (Uvicorn)
  - Node-based frontend (Vite build → static files)
- Containerized together via `docker-compose.yml`
- `.env` support for API keys and runtime configuration

---

## File Structure (Simplified)

```
/app
  └── main.py              # FastAPI app
  └── orchestrator_foundry.py
  └── agents/              # Agent wrappers and role logic
/frontend
  └── index.html
  └── src/
      └── components/
      └── views/
/docs
  └── README.md
  └── agents.md
  └── quorum_logic.md
  └── architecture.md
/docker
  └── Dockerfile
  └── docker-compose.yml
.env.example
```

---

## Data Flow

```text
User → UI → /api/ask → [Agents] → Quorum Logic → Response (Consensus + Dissent) → UI Render
```

---

## Planned Extensions

- CLI orchestration mode (for agent testing and scripting)
- Local model agent support (e.g., llamacpp)
- Real-time debate log and public-facing consensus ledger
- Session persistence and agent memory simulation

---

For orchestration logic details, see [`quorum_logic.md`](./quorum_logic.md)
