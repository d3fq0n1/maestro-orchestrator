# Agent Layer -- Maestro-Orchestrator

**Version:** v0.3
**Last Updated:** 2026-03-02
**Maintainer:** defcon

Maestro-Orchestrator integrates multiple LLM agents via a containerized backend. This document describes the agent architecture and the current council.

---

## Architecture

All agents extend a shared abstract base class (`maestro/agents/base.py`):

```python
class Agent(ABC):
    name: str
    model: str

    @abstractmethod
    async def fetch(self, prompt: str) -> str: ...
```

Every agent implements one method: receive a prompt, return a response string. The analysis pipeline (dissent, NCG, R2, MAGI) then measures the actual behavior of each agent's output rather than assigning explicit roles.

---

## Current Agent Council

| ID          | Codename   | Backed By           | Description                                  |
|-------------|------------|---------------------|----------------------------------------------|
| `sol`       | Sol        | OpenAI (GPT-4)      | Language-first anchor and reasoning engine    |
| `aria`      | Aria       | Claude (Anthropic)  | Contextual analyst, ethical perspective       |
| `prism`     | Prism      | Gemini (Google)     | Analytical and pattern-focused perspective    |
| `tempagent` | TempAgent  | OpenRouter (varied) | Rotating agent for external model diversity   |
| `mock`      | MockAgent  | (built-in)          | Deterministic responses for testing           |

---

## How Agents Are Used

1. The **orchestrator foundry** (`backend/orchestrator_foundry.py`) instantiates the live council
2. All agents receive the same prompt concurrently via `asyncio.gather`
3. The **dissent analyzer** measures pairwise semantic distance between agent responses
4. The **aggregator** clusters agents by similarity to determine quorum
5. **R2** scores the session quality based on agent agreement patterns
6. **MAGI** tracks per-agent health across sessions (outlier rates, consistency)

Agents that consistently diverge from the council are flagged by R2 as persistent outliers. MAGI tracks whether this divergence is providing valuable signal (healthy dissent) or noise (model degradation).

---

## API Behavior

Each agent receives the same prompt via `/api/ask`, responds independently, and contributes to:

- Raw response log (displayed per-agent in the UI)
- Semantic quorum evaluation (66% similarity threshold)
- Dissent analysis (pairwise distances, outlier detection)
- NCG drift measurement (distance from headless baseline)

---

## Adding a New Agent

1. Create a new file in `maestro/agents/` extending `Agent`
2. Implement `name`, `model`, and `async fetch(prompt) -> str`
3. Handle missing API keys gracefully (return error string)
4. Add to `maestro/agents/__init__.py`
5. Add to the `COUNCIL` list in `backend/orchestrator_foundry.py`

---

## Future Agents

- Multilingual agents (French, Spanish, etc.)
- Image-captioning or visual interpretation models
- Local model support (e.g., llamacpp, Ollama)
- Simulated adversarial agents for stress testing
