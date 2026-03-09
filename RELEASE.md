# Maestro-Orchestrator v0.5

**Multi-Agent AI Orchestration with Synthetic Consensus and Dissent**

---

## What's New in v0.5

### Documentation Overhaul

All documentation reviewed, corrected, and brought in sync with the current codebase. Version references, agent names, model IDs, API endpoints, and feature descriptions are now consistent across `readme.md`, `docs/`, and the changelog.

### Auto-Updater (milestone complete)

The built-in update system introduced in v0.4.3 is now a stable, documented feature of the v0.5 baseline:

- **Web UI Update panel** — check for updates, view available versions, apply with one click
- **REST API** — `GET /api/update/check`, `POST /api/update/apply`, `GET/PUT /api/update/remote`
- **CLI** — `/update` command in the interactive REPL
- **Shell** — `make update` pulls latest and rebuilds Docker
- **Docker-aware** — uses `git ls-remote` + `VERSION` file where full git history is unavailable
- **Configurable remote** — `MAESTRO_UPDATE_REMOTE` env var or Update panel setting

---

## Highlights from v0.4.x

For users upgrading from v0.3.x, here's what the full v0.4 series brought:

- **SSE Response Streaming** (`/api/ask/stream`) — agent responses render progressively as they arrive
- **Updated agent models** — GPT-4o, Claude Sonnet 4.6, Gemini 2.5 Flash, Llama 3.3 70B
- **One-command setup** — `make setup` or `python setup.py` handles everything
- **Health endpoint** — `GET /api/health` for monitoring and Docker HEALTHCHECK
- **Optional `.env`** — configure API keys entirely through the Web UI
- **Comprehensive error handling** — no silent failures; every agent and API endpoint has typed exception handling
- **Agent system prompts** — current date injected into every agent system prompt

---

## Agent Council

| Agent | Model | Role |
|-------|-------|------|
| GPT-4o | `gpt-4o` (OpenAI) | Primary reasoning engine |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` (Anthropic) | Contextual analysis |
| Gemini 2.5 Flash | `models/gemini-2.5-flash` (Google) | Pattern-focused, low latency |
| Llama 3.3 70B | `meta-llama/llama-3.3-70b-instruct` (OpenRouter) | Diversity anchor (open-weight) |

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

- **Multi-agent orchestration** — route prompts through 4 LLMs simultaneously
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
