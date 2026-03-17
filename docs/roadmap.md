# Maestro-Orchestrator Roadmap

**Current Version:** v7.2.4
**Last Updated:** 2026-03-17
**Maintainer:** defcon

---

## Completed Milestones

- **Core Orchestration Logic** -- Functional quorum-based multi-agent orchestration
- **FastAPI Backend** -- Exposes `/api/ask` endpoint for live prompt orchestration
- **React Web UI** -- Full analysis display: R2 grades, quorum bar, dissent, NCG, session history
- **Full Containerization** -- Docker support for one-step deployment of backend + frontend
- **Interactive CLI** -- Full orchestration pipeline in the terminal (`maestro/cli.py`)
- **License Split** -- Custom open-use license and commercial terms clarified
- **NCG Module** -- Novel Content Generation with headless generators, drift detection, and silent collapse prevention
- **Session History Logging** -- Persistent JSON-based session records with unified data layer for cross-session analysis
- **Module Isolation** -- Agent logic refactored into swappable, testable components with shared async interface
- **Dissent Analysis** -- Pairwise semantic distance, outlier detection, cross-session trend analysis, internal_agreement score feeding NCG silent collapse detection
- **R2 Engine** -- Rapid Recursion & Reinforcement: session scoring, consensus ledger indexing, structured improvement signal generation for MAGI, cross-session trend analysis
- **Unified Pipeline** -- Web API runs the full analysis pipeline (dissent, NCG, R2, session logging) on every request; orchestrator foundry is a thin wrapper over the core engine
- **Semantic Quorum** -- Agreement determined by semantic similarity clustering (pairwise distance threshold) rather than exact string matching; numeric agreement_ratio with 66% supermajority
- **MAGI Module** -- Meta-Agent Governance and Insight: reads R2 ledger and session history, detects cross-session patterns (persistent outliers, confidence trends, collapse frequency), produces structured recommendations
- **Headless Generator Selection** -- Automatically selects the best available headless generator (OpenAI with logprobs, Anthropic, or mock fallback) based on API key availability
- **Self-Improvement Pipeline** -- Complete rapid recursion loop: MAGI analysis → code introspection (AST, signal-to-code mapping, token-level analysis) → optimization proposals (threshold tuning, agent config, prompt optimization, architecture refactoring) → MAGI_VIR sandboxed validation → promote/reject cycle
- **MAGI_VIR (Virtual Instance Runtime)** -- Isolated sandbox for testing optimization proposals with ephemeral data directories, benchmark suite, and side-by-side comparison reporting
- **Code Introspection Engine** -- Three-tier analysis: static source (AST parsing, complexity metrics), runtime signal mapping (R2 signals → code locations), and token-level behavior analysis
- **Compute Node Registry** -- JSON-based registry for distributed MAGI_VIR validation across multiple Maestro nodes
- **Self-Improvement API** -- REST endpoints for triggering cycles, reviewing proposals, and managing compute nodes (`/api/self-improve/*`)
- **Self-Improvement CLI Commands** -- `/improve`, `/introspect`, `/cycles` commands in the interactive CLI
- **MAGI Automation Layer** -- Opt-in auto-apply for validated low-risk proposals via `MAESTRO_AUTO_INJECT=true`; category whitelist, bounds enforcement, rate limiting, post-injection smoke test with automatic rollback
- **Model Updates (v0.4)** -- All four council agents updated to current-generation models (gpt-4o, claude-sonnet-4-6, gemini-2.5-flash, llama-3.3-70b-instruct); NCG headless generators updated (gpt-4o-mini, claude-haiku-4-5-20251001)
- **Comprehensive Error Handling (v0.4)** -- All agents, orchestrator, API endpoints, and session/R2 persistence wrapped with typed exception handlers; no silent failures anywhere in the pipeline
- **Auto-Updater (v0.5)** -- Built-in update system that checks the remote repo for new commits and pulls changes in-place; available via `/update` CLI command, `make update`, and optional startup notification (`MAESTRO_AUTO_UPDATE=1`); stashes local changes before pulling, supports Docker rebuild
- **Proof-of-Storage Distributed Inference (v0.6)** -- Full storage network layer: shard registry with topology-aware pipeline construction, cryptographic challenge-response verification (PoRep, PoRes, PoI), reputation scoring integrated with R2, automatic eviction, ShardAgent with failover, standalone node server
- **Modular Plugin Architecture (v0.6)** -- Mod Manager with full plugin lifecycle (discover/validate/load/enable/disable/unload/reload), 8 pipeline hook points, event bus, PluginContext with controlled access to internals, hook ownership tracking for clean deactivation
- **Weight State Snapshots (v0.6)** -- Save/restore/diff system configurations (plugins, agents, thresholds, runtime config); snapshot CRUD via REST API and CLI
- **Remote Compute Node Validation (v0.6)** -- Full MAGI_VIR validation on remote Maestro nodes via the compute node registry and storage network infrastructure
- **Storage Network Dashboard (v0.6.3)** -- Network topology visualization with mirror completeness tracking, visual shard map grid (nodes x layer blocks), neighbor node display, pipeline hop visualization, redundancy indicators, gap detection, and coverage bars. Accessible via Storage button in the Web-UI header.
- **Windows Setup Fix (v0.6.3.1)** -- `setup.py` now works correctly when Python is installed via winget or the Microsoft Store: UTF-8 output encoding forced at startup (fixes `UnicodeEncodeError` crash-on-launch), and working directory pinned to the project root (fixes "no configuration file provided" Docker Compose error when run from a non-root path).
- **TUI Dashboard (v0.7.0)** -- Textual-based terminal dashboard optimized for SoC devices. Mainframe-style single-keypress navigation, first-run API key setup wizard, BTOP-style shard network monitor with animated indicators, LAN shard discovery panel. Full orchestration pipeline with live agent status, consensus/quorum/R2/dissent/NCG metrics, scrollable response viewer. Dual backend modes: direct import (in-process) and HTTP client (multi-device clusters).
- **Model Deliberation (v0.7.1)** -- After initial response collection, each agent reads its peers' responses and produces a refined reply before any analysis runs. Configurable rounds (default 1), default on, non-fatal. All downstream analysis (dissent, NCG, quorum) operates on deliberated positions. Full API exposure (`deliberation_enabled`, `deliberation_rounds`) with SSE events for the streaming endpoint. See [`deliberation.md`](./deliberation.md).
- **Interactive Mode Selector (v0.7.2)** -- Arrow-key terminal selector replaces static command suggestions after Docker setup and in the startup wrapper. TUI crash fix (`ShardNetworkPanel._nodes` collision with Textual internals).
- **Web UI LAN Discovery & Agent Name Fix (v7.1.4)** -- Storage Network panel gains a LAN Discovery tab showing discovered peers, adjacency state, and Maestro Node formation status. TUI Pipeline panel now displays correct model names (GPT-4o, Claude Sonnet 4.6, Gemini 2.5 Flash, Llama 3.3 70B) instead of deprecated codenames. Documentation updated for consistency.
- **Automatic Background Updater (v7.1.5)** -- Background auto-updater that polls git for new commits at a configurable interval (10s–3600s) and optionally auto-applies updates. SSE stream endpoint for real-time notifications. WebUI live banner and auto-update controls. TUI background loop with event-driven notifications and toggle. FastAPI lifespan integration. New env vars: `MAESTRO_UPDATE_INTERVAL`, `MAESTRO_AUTO_APPLY_UPDATES`.
- **TUI Node Detail Crash Fix (v7.1.6)** -- Fixed `NodeDetailScreen._nodes` collision with Textual internals (same class of bug as the v0.7.2 `ShardNetworkPanel` fix). Pressing `N` for node details no longer crashes the TUI.
- **Cluster-Aware Instance Spawning (v7.2.0)** -- TUI Instance manager (`+` key) now spawns fully functional shard/node cluster members with auto-assigned names, IPs, and shard indices. First instance = orchestrator, subsequent = shard workers. Shared Docker network and Redis for inter-node communication. Persistent instance registry. Thread-safe TUI updates. 23 new tests.
- **Boot Loading Animation (v7.2.4)** -- Pre-launch sequence wrapped behind a bouncing-ball animation. Dependency installation runs quietly. All decorative emoji purged from codebase and replaced with ASCII equivalents.

---

## Active Development (v0.8 Goals)

- **Interactive Sessions** -- Similar to Deliberation mode, the human agent can actively participate in deliberations alongside AI agents, injecting their own responses and steering the multi-round debate in real time
- **Token-Level NCG Analysis** -- Bridge from conversational metadata to logprob-level drift measurement across all providers (OpenAI logprobs integration built, pending for Anthropic/Google)
- **NCG Feedback Loops** -- Reshape prompts based on drift signals before they reach conversational agents
- **Reinforcement Loop** -- Feed consensus outcomes into fine-tuning or snapshot logs
- **Plugin Marketplace** -- Curated plugin registry with versioning, dependency resolution, and one-click install
- **ESP32 SoC Support** -- Lightweight node agent for ESP32 microcontrollers (planned)

---

## Planned Milestones

- **Decentralized Consensus Layer** -- Future module allowing cross-host quorum
- **Public Demo Endpoint** -- Limited-use hosted version with transparent logging
- **Contributor Onboarding** -- Expand `CONTRIBUTING.md` with examples and task tags
- **Multilingual Agent Support** -- Introduce language specialization agents
- **Cross-Session NCG Baselines** -- Track what "normal" headless output looks like over time to detect gradual model drift
- **Local Model Support** -- Agent wrappers for llamacpp, Ollama, and other local inference

---

## Community & Contributions

Contributors who align with the principles of transparency and structured dissent are welcome. See `CONTRIBUTING.md` for details, or follow project essays at [substack.com/@defqon1](https://substack.com/@defqon1).

---

## Guiding Principles

- Preserve dissent
- Prevent stagnation
- Embrace disagreement as structure
- Always show your work
