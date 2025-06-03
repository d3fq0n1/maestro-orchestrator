# Architecture: Maestro-Orchestrator

## System Overview

Maestro-Orchestrator is a modular, multi-agent orchestration system. It coordinates independent large language models (LLMs) to generate structured responses and reach consensus using quorum logic. The system emphasizes transparency, dissent preservation, and extensibility.

---

## Core Principles

- **Agent Independence**  
  Each agent responds to a prompt independently, without access to others’ outputs.

- **Quorum Consensus**  
  The orchestrator uses a configurable threshold (default: 2/3) to identify agreement among agents.

- **Structured Dissent**  
  Non-matching responses are preserved and returned to the user alongside the consensus.

---

## Backend Components

### `main.py`
- FastAPI application
- Exposes `POST /api/ask`
- Loads environment variables from `.env`
- Sends prompt to orchestrator and returns structured results

### `orchestrator_foundry.py`
- Core orchestration logic
- Initializes agents (`Sol`, `Aria`, `Prism`, `TempAgent`)
- Sends prompts asynchronously
- Gathers responses and determines quorum + dissent

### `orchestration_livefire.py`
- CLI-compatible orchestrator
- Enables local sessions and session history
- Uses same quorum and agent logic as the web backend

---

## Agent Model

Each agent has:
- A unique name and API backend (OpenAI, Claude, Gemini, OpenRouter)
- An assigned emoji for frontend display
- A shared schema for prompt input and structured output

Agents operate in parallel and are blind to each other’s outputs.

---

## Frontend Components

### `ui/index.html`
- Entry point for Vite-based React app

### `ui/src/maestroUI.tsx`
- React interface using TailwindCSS
- Sends prompt to `/api/ask`
- Displays each agent's response with emoji
- Renders quorum consensus and structured dissent

---

## Data Flow

```
[User Input]
      ↓
 /api/ask (FastAPI)
      ↓
[Orchestrator Foundry]
      ↓
[Agents → Responses]
      ↓
[Quorum + Dissent Calculation]
      ↓
[Frontend Rendering]
```

---

## Quorum Logic (Simplified)

```python
if matching_responses >= quorum_threshold:
    return "Consensus"
else:
    return "No consensus" and preserve all responses
```

---

## Configuration

- Environment managed via `.env` (see `.env.template`)
- CORS fully enabled for local and container development
- Docker builds support full-stack orchestration

---

## Extensibility (Planned for v0.3)

- **R2 Engine**: Score, reinforce, and learn from consensus patterns
- **Snapshot Ledger**: Immutable logging of decisions and outcomes
- **MAGI Loop**: Meta-agent layer for audit, drift detection, and ethical flags
- **Unified Session Layer**: CLI and UI share common history and analysis
