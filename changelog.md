## [Unreleased]

### Added

- Session history logging (`maestro/session.py`) — every orchestration session persisted to `data/sessions/` as structured JSON
- `SessionLogger` class with save, load, list, delete, and count operations
- `SessionRecord` dataclass capturing prompt, agent responses, consensus, NCG benchmark, and metadata
- `build_session_record()` convenience function for orchestrator integration
- Session history REST API (`maestro/api_sessions.py`) — `GET /api/sessions` and `GET /api/sessions/{id}`
- Orchestrator now returns `session_id` in its output
- Tests for session persistence, orchestrator integration, and edge cases

### Planned for 0.3.0

- Dissent analysis module (operating on session history data layer)
- R2 Engine for scoring and consensus reinforcement
- Immutable Snapshot Ledger
- MAGI loop for meta-agent audits and drift detection
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
