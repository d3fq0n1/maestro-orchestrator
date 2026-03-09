# Maestro-Orchestrator v0.4.3

**Multi-Agent AI Orchestration with Synthetic Consensus and Dissent**

---

## What's New in v0.4.3

### Built-in Auto-Updater

Stay current without re-cloning. Maestro now ships with a fully integrated update system accessible from both the Web UI and the API.

- **Update panel in the Web UI header** — check for updates, view available versions, and apply them with a single click
- **REST API endpoints** — `GET /api/update/check`, `POST /api/update/apply`, `GET/PUT /api/update/remote`
- **Docker-aware** — uses `git ls-remote` and a `VERSION` file for environments where a full git history isn't available; git is now included in the Docker image
- **Configurable remote** — set a custom update remote via the `MAESTRO_UPDATE_REMOTE` environment variable or directly from the Update panel
- **Graceful degradation** — if git is missing or the remote is unreachable, the UI shows friendly error messages instead of crashing

### Agent System Prompts

All four council agents now receive a system prompt with the current date. This prevents models from hallucinating outdated information or behaving as if they are in a prior time period.

### Session History Fix

The session history page no longer renders blank — the API response is now correctly unwrapped before display.

### Streaming Fix

Fixed an issue where SSE streaming could lose track of agent tasks by switching from `asyncio.as_completed` to `asyncio.wait` for reliable task-to-agent mapping.

---

## Highlights from v0.4.x

For users upgrading from v0.3.x, here's what the full v0.4 series brings:

- **SSE Response Streaming** (`/api/ask/stream`) — agent responses render progressively as they arrive
- **Updated agent models** — GPT-4o, Claude Sonnet 4.6, Gemini 2.5 Flash, Llama 3.3 70B
- **One-command setup** — `make setup` or `python setup.py` handles everything
- **Health endpoint** — `GET /api/health` for monitoring and Docker HEALTHCHECK
- **Optional `.env`** — configure API keys entirely through the Web UI
- **Comprehensive error handling** — no silent failures; every agent and API endpoint has typed exception handling

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
