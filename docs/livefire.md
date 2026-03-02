# Livefire CLI Orchestrator

The `backend/orchestration_livefire.py` script is the primary interface for running Maestro-Orchestrator in a real-time command-line session. It initializes agents, conducts multi-model rounds, records outputs, and applies quorum logic.

---

## How It Works

### 1. Session Initialization

- Loads agents from `maestro/agents/` (Sol, Aria, Prism, TempAgent).
- Reads environment variables from `.env` (e.g., API keys).
- Begins an interactive CLI prompt.

### 2. Prompt Loop

Each cycle includes:
- User input
- Agent response generation
- Consensus evaluation
- Session persistence to `data/sessions/` as structured JSON

---

## Quorum Logic

By default:
- 66% agreement is required for a consensus.
- Disagreement is recorded and visible.
- Sol may synthesize a fallback if disagreement persists.

---

## Output Format

Sessions are persisted as individual JSON files in `data/sessions/`:

```
data/sessions/<session_id>.json
```

Each session record contains the prompt, all agent responses, consensus output, NCG benchmark data, and metadata. See [`logging.md`](./logging.md) for the full schema.

---

## Testing Mode

Developers can use the `MockAgent` class in `maestro/agents/mock.py` for dry-runs without real API costs.

---

## Future Enhancements (v0.3 Roadmap)

- Agent-specific error handling
- Replay mode using session logs
- NCG baseline generation alongside livefire sessions for drift analysis
- Session logs feeding into MAGI for cross-session NCG drift tracking
