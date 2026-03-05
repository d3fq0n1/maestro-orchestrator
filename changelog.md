# Changelog

## [0.4.2] - 2026-03-05

### Added

- **SSE Response Streaming**: New `POST /api/ask/stream` endpoint returns Server-Sent Events as each pipeline stage completes (agent responses, dissent, NCG, consensus, R2). The frontend now renders results progressively instead of waiting for the full pipeline to finish.
- **Progressive UI rendering**: Agent responses appear one-by-one as they arrive, with animated stage indicators showing pipeline progress.
- **Streaming stage indicator**: Visual pills show which pipeline stage is currently running (agents, dissent, NCG, consensus, R2).

### Changed

- **Agent display names**: Agents now display their model names instead of codenames: GPT-4o (was Sol), Claude Sonnet 4.6 (was Aria), Gemini 2.5 Flash (was Prism), Llama 3.3 70B (was TempAgent). Class names remain unchanged for backward compatibility.
- **Gemini model updated**: `models/gemini-2.0-flash` → `models/gemini-2.5-flash`
- **Frontend default endpoint**: UI now uses `/api/ask/stream` instead of `/api/ask` for better perceived performance.
- All documentation updated to reflect new agent display names, streaming endpoint, and Gemini model version.

---

## [0.4.1] - 2026-03-04

### Added

- **One-command setup**: `make setup` builds the container, waits for the health check, and opens the browser automatically
- **Makefile**: Common operations — `make up`, `make down`, `make logs`, `make status`, `make build`, `make clean`, `make dev`
- **`setup.sh`**: Setup script with dependency checks, Docker build, health polling, and cross-platform browser launch
- **Health endpoint**: `GET /api/health` returns `{"status": "ok"}` for container and external health monitoring
- **Docker HEALTHCHECK**: Built into both `Dockerfile` and `docker-compose.yml` with 30s start period
- **Restart policy**: `restart: unless-stopped` in `docker-compose.yml` for crash recovery

### Changed

- **`.env` file is now optional**: `docker-compose.yml` uses `required: false` — API keys can be configured entirely through the Web-UI
- **Removed `stdin_open`/`tty`** from `docker-compose.yml` — no longer needed since `MAESTRO_MODE` defaults to `web`
- **`make dev`**: Starts both backend and frontend together for local development
- Updated all documentation (README, deployment, quickstart, setup guide, troubleshooting, contributing, architecture) to reflect simplified deployment workflow

---

## [0.4.0] - 2026-03-04

### Changed

- **Sol** model updated: `gpt-4` → `gpt-4o` (faster, more capable, multimodal-capable)
- **Aria** model updated: `claude-3-opus-20240229` → `claude-sonnet-4-6` (current-generation Anthropic model)
- **Prism** model updated: `models/gemini-1.5-pro-latest` → `models/gemini-2.0-flash` (latest Google model, lower latency)
- **TempAgent** model updated: `mistralai/mistral-7b-instruct` → `meta-llama/llama-3.3-70b-instruct` (significantly stronger diversity anchor)
- **NCG OpenAI headless generator** updated: `gpt-3.5-turbo` → `gpt-4o-mini` (better quality baseline at similar cost)
- **NCG Anthropic headless generator** updated: `claude-sonnet-4-20250514` → `claude-haiku-4-5-20251001` (lightweight, fast, appropriate for headless baseline role)

### Fixed (Error Handling)

- **All agents** (`sol.py`, `aria.py`, `prism.py`, `tempagent.py`): Added `httpx.TimeoutException` and `httpx.ConnectError` specific exception handlers before the generic `except Exception`. Added `KeyError`/`IndexError` handling for malformed API responses. All failure paths return typed error strings — no silent failures.
- **orchestrator.py**: `asyncio.gather` now uses `return_exceptions=True`. Unhandled agent exceptions are caught, logged, and converted to error-string responses so a single agent failure never aborts the pipeline. NCG track failures are caught and logged; the track is skipped rather than raising. Session persistence and R2 indexing failures are caught and logged; the user-facing response is always returned.
- **ncg/generator.py** (`OpenAIHeadlessGenerator`, `AnthropicHeadlessGenerator`): Both generators now wrap their entire API call path in `try/except`. Any exception falls back to `MockHeadlessGenerator` automatically. Anthropic generator now sets an explicit `timeout=30` on the `requests.post` call. Empty content responses are detected and fall back to mock.
- **api_magi.py**: MAGI analysis endpoint now wrapped in `try/except`; returns `HTTP 500` with descriptive detail on failure instead of propagating unhandled exceptions.
- **api_sessions.py**: `list_sessions` wrapped in `try/except` with `HTTP 500` on failure. `get_session` now catches `json.JSONDecodeError` separately and returns `HTTP 422` for corrupted session files.
- **api_self_improve.py**: All 10 endpoints now wrapped in `try/except` with typed `HTTP 500` responses. `HTTPException` instances are re-raised to preserve intentional 400/404 status codes.
- **session.py** (`SessionLogger.load`): Explicit `FileNotFoundError` check with descriptive message before attempting JSON parse. `json.JSONDecodeError` now propagates cleanly to the API layer.
- **r2.py** (`R2Ledger.load_entry`): Explicit `FileNotFoundError` check before read. `json.JSONDecodeError` now propagates cleanly.
- **backend/main.py**: Error log now includes exception type (`{type(e).__name__}: {str(e)}`) for easier debugging. Added inline comment documenting the CORS `allow_origins=["*"]` default and how to restrict it for production.

### Documentation

- `readme.md`: Agent Council table updated with current model IDs. Version badge updated to v0.4.
- `docs/agents.md`: Agent council table updated with model IDs. New **Error Handling Contract** section documents the full exception hierarchy every agent follows.
- `docs/architecture.md`: Agent layer section updated with current model IDs. Orchestrator section updated to document `return_exceptions=True` and non-fatal pipeline stages. NCG section updated with generator selection order and fallback behavior.

---

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
- Multi-agent architecture: GPT-4o (OpenAI), Claude Sonnet 4.6 (Anthropic), Gemini (Google), Llama 3.3 70B (OpenRouter)
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
