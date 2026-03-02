## [Unreleased]

### Added

- Session history logging (`maestro/session.py`) — every orchestration session persisted to `data/sessions/` as structured JSON
- `SessionLogger` class with save, load, list, delete, and count operations
- `SessionRecord` dataclass capturing prompt, agent responses, consensus, NCG benchmark, and metadata
- `build_session_record()` convenience function for orchestrator integration
- Session history REST API (`maestro/api_sessions.py`) — `GET /api/sessions` and `GET /api/sessions/{id}`
- Orchestrator now returns `session_id` in its output
- Dissent analysis module (`maestro/dissent.py`) — pairwise semantic distance, outlier detection, cross-session trend analysis
- `DissentAnalyzer` produces `internal_agreement` score that feeds into NCG silent collapse detection
- Dissent report included in aggregated output with per-agent profiles and pairwise distances
- R2 Engine (`maestro/r2.py`) — Rapid Recursion & Reinforcement engine for session scoring, consensus indexing, and improvement signal generation
- `R2Engine` with `score_session()`, `detect_signals()`, `index()`, and `analyze_ledger_trends()` methods
- `R2Score` grades each session as strong/acceptable/weak/suspicious based on dissent, NCG drift, and quorum data
- `ImprovementSignal` dataclass produces structured observations (persistent_outlier, suspicious_consensus, compression, healthy_dissent, agent_degradation) for MAGI consumption
- `R2LedgerEntry` writes scored consensus nodes to persistent ledger at `data/r2/`
- Cross-session trend analysis detects confidence trends, recurring signals, and repeated suspicious consensus
- R2 integrated into orchestrator pipeline — every session is scored, signals detected, and indexed after aggregation
- Tests for R2 scoring, signal detection, ledger persistence, trend analysis, and orchestrator integration

### Planned for 0.3.0

- MAGI loop for meta-agent audits — reads R2 ledger to propose code-level improvements (rapid recursion)
- Immutable Snapshot Ledger
- Capsule history anchoring and meta-analysis

---

## [0.2.0] - 2025-06

### Added

- FastAPI backend with `/api/ask` POST route
- Core orchestration engine modularized as `orchestrator_foundry.py`
- Multi-agent architecture: Sol (OpenAI), Aria (Claude), Prism (Gemini), TempAgent (OpenRouter)
- Vite + React + Tailwind frontend with live quorum rendering
- Emoji mapping for agent identity in frontend
- `.env.template` with API key structure and variable examples

### Fixed

- CORS issues during local development
- Basic frontend error handling for API failures

### Changed

- Improved backend modularity for orchestration logic
- Consolidated usage and launch instructions in `README.md`

---

## [0.1.0] - 2025-05

### Added

- Initial proof-of-concept orchestrator script
- Manual prompt input and round-robin agent polling
- CLI-only prototype with JSON log output
