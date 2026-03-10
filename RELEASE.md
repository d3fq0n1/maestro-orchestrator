# Maestro-Orchestrator v0.6.3.1

**Multi-Agent AI Orchestration with Synthetic Consensus and Dissent**

---

## What's New in v0.6.3.1

### Bug Fixes: Windows Setup

- **UnicodeEncodeError on Windows** — `setup.py` crashed silently on launch when Python was installed via winget or the Microsoft Store (which default to the system code page, not UTF-8). The banner, spinner, and status glyphs raised `UnicodeEncodeError` before any output appeared. Fixed with `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` at startup.
- **"no configuration file provided"** — `setup.py` called `docker compose up` without setting a working directory. Running the script from any path other than the project root caused Docker Compose to fail finding `docker-compose.yml`, with the error only visible in `.setup-build.log`. Fixed by pinning the working directory to the script's own location at module load time.

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
