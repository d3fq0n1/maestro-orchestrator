# Agent Layer -- Maestro-Orchestrator

**Version:** v0.7.0
**Last Updated:** 2026-03-11
**Maintainer:** defcon

Maestro-Orchestrator integrates multiple LLM agents via a containerized backend. This document describes the agent architecture and the current council.

---

## Architecture

All agents extend a shared abstract base class (`maestro/agents/base.py`):

```python
class Agent(ABC):
    name: str
    model: str

    @staticmethod
    def build_system_prompt() -> str:
        """Return a system prompt grounding the model with the current date."""
        ...

    @abstractmethod
    async def fetch(self, prompt: str) -> str: ...
```

Every agent implements one method: receive a prompt, return a response string. The base class provides a shared `build_system_prompt()` that includes today's date and instructs the model to answer directly without knowledge-cutoff hedging. Each agent includes this system prompt in its API call using the provider-appropriate format. The analysis pipeline (dissent, NCG, R2, MAGI) then measures the actual behavior of each agent's output rather than assigning explicit roles.

---

## Current Agent Council

| Display Name         | Class      | Provider   | Model                                | Notes                                    |
|----------------------|------------|------------|--------------------------------------|------------------------------------------|
| GPT-4o               | `Sol`      | OpenAI     | `gpt-4o`                             | Primary reasoning engine                 |
| Claude Sonnet 4.6    | `Aria`     | Anthropic  | `claude-sonnet-4-6`                  | Contextual analysis                      |
| Gemini 2.5 Flash     | `Prism`    | Google     | `models/gemini-2.5-flash`            | Pattern-focused, low latency             |
| Llama 3.3 70B        | `TempAgent`| OpenRouter | `meta-llama/llama-3.3-70b-instruct`  | Diversity anchor (open-weight model)     |
| ShardNet             | `ShardAgent`| Distributed| `distributed`                       | Proof-of-storage distributed inference   |
| MockAgent            | `MockAgent`| (built-in) | n/a                                 | Deterministic responses for testing      |
| MockShardNode        | `MockShardNode`| (built-in)| n/a                              | Mock storage node for testing            |

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

Each agent receives the same prompt via `/api/ask` (or `/api/ask/stream` for SSE streaming), responds independently, and contributes to:

- Raw response log (displayed per-agent in the UI)
- Semantic quorum evaluation (66% similarity threshold)
- Dissent analysis (pairwise distances, outlier detection)
- NCG drift measurement (distance from headless baseline)

---

## Error Handling Contract

Every agent follows the same error handling contract so the orchestration pipeline is never aborted by a single agent failure:

| Exception | Handling |
|-----------|----------|
| Missing API key | Return `"[AgentName] API Key Missing"` immediately (no network call) |
| `httpx.TimeoutException` | Return `"[AgentName] Timeout"` with a descriptive log |
| `httpx.ConnectError` | Return `"[AgentName] Connection failed"` — DNS/network unreachable |
| `httpx.HTTPStatusError` | Return `"[AgentName] HTTP {status_code}"` — 4xx/5xx from provider |
| `KeyError` / `IndexError` | Return `"[AgentName] Malformed response"` — unexpected response structure |
| Any other exception | Return `"[AgentName] Failed"` — catch-all, always logged |

All agents also use `return_exceptions=True` in `asyncio.gather` (handled in `orchestrator.py`) as a second layer — even if an agent raises rather than returns, the pipeline continues.

---

## Adding a New Agent

1. Create a new file in `maestro/agents/` extending `Agent`
2. Implement `name`, `model`, and `async fetch(prompt) -> str`
3. Include the system prompt from `self.build_system_prompt()` in your API call using the provider-appropriate format (e.g. `system` message for chat completions APIs, `system` field for Anthropic, `systemInstruction` for Gemini)
4. Follow the error handling contract above — return error strings, never raise
5. Add to `maestro/agents/__init__.py`
6. Add to the `COUNCIL` list in `backend/orchestrator_foundry.py`

---

## ShardAgent (Distributed Inference)

The ShardAgent is unique among council agents — instead of calling a centralized API, it constructs an inference pipeline across a network of storage nodes, each holding specific weight shards. Compute follows storage.

The orchestrator sees it as just another agent: `fetch(prompt) -> str`. Internally:

1. Queries the `StorageNodeRegistry` for a pipeline covering all model layers
2. Filters nodes by reputation (minimum threshold, default 0.5)
3. Sends activation tensors through each pipeline node sequentially
4. On failure, attempts failover to a redundant node
5. Returns the decoded response as a string

Error handling follows the same contract as all other agents — typed error strings, never raises.

See [`storage-network.md`](./storage-network.md) for full documentation on the storage network architecture, proof system, and node server.

---

## Plugin-Provided Agents

The Mod Manager allows plugins to register agents dynamically via `PluginContext.register_agent()`. Plugin-registered agents participate in orchestration like any other agent. When the plugin is disabled, its agents are automatically unregistered.

See [`mod-manager.md`](./mod-manager.md) for the plugin protocol and how to write agent plugins.

---

## Future Agents

See [`roadmap.md`](./roadmap.md) for planned agent enhancements including multilingual agents, local model support (llamacpp, Ollama), and adversarial stress-testing agents.
