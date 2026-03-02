# Logging & Session Persistence

Maestro-Orchestrator persists every orchestration session as structured JSON. This supports auditing, analysis, replay, and future integration with meta-agents like MAGI.

---

## Session Storage

Sessions are stored as individual JSON files in `data/sessions/`:

```
data/sessions/<session_id>.json
```

Each file is a complete `SessionRecord` containing the prompt, all agent responses, consensus output, NCG benchmark data, and metadata.

---

## Session Record Structure

```json
{
  "session_id": "b04e41f8-...",
  "timestamp": "2025-06-02T14:32:12+00:00",
  "prompt": "What are the risks of synthetic consensus?",
  "agent_responses": {
    "sol": "The key risk lies in...",
    "aria": "From an ethical standpoint...",
    "prism": "Analytically, the pattern suggests..."
  },
  "consensus": {
    "agreement_ratio": 0.75,
    "agreed": true,
    "summary": "Consensus reached."
  },
  "ncg_benchmark": { ... },
  "metadata": { ... }
}
```

### Key Fields:
- `session_id`: Unique identifier for the session
- `timestamp`: UTC timestamp for the session
- `prompt`: The user's input
- `agent_responses`: Each agent's full output keyed by agent name
- `consensus`: Quorum result with agreement ratio and summary
- `ncg_benchmark`: NCG drift data (when enabled)

---

## R2 Engine Ledger

R2 scored sessions are additionally indexed to `data/r2/` as ledger entries. Each entry captures the session score, improvement signals, and condensed dissent summary.

---

## Session History API

- `GET /api/sessions` — List stored sessions (most recent first)
- `GET /api/sessions/{session_id}` — Retrieve a full session record

---

## Replay Possibility

Planned future functionality:
- Reconstruct entire sessions from stored records
- Re-analyze outputs under new logic rules
- Feed sessions to MAGI or other analysis engines

---

## Log Safety

Session files can contain sensitive API-driven responses. Avoid sharing session data publicly without sanitization.

Use `.gitignore` to exclude `data/` from public repos by default.
