# Maestro-Orchestrator v0.6

**Multi-Agent AI Orchestration with Synthetic Consensus and Dissent**

---

## What's New in v0.6

### Proof-of-Storage Distributed Inference

Full storage network layer enabling distributed inference across storage nodes:

- **Storage Node Registry** — Shard-aware topology with pipeline construction, redundancy mapping, heartbeat tracking, and reputation integration
- **Storage Proof Engine** — Cryptographic challenge-response verification with three proof types: Proof-of-Replication (byte-range hash), Proof-of-Residency (latency probe), Proof-of-Inference (canary inference)
- **Reputation Scoring** — `0.7 × challenge_pass_rate + 0.3 × R2_contribution`. Automatic eviction below threshold. Integrates with R2 for cross-session node health tracking.
- **ShardAgent** — Distributed inference agent with the same `fetch(prompt) -> str` interface as centralized agents. Pipeline construction, activation tensor routing, and failover.
- **Node Server** — Standalone FastAPI server for storage nodes (separate process). Endpoints: `/infer`, `/challenge`, `/health`, `/heartbeat`, `/shards`.

### Modular Plugin Architecture (Mod Manager)

Complete plugin system for extending Maestro without modifying core code:

- **Plugin Protocol** — `MaestroPlugin` ABC with `activate()`, `deactivate()`, `health_check()`, and `on_config_change()`
- **Full Lifecycle** — Discover, validate, load, enable, disable, unload, hot-reload
- **8 Pipeline Hooks** — `pre_orchestration`, `post_agent_response`, `pre_aggregation`, `post_aggregation`, `pre_r2_scoring`, `post_r2_scoring`, `pre_session_save`, `post_session_save`
- **Event Bus** — Inter-plugin communication via pub/sub with error isolation
- **PluginContext** — Controlled access to Maestro internals (registry, R2, session logger, agent registration, hooks, events)
- **Hook Ownership Tracking** — Hooks registered through PluginContext are automatically removed when the plugin is disabled

### Weight State Snapshots

Save, restore, diff, and delete system configuration snapshots:

- Captures plugin states, configs, active agents, runtime config overlay
- Snapshot diff shows exactly what changed between two states
- Restore reverts the entire system to a previous configuration

### New REST API Endpoints

- **Storage Network** — `/api/storage/nodes/*`, `/api/storage/challenge/*`, `/api/storage/pipeline/*`, `/api/storage/redundancy/*`, `/api/storage/reputation`
- **Plugins** — `/api/plugins/*` (lifecycle, config, health)
- **Snapshots** — `/api/snapshots/*` (CRUD, restore, diff)

### New CLI Commands

- `/nodes` — List storage nodes
- `/plugins` — Plugin management
- `/snapshot` — Weight state snapshots
- `/challenge` — Proof-of-storage challenge cycle

---

## Highlights from v0.5

- **Documentation overhaul** — All docs audited for accuracy and consistency
- **Auto-updater** — Built-in update system (Web UI, REST API, CLI, shell)

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

### Docker (Recommended)

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
make setup
```

### Local Development

```bash
python setup.py --dev
# or
make dev
```

API keys can be configured through the Web UI — no `.env` file required.

---

## Core Features

- **Multi-agent orchestration** — route prompts through multiple LLMs simultaneously
- **Proof-of-storage distributed inference** — run models across a network of storage nodes with cryptographic verification
- **Modular plugin architecture** — extend Maestro with plugins (agents, analyzers, hooks) without modifying core code
- **Weight state snapshots** — save/restore/diff system configurations
- **Semantic quorum consensus** — 66% similarity-cluster agreement with dissent preservation
- **Novel Content Generation (NCG)** — headless baseline for detecting model collapse and RLHF drift
- **Dissent analysis** — pairwise semantic distance, outlier detection, cross-session trends
- **R2 Engine** — session scoring, consensus ledger, structured improvement signals
- **MAGI governance** — cross-session pattern analysis with human-reviewable recommendations
- **Self-improvement pipeline** — introspection, proposal generation, sandboxed validation, code injection with rollback
- **Interactive CLI** — full pipeline in the terminal
- **React/Vite dashboard** — R2 grading, quorum bars, dissent visualization, session browser

---

## Full Changelog

See [changelog.md](changelog.md) for the complete version history.
