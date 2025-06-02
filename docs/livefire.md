# Livefire CLI Orchestrator

The `orchestration_livefire.py` script is the primary interface for running Maestro-Orchestrator in a real-time command-line session. It initializes agents, conducts multi-model rounds, records outputs, and applies quorum logic.

---

## 🚀 How It Works

### 1. Session Initialization

- Loads agents from the `agents/` directory.
- Reads environment variables from `.env` (e.g., API keys).
- Begins an interactive CLI prompt.

### 2. Prompt Loop

Each cycle includes:
- User input
- Agent response generation
- Consensus evaluation
- Logging of all activity to timestamped `.jsonl`

---

## 🧠 Quorum Logic

By default:
- 66% agreement is required for a consensus.
- Disagreement is recorded and visible.
- Sol may synthesize a fallback if disagreement persists.

---

## 📂 Output Format

Session logs are written to:

```bash
logs/session_YYYY-MM-DD_HHMM.jsonl
```

Each entry contains:
```json
{
  "role": "aria",
  "prompt": "What is the future of AI?",
  "response": "...",
  "timestamp": "2025-06-02T14:32:00Z"
}
```

---

## 🧪 Testing Mode

Developers can uncomment mock agent logic or use stubbed response mode for dry-runs without real API costs.

---

## 🛠️ Future Enhancements (v0.2 Roadmap)

- Agent-specific error handling
- Dynamic agent role assignment
- Replay mode using `.jsonl` logs
- Web-based orchestration panel (in development)

