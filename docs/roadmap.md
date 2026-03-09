# Maestro-Orchestrator Roadmap

**Current Version:** v0.5
**Last Updated:** 2026-03-09
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

---

## Active Development (v0.6 Goals)

- **Token-Level NCG Analysis** -- Bridge from conversational metadata to logprob-level drift measurement across all providers (OpenAI logprobs integration built, pending for Anthropic/Google)
- **NCG Feedback Loops** -- Reshape prompts based on drift signals before they reach conversational agents
- **Reinforcement Loop** -- Feed consensus outcomes into fine-tuning or snapshot logs
- **Remote Compute Node Validation** -- Full MAGI_VIR validation on remote Maestro nodes via the compute node registry

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
