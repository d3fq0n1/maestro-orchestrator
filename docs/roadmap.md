# Maestro-Orchestrator Roadmap

**Current Version:** v0.2-webui
**Last Updated:** 2025-06-05
**Maintainer:** defcon

---

## Completed Milestones

- **Core Orchestration Logic** – Functional quorum-based multi-agent orchestration
- **Agent Roles System** – Randomized agent rotation to avoid bias accumulation
- **FastAPI Backend** – Exposes `/api/ask` endpoint for live prompt orchestration
- **React Web UI** – Functional frontend displaying agent output and consensus
- **Full Containerization** – Docker support for one-step deployment of backend + frontend
- **CLI Fallback** – Standalone session runner (`orchestration_livefire.py`)
- **License Split** – Custom open-use license and commercial terms clarified
- **NCG Module** – Novel Content Generation with headless generators, drift detection, and silent collapse prevention
- **Session History Logging** – Persistent JSON-based session records with unified data layer for cross-session analysis
- **Module Isolation** – Agent logic refactored into swappable, testable components with shared async interface
- **Dissent Analysis** – Pairwise semantic distance, outlier detection, cross-session trend analysis, internal_agreement score feeding NCG silent collapse detection

---

## Active Development (v0.3 Goals)

- **R2 Engine** – Scoring, consensus reinforcement, and real-time dissent detection (building on dissent analysis)
- **Reinforcement Loop** – Feed consensus outcomes into fine-tuning or snapshot logs
- **UI Enhancements** – Add tooltips, loading indicators, and error handling
- **Drift Detection** – Meta-agent layer to compare outputs over time for stability (NCG semantic tier operational, token-level tier in progress)
- **Token-Level NCG Analysis** – Bridge from conversational metadata to logprob-level drift measurement (OpenAI logprobs integration built, pending for Anthropic/Google)

---

## Planned Milestones

- **Decentralized Consensus Layer** – Future module allowing cross-host quorum
- **Public Demo Endpoint** – Limited-use hosted version with transparent logging
- **Expanded Documentation** – Add markdown docs on quorum theory, dissent modeling
- **Contributor Onboarding** – Expand `CONTRIBUTING.md` with examples and task tags
- **Multilingual Agent Support** – Introduce language specialization agents
- **NCG Feedback Loops** – Reshape prompts based on drift signals before they reach conversational agents
- **Cross-Session NCG Baselines** – Track what "normal" headless output looks like over time to detect gradual model drift

---

## Community & Contributions

Contributors who align with the principles of transparency and structured dissent are welcome. See `CONTRIBUTING.md` for details, or follow project essays at [substack.com/@defqon1](https://substack.com/@defqon1).

---

## Guiding Principles

- Preserve dissent
- Prevent stagnation
- Embrace disagreement as structure
- Always show your work
