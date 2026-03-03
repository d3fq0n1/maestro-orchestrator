## [0.3.0] - 2026-03

### Added

- MAGI meta-agent governance (`maestro/magi.py`) — cross-session pattern analysis with structured recommendations
- API key management (`maestro/keyring.py`, `maestro/api_keys.py`, `maestro/cli_keys.py`) — in-app key configuration, validation, and secure `.env` persistence
- Key management REST endpoints: `GET /api/keys`, `POST /api/keys/{provider}`, `POST /api/keys/validate`
- Key management test suite (`tests/test_keyring.py`)
- MAGI REST endpoint: `GET /api/magi`
- Frontend key configuration panel in the web UI
- Session history logging (`maestro/session.py`) — every orchestration session persisted to `data/sessions/` as structured JSON
- Session history REST API (`maestro/api_sessions.py`) — `GET /api/sessions` and `GET /api/sessions/{id}`
- Dissent analysis module (`maestro/dissent.py`) — pairwise semantic distance, outlier detection, cross-session trend analysis
- R2 Engine (`maestro/r2.py`) — session scoring, consensus ledger indexing, and improvement signal generation
- Cross-session trend analysis detects confidence trends, recurring signals, and repeated suspicious consensus
- Code Injection Engine (`maestro/applicator.py`) — applies validated proposals to the running system via three modes: runtime parameter mutation, AST-based source patching, and config overlay writes
- Rollback & Snapshot System (`maestro/rollback.py`) — append-only ledger with per-injection snapshots; supports single-entry and full-cycle rollback
- Injection Safety Guards (`maestro/injection_guard.py`) — category whitelist, bounds enforcement, rate limiting, post-injection smoke test with automatic rollback on degradation
- Auto-injection opt-in gate via `MAESTRO_AUTO_INJECT=true` environment variable (disabled by default)
- Self-improvement Phase 6 (Code Injection) and Phase 7 (Smoke Test/Rollback) in `SelfImprovementEngine`
- Manual injection endpoint: `POST /api/self-improve/inject/{cycle_id}`
- Rollback endpoints: `POST /api/self-improve/rollback/{rollback_id}`, `POST /api/self-improve/rollback-cycle/{cycle_id}`
- Injection query endpoints: `GET /api/self-improve/injections`, `GET /api/self-improve/rollbacks`
- Code injection test suite (`tests/test_code_injection.py`) — 40 tests covering injection, rollback, guards, and integration

### Removed

- Legacy `agents/` directory (replaced by `maestro/agents/`)
- Legacy `scripts/` directory (orchestrator.py, model_adapters.py, council_session/, etc.)
- Legacy CLI scripts: `backend/orchestration_livefire.py`, `backend/orchestration_livefire_rotating.py`, `backend/maestro_cli.py`
- Legacy utility scripts: `backend/env_debug.py`, `backend/manual_verification.py`
- Root-level `orchestrator_foundry.py` (replaced by `backend/orchestrator_foundry.py`)
- PowerShell scripts: `combo-sync.ps1`, `scaffold.ps1`, `scripts/combosync.ps1`
- Duplicate Dockerfiles: `backend/Dockerfile`, `frontend/Dockerfile` (root `Dockerfile` is canonical)
- Duplicate/stale docs: `.env.template`, root `agents.md`, root `ui-guide.md`, `dev thoughts.md`
- Windows artifacts: `desktop.ini`, `scripts/desktop.ini`
- Vite boilerplate: `frontend/src/counter.ts`, `frontend/src/typescript.svg`

### Fixed

- `backend/main.py` no longer crashes when frontend dist is missing (runs in API-only mode)
- Root `requirements.txt` now references `backend/requirements.txt` instead of listing stale legacy deps
- `.gitignore` cleaned up (removed duplicate entries)
- `frontend/index.html` title changed from "Vite + TS" to "Maestro-Orchestrator"

### Changed

- All documentation updated to reflect current codebase (removed references to deleted files, updated API response format, added key management endpoints)

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
