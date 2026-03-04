# Livefire Orchestration

Livefire orchestration is the primary mode of Maestro-Orchestrator -- live API calls to real LLM providers, processed through the full analysis pipeline.

---

## How It Works

### 1. Council Assembly

- `backend/orchestrator_foundry.py` builds the live agent council (Sol, Aria, Prism, TempAgent).
- It selects the best available headless generator for NCG based on configured API keys.
- Calls `maestro.orchestrator.run_orchestration_async()` with the live council.

### 2. Full Pipeline

Each orchestration request runs through:
1. **Conversational Track** -- All agents receive the prompt concurrently via `asyncio.gather`
2. **Dissent Analysis** -- Pairwise semantic distance, outlier detection, internal agreement score
3. **NCG Track** -- Headless baseline generation + drift detection
4. **Aggregation** -- Semantic quorum clustering (66% similarity threshold)
5. **R2 Scoring** -- Session grading, signal detection, ledger indexing
6. **Session Persistence** -- Full record saved to `data/sessions/`

---

## Running Livefire

### Via Web UI (recommended)
```bash
docker-compose up --build
# Open http://localhost:8000
```

### Via API
```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What are the ethical concerns of autonomous systems?"}'
```

---

## Testing Mode

Developers can use the `MockAgent` class in `maestro/agents/mock.py` for dry-runs without real API costs. The test suite in `tests/test_orchestration.py` uses mock agents exclusively.

```bash
python -m pytest tests/ -v
```

---

## Future Enhancements

- Replay mode using stored session logs
- Cross-session NCG baselines tracking drift over time
