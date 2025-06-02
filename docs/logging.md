# Logging & Session Replay

Maestro-Orchestrator logs every interaction between the user and agents in structured `.jsonl` (JSON Lines) format. This supports auditing, analysis, replay, and future integration with meta-agents like MAGI.

---

## 🗃️ Log File Structure

Each session generates a timestamped log file under the `logs/` directory:

```
logs/session_2025-06-02_1432.jsonl
```

---

## 📄 Log Entry Format

Each line in the file is a JSON object:

```json
{
  "role": "sol",
  "prompt": "What are the risks of synthetic consensus?",
  "response": "The key risk lies in...",
  "timestamp": "2025-06-02T14:32:12Z"
}
```

### Fields:
- `role`: The agent responding (e.g., `sol`, `aria`)
- `prompt`: The user's input that initiated this round
- `response`: The agent's full output
- `timestamp`: UTC timestamp for the entry

---

## 🔁 Replay Possibility

Planned future functionality:
- Reconstruct entire sessions from logs
- Re-analyze outputs under new logic rules
- Feed logs to MAGI or other analysis engines

---

## 🔐 Log Safety

Logs can contain sensitive API-driven responses. Avoid sharing `.jsonl` files publicly without sanitization.

Use `.gitignore` to exclude `logs/` from public repos by default.

