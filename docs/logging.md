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
  "timestamp": "2026-03-02T14:32:12+00:00",
  "prompt": "What are the risks of synthetic consensus?",
  "agent_responses": {
    "Sol": "The key risk lies in...",
    "Aria": "From an ethical standpoint...",
    "Prism": "Analytically, the pattern suggests..."
  },
  "agents_used": ["Sol", "Aria", "Prism"],
  "final_output": {
    "consensus": "Merged consensus view...",
    "majority_view": "...",
    "confidence": "High",
    "agreement_ratio": 0.75,
    "quorum_met": true,
    "dissent": { ... },
    "ncg_benchmark": { ... },
    "r2": { "grade": "strong", "confidence_score": 0.82, ... }
  },
  "ncg_enabled": true,
  "ncg_benchmark": { ... }
}
```

### Key Fields:
- `session_id`: Unique identifier (UUID) for the session
- `timestamp`: UTC ISO timestamp
- `prompt`: The user's input
- `agent_responses`: Each agent's full output keyed by agent name
- `agents_used`: List of agent names that participated
- `final_output`: Full analysis results (consensus, dissent, NCG, R2)
- `ncg_enabled`: Whether NCG headless benchmark was active
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
