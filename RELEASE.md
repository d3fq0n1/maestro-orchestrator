# Maestro-Orchestrator v0.7.1

**Multi-Agent AI Orchestration with Synthetic Consensus, Deliberation, and Dissent**

---

## What's New in v0.7.1

### Model Deliberation

Agents no longer respond in isolation. After all agents return their initial answers, the **Deliberation Engine** feeds each agent's response back into the pool — every agent reads what its peers said and produces a refined reply before any analysis runs.

- **Default on** — deliberation runs automatically with 1 round unless you opt out via `deliberation_enabled: false` in the API request.
- **Configurable rounds** — set `deliberation_rounds` (1–5) to run multiple passes of cross-agent debate. Each round costs one additional API call per agent.
- **Non-fatal** — if any agent errors during deliberation, it keeps its previous response and the pipeline continues.
- **Full history** — the API response includes a `deliberation` summary (rounds completed, participating agents). The streaming endpoint emits per-round responses as they arrive.
- **Downstream analysis operates on deliberated positions** — dissent analysis, NCG drift detection, and quorum aggregation all run on the agents' considered, post-deliberation outputs.

**API changes (both `/api/ask` and `/api/ask/stream`):**

```json
{
  "prompt": "Your question here",
  "deliberation_enabled": true,
  "deliberation_rounds": 1
}
```

Both new fields are optional. The default behaviour (`deliberation_enabled: true, deliberation_rounds: 1`) requires no changes to existing integrations.

**New SSE events (streaming endpoint):**

| Event | Description |
|-------|-------------|
| `deliberation_start` | Deliberation beginning — round count and agent list |
| `deliberation_round` | One round complete — round number and all per-agent deliberated responses |
| `deliberation_done` | All rounds finished — summary with participation and any skip reason |

---

## Highlights from v0.7.0

### TUI Dashboard

- **Full Textual-based terminal dashboard** optimized for SoC devices (Raspberry Pi 5). Agent panel with live status indicators, consensus metrics, response viewer with syntax highlighting, shard network monitor, modal screens (F1 help, F2 node detail, F3 API key status).
- **Dual backend modes** — Direct import (in-process, lowest latency) and HTTP client (connects to running server via SSE, supports multi-device clusters).
- **TUI mode in startup wrapper** — `entrypoint.py` now offers TUI as a third option alongside Web-UI and CLI. Selectable via dialog menu or `MAESTRO_MODE=tui`.

### Setup Improvements

- **Graceful Docker fallback** — `setup.py` now suggests `--dev` mode when Docker is not installed, with an interactive prompt to switch automatically. No more hard failure on systems without Docker.

---

## Highlights from v0.6.3

### Storage Network Dashboard

Full GUI for visualizing the distributed storage network, accessible via the **Storage** button in the Web-UI header:

- **Network tab** — Per-model mirror status, layer coverage bars, inference pipeline visualization, redundancy map, gap detection
- **Shard Map tab** — Visual grid of nodes × layer blocks with color-coded coverage and redundancy indicators
- **Network topology API** (`GET /api/storage/network/topology`) — Full network state in a single call

### Shard Management API

- Download model shards from HuggingFace Hub, track progress, verify integrity, report disk usage, and generate `node_shards.json` configs via `/api/storage/shards/*`

---

## Highlights from v0.6.2

- **Shard utilities** — Header parsing, layer index extraction, byte-range SHA-256 proofs, and shard descriptor generation for safetensors weight files
- **Shard Manager** — Download, index, verify, and manage local weight shards; integrates with HuggingFace Hub
- **Node CLI** — `python -m maestro.node_cli` for storage node operators (setup, start, status, verify, shards)
- **Real byte-range proof challenges** — Node server hashes actual file bytes when shards are on disk
- **Node auto-registration** — Node server registers with the orchestrator and sends heartbeats automatically

---

## Highlights from v0.6.1

- **Update progress bar** — Visual feedback while updates are applied
- **Restart server button** — One-click restart after a successful update
- **Default remote URL** — Auto-updater now defaults to the canonical GitHub repo
- **Bug fixes** — API keys preserved across updates, duplicate error prefixes removed, `Errno 17` on update resolved

---

## Highlights from v0.6

### Proof-of-Storage Distributed Inference

Full storage network layer enabling distributed model inference across storage nodes:

- **Storage Node Registry** — Shard-aware topology, pipeline construction, redundancy mapping, heartbeat tracking, reputation integration
- **Storage Proof Engine** — Three proof types: Proof-of-Replication (byte-range hash), Proof-of-Residency (latency probe), Proof-of-Inference (canary inference)
- **Reputation Scoring** — `0.7 × challenge_pass_rate + 0.3 × R2_contribution`. Automatic eviction below threshold.
- **ShardAgent** — Distributed inference agent with the same `fetch(prompt) -> str` interface as centralized agents
- **Node Server** — Standalone FastAPI server for storage nodes. Endpoints: `/infer`, `/challenge`, `/health`, `/heartbeat`, `/shards`

### Modular Plugin Architecture (Mod Manager)

Complete plugin system for extending Maestro without modifying core code:

- **Plugin Protocol** — `MaestroPlugin` ABC with `activate()`, `deactivate()`, `health_check()`, and `on_config_change()`
- **Full Lifecycle** — Discover, validate, load, enable, disable, unload, hot-reload
- **8 Pipeline Hooks** — `pre_orchestration`, `post_agent_response`, `pre_aggregation`, `post_aggregation`, `pre_r2_scoring`, `post_r2_scoring`, `pre_session_save`, `post_session_save`
- **Event Bus** — Inter-plugin pub/sub with error isolation
- **PluginContext** — Controlled access to Maestro internals (registry, R2, session logger, agent registration, hooks, events)

### Weight State Snapshots

Save, restore, diff, and delete system configuration snapshots capturing plugin states, active agents, thresholds, and runtime config overlay.

---

## Agent Council

| Agent | Model | Role |
|-------|-------|------|
| GPT-4o | `gpt-4o` (OpenAI) | Primary reasoning engine |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` (Anthropic) | Contextual analysis |
| Gemini 2.5 Flash | `models/gemini-2.5-flash` (Google) | Pattern-focused, low latency |
| Llama 3.3 70B | `meta-llama/llama-3.3-70b-instruct` (OpenRouter) | Diversity anchor (open-weight) |
| ShardNet | `distributed` (Storage Network) | Proof-of-storage distributed inference |

---

## Quick Start

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python setup.py        # Windows, macOS, Linux — just needs Python + Docker
```

On macOS/Linux you can also use `make setup`.

API keys can be configured through the Web UI — no `.env` file required.

---

## Full Changelog

See [changelog.md](changelog.md) for the complete version history.
