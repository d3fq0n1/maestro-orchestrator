# Changelog

## [0.7.2] - 2026-03-12

### Added

- **Interactive Mode Selector** (`maestro/selector.py`) — Arrow-key terminal selector with colored highlights, replacing the plain numbered prompt and static command suggestions. Users can now pick TUI, CLI, or Web-UI mode without memorizing commands. Falls back to a numbered prompt when raw terminal input is unavailable.
- **Post-setup launcher** — When `setup.py` detects no graphical browser after Docker setup, it now shows the interactive selector and launches the chosen mode directly instead of printing commands to copy-paste.

### Fixed

- **TUI crash on launch** (`maestro/tui/widgets.py`) — `ShardNetworkPanel.__init__` was setting `self._nodes` to a plain `list`, which overwrote Textual's internal `_nodes` attribute (a `NodeList` used for the widget tree). This caused `AttributeError: 'list' object has no attribute '_append'` when Textual tried to mount child widgets. Renamed to `self._storage_nodes` to avoid the collision.

### Changed

- `entrypoint.py` — `_plain_prompt()` now uses the interactive selector from `maestro/selector.py` instead of a static numbered menu.
- `setup.py` — `open_browser()` shows the interactive selector and launches the chosen mode when no graphical browser is available, instead of printing raw commands.
- **Version bumped to v0.7.2** across readme, frontend, docs, roadmap, node server, plugin manager, release notes, and changelog.

---

## [0.7.1] - 2026-03-11

### Added

- **Deliberation Engine** (`maestro/deliberation.py`) — After collecting initial responses from all agents, each agent now reads what its peers said and produces a refined reply before any analysis runs. This transforms the parallel-collect pattern into an actual multi-round debate.
  - **`DeliberationEngine`** — Configurable rounds (default 1). Non-fatal: if any agent errors during deliberation, it keeps its previous response and the pipeline continues.
  - **`DeliberationReport`** — Full history of every round (round 0 = initial responses, rounds 1..N = deliberation turns), final deliberated responses, participating agents, and skip reason if fewer than 2 healthy agents are available.
  - **`_build_deliberation_prompt()`** — Constructs a per-agent prompt containing the original question, the agent's own previous reply, and all peer agents' previous replies (by model/vendor name). Asks the agent to affirm, refine, or challenge its position.
- **`deliberation_enabled` parameter** — Available on `run_orchestration_async()`, `run_orchestration_stream()`, `run_orchestration()` (sync wrapper), `run_orchestration()` in `orchestrator_foundry.py`, and `stream_orchestration()`. Default `True` (deliberation is on by default).
- **`deliberation_rounds` parameter** — Number of deliberation rounds, default 1, accepted on all orchestration entry points.
- **API request fields** — `POST /api/ask` and `POST /api/ask/stream` now accept `deliberation_enabled: bool` (default `true`) and `deliberation_rounds: int` (default `1`, max `5`) in the JSON request body. Both fields are optional; omitting them keeps the default-on behaviour.
- **SSE deliberation events** (streaming endpoint):
  - `deliberation_start` — Emitted when deliberation begins (includes round count and agent list).
  - `deliberation_round` — Emitted after each round completes (includes round number and all per-agent deliberated responses).
  - `deliberation_done` — Emitted when all rounds finish (summary: rounds completed, agents participated, skip reason if applicable).
  - `stage` event with `name: "deliberation"` emitted at the start of the phase.
- **`deliberation` field in API responses** — Both batch (`/api/ask`) and streaming (`done` event) responses now include a `deliberation` object: `enabled`, `rounds_requested`, `rounds_completed`, `agents_participated`, `skipped`, `skip_reason`.

### Changed

- `maestro/orchestrator.py` — Deliberation phase inserted between initial agent collection and dissent analysis. The deliberated responses replace initial responses for all downstream analysis (dissent, NCG, aggregation). The `done` SSE event includes the `deliberation` summary. Sync wrapper `run_orchestration()` updated with new params.
- `backend/orchestrator_foundry.py` — `run_orchestration()` and `stream_orchestration()` wrappers updated to accept and forward `deliberation_enabled` and `deliberation_rounds`.
- `backend/main.py` — `Prompt` request model extended with `deliberation_enabled` and `deliberation_rounds` fields. Both endpoints log deliberation settings on receipt.
- **Version bumped to v0.7.1** across readme, frontend, docs, roadmap, node server, plugin manager, release notes, and changelog.

---

## [0.7.0] - 2026-03-11

### Added

- **TUI Dashboard** (`maestro/tui/`) — Full Textual-based terminal dashboard optimized for SoC devices (Raspberry Pi 5). Provides the complete orchestration experience in a rich terminal interface.
  - **Agent Panel** — Live status indicators (ready/running/done/error) for each agent in the council with Unicode icons
  - **Consensus Panel** — Real-time metrics display: agreement ratio, quorum status, confidence level, dissent level, R2 grade, NCG drift with color-coded severity
  - **Response Viewer** — Scrollable RichLog showing streaming agent responses and consensus output with syntax highlighting
  - **Shard Network Panel** — Compact storage node overview with status, layer assignments, reputation scores, and memory usage bars
  - **Modal Screens** — F1 help overlay, F2 node detail overlay, F3 API key status overlay
  - **Dual Backend Modes** — Direct import (in-process, lowest latency) and HTTP client (connects to running server via SSE, supports multi-device clusters)
  - **Backend Abstraction** (`maestro/tui/backend.py`) — `MaestroBackend` ABC with `DirectBackend` and `HTTPBackend` implementations; factory function `create_backend(mode, url)`
  - **Textual CSS** (`maestro/tui/maestro_tui.tcss`) — Responsive layout targeting 80x24 minimum terminal size with scaling for larger displays
  - **Entry Point** — `python -m maestro.tui` with `--mode` (direct/http) and `--url` arguments
- **TUI mode in startup wrapper** — `entrypoint.py` now offers TUI as a third option alongside Web-UI and CLI. Selectable via dialog menu or `MAESTRO_MODE=tui` environment variable.
- **New dependencies** — `textual>=0.85.0` and `rich>=13.0.0` added to `backend/requirements.txt`

### Changed

- **`entrypoint.py`** — Dialog menu expanded from 2 to 3 options (web/cli/tui). Plain text fallback updated to match. `MAESTRO_MODE` now accepts `tui` in addition to `web` and `cli`.
- **Documentation updated** — `readme.md`, `docs/architecture.md`, `docs/deployment.md`, `docs/ui-guide.md`, `docs/roadmap.md`, and `changelog.md` updated with TUI documentation, launch instructions, keybindings, backend modes, and file structure.
- **`setup.py` graceful Docker fallback** — When Docker is not installed, setup now suggests `--dev` mode with an interactive prompt to switch, instead of exiting with an error.
- **Version bumped to v0.7.0** across readme, frontend, docs, roadmap, node server, plugin manager, release notes, and changelog.

---

## [0.6.3.1] - 2026-03-10

### Fixed

- **setup.py crash on Windows (UnicodeEncodeError)** — Python installed via winget or the Microsoft Store defaults to the system code page (e.g. cp1252) instead of UTF-8. The banner (`♫`), Braille spinner frames (`⠋⠙⠹…`), and status glyphs (`✓`, `⚠`) all raised `UnicodeEncodeError` before any output was visible, causing the terminal window to flash and close. Fixed by calling `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` immediately after imports.
- **setup.py "no configuration file provided: not found"** — `docker compose up` was called without a working directory, so running `python setup.py` from any path other than the project root caused Docker Compose to fail silently (error visible only in `.setup-build.log`). Fixed by resolving `PROJECT_ROOT` from `__file__` and calling `os.chdir(PROJECT_ROOT)` at module load time. Log file path also pinned to `PROJECT_ROOT` for consistency.

### Changed

- **Version bumped to v0.6.3.1** across readme, frontend, docs, roadmap, node server, plugin manager, and changelog.

---

## [0.6.3] - 2026-03-10

### Added

- **Storage Network Dashboard** — Full GUI for visualizing shard distribution, node topology, and mirror completeness. Accessible via the "Storage" button in the Web-UI header.
  - **Network tab** — Per-model mirror status (full mirror vs partial coverage %), layer coverage bar with color-coded node segments, inference pipeline visualization with hop ordering, neighbor node listing with reputation/latency/status, redundancy map showing replication factor per layer range, gap detection for missing layers.
  - **Shard Map tab** — Visual grid of nodes x layer blocks. Per-node rows with color-coded coverage, aggregate network row with redundancy indicators (green = 2x+, yellow = 1x, red dashed = gap). Scales to any layer count via automatic block sizing.
- **Network topology API endpoint** (`GET /api/storage/network/topology`) — Returns full network state: all nodes with reputation details, per-model layer coverage/gaps/mirror status, inference pipeline, redundancy map, and neighbor node contributions.
- **Shard management API endpoints** documented in REST API table — download, verify, disk-usage, generate-config, and remove endpoints.

### Fixed

- **Node server version mismatch** — `node_server.py` FastAPI version now matches the system version instead of being hardcoded to `0.7.0`.
- **Storage panel not mounted** — `StoragePanel` component was defined but never wired into the main `MaestroUI` component. Now accessible via the header button.
- **Deployment docs missing env vars** — Added `MAESTRO_ORCHESTRATOR_URL`, `MAESTRO_ADVERTISED_HOST`, `MAESTRO_HEARTBEAT_INTERVAL`, `MAESTRO_NODE_PORT` to `deployment.md`.

### Changed

- **Version bumped to v0.6.3** across readme, frontend, docs, roadmap, node server, and changelog.
- **Roadmap updated** — "Storage Network Dashboard" moved from v0.7 goals to completed milestones.

---

## [0.6.2] - 2026-03-10

### Added

- **Shard Utilities** (`maestro/shard_utils.py`): Low-level tools for working with safetensors weight files — header parsing, layer index extraction (supports Llama, GPT-2, BERT, GGUF naming), byte-range SHA-256 hashing for proof-of-replication challenges, shard descriptor generation, and directory scanning.
- **Shard Manager** (`maestro/shard_manager.py`): High-level manager for downloading weight shards from HuggingFace Hub, indexing local shards into manifests, generating `node_shards.json` configs, verifying shard integrity, and reporting disk usage.
- **Node CLI** (`maestro/node_cli.py`): Command-line interface for storage node operators — `setup` (download shards), `start` (run node server), `status` (inventory), `verify` (integrity check), `shards` (config view). Run via `python -m maestro.node_cli`.
- **Real byte-range proof challenges**: Node server `/challenge` endpoint now hashes actual file bytes when shard files exist on disk, with backwards-compatible fallback to deterministic mocks.
- **Node auto-registration**: Node server automatically registers with the orchestrator on startup when `MAESTRO_ORCHESTRATOR_URL` is set, with periodic heartbeats.
- **New environment variables**: `MAESTRO_ORCHESTRATOR_URL`, `MAESTRO_ADVERTISED_HOST`, `MAESTRO_HEARTBEAT_INTERVAL`, `MAESTRO_NODE_PORT` for node server configuration.
- **New dependencies**: `safetensors>=0.4.0`, `huggingface_hub>=0.20.0` added to requirements.
- **Tests**: 47 new tests for shard_utils and shard_manager (87 total storage/shard tests passing).

### Changed

- **Node server rewrite** (`maestro/node_server.py`): FastAPI lifespan management, shard file map for proof challenges, enriched `/health` and `/shards` endpoints showing on-disk verification status. Version bumped to 0.7.0.
- **Version bumped to v0.6.2** across readme, frontend, docs, roadmap, backend (`manager.py`, `node_server.py`), and changelog.

---

## [0.6.1] - 2026-03-10

### Added

- **Update progress bar**: Indeterminate progress bar shown in the Update panel while an update is being applied.
- **Restart server button**: Red "Restart server" button on the success card after a successful update, with `POST /api/update/restart` backend endpoint that sends SIGTERM to trigger Docker's restart policy.
- **Default remote URL**: The updater now defaults to `https://github.com/d3fq0n1/maestro-orchestrator.git` when no remote URL is configured (set via `MAESTRO_UPDATE_REMOTE` in Dockerfile and as a frontend fallback).

### Fixed

- **API keys deleted on update**: Docker-mode auto-updater now preserves `.env` files when syncing the `backend/` directory, preventing API keys from being wiped during system updates.
- **Placeholder consistency in key validation**: `validate_key()` now uses the same placeholder value list as `list_keys()`, so template values from `.env.example` are no longer sent to provider APIs for validation.
- **API endpoint documentation**: Corrected HTTP methods in readme, architecture, and changelog — key update uses `PUT` (not `POST`), added missing `DELETE /api/keys/{provider}` and `POST /api/keys/{provider}/validate` endpoints.
- **Double "Update failed" prefix**: Error messages from Docker-mode updates no longer show "Update failed: Update failed: ..." — removed duplicate prefix from the backend.
- **Errno 17 File exists during update**: `_sync_directory` now uses `dirs_exist_ok=True` so `shutil.copytree` succeeds even when `rmtree` silently fails to remove the destination.
- **Overlapping update UI cards**: The "Update available" card is now hidden when an error is displayed, preventing both cards from showing simultaneously after a failed apply.
- **Python startup warning in Docker**: Added `PYTHONHOME=/usr/local` to Dockerfile to suppress "Could not find platform independent libraries" warning on container startup.

### Changed

- **Version bumped to v0.6.1** across readme, frontend, docs, roadmap, backend (`manager.py`, `node_server.py`), and changelog.

---

## [0.6] - 2026-03-09

### Added

- **Proof-of-Storage Distributed Inference** — Full storage network layer: `StorageNodeRegistry` for shard-aware topology, `StorageProofEngine` with three proof types (PoRep byte-range hash, PoRes latency probe, PoI canary inference), `NodeReputation` scoring (0.7×pass_rate + 0.3×R2_contribution), and automatic eviction below threshold.
- **ShardAgent** (`maestro/agents/shard.py`) — Distributed inference agent implementing the same `Agent.fetch(prompt) -> str` interface. Constructs inference pipelines across storage nodes, routes activation tensors, handles failover to redundant nodes. Follows the agent error handling contract.
- **Node Server** (`maestro/node_server.py`) — Standalone FastAPI server for storage nodes (separate process from Maestro backend). Endpoints: `/infer`, `/challenge`, `/health`, `/heartbeat`, `/shards`. Configured via `MAESTRO_NODE_ID` and `MAESTRO_SHARD_CONFIG` environment variables.
- **Modular Plugin Architecture (Mod Manager)** — Full plugin lifecycle: discover, validate, load, enable, disable, unload, hot-reload. Plugin protocol (`MaestroPlugin` ABC), manifest validation, version compatibility checks, dependency resolution, and permission system.
- **Pipeline Hooks** — 8 hook points in the orchestration pipeline (`pre_orchestration`, `post_agent_response`, `pre_aggregation`, `post_aggregation`, `pre_r2_scoring`, `post_r2_scoring`, `pre_session_save`, `post_session_save`). Hooks run in registration order, support async, and are fail-safe.
- **Plugin Context** — Controlled access to Maestro internals via `PluginContext` dataclass: registry access, R2 engine, session logger, agent registration, hook registration (with ownership tracking), event bus, and scoped logging.
- **Event Bus** — Inter-plugin communication via `emit_event()`/`subscribe_event()`. Decoupled pub/sub with error isolation.
- **Weight State Snapshots** — Save, restore, diff, and delete system configuration snapshots. Captures plugin states, configs, active agents, runtime config overlay.
- **Storage Network REST API** (`maestro/api_storage.py`) — Endpoints under `/api/storage/`: node registration/unregistration, node listing, challenge triggering, pipeline viewing, redundancy mapping, reputation querying.
- **Plugin REST API** (`maestro/api_plugins.py`) — Endpoints under `/api/plugins/` and `/api/snapshots/`: plugin lifecycle management, configuration, health checks, snapshot CRUD, snapshot diff.
- **R2 Node Integration** — `score_node_contribution()` and `detect_node_signals()` methods in R2Engine. New signal types: `node_degradation`, `proof_failure`.
- **Injection Guard Extensions** — Injectable categories extended with `storage` and `module`. Blocked categories extended with `shard_eviction`.
- **CLI Commands** — `/nodes` (storage node listing), `/plugins` (plugin management), `/snapshot` (weight state snapshots), `/challenge` (proof-of-storage challenge cycle).
- **Reference Plugin** — `data/plugins/installed/defcon.shard-agent/` with `manifest.json` and `plugin.py` demonstrating the plugin protocol.
- **Test Suite** — 96 tests total: 14 orchestrator snapshot tests, 28 mod manager tests, 15 storage proof tests, 14 shard registry tests, 7 shard agent tests, 7 weight snapshot tests, 7 plugin hook tests, plus existing suites.
- **Documentation** — New `docs/storage-network.md` and `docs/mod-manager.md`. All existing documentation updated for v0.6 consistency.

### Changed

- **Version bumped to v0.6** across readme, frontend, roadmap, release notes, and changelog.
- `maestro/orchestrator.py` — Added `mod_manager` parameter to `run_orchestration_async()` and `run_orchestration_stream()` with 8 hook call points, all guarded by `if mod_manager:` for backward compatibility.
- `maestro/injection_guard.py` — Extended injectable and blocked category lists.
- `maestro/agents/__init__.py` — Added ShardAgent export.
- `maestro/__init__.py` — Added ModManager export.
- `maestro/cli.py` — Added `/nodes`, `/plugins`, `/snapshot`, `/challenge` commands.
- `backend/main.py` — Mounted storage and plugin API routers.

---

## [0.5] - 2026-03-09

### Changed

- **Version bumped to v0.5** across readme, frontend, roadmap, release notes, and changelog.
- **Documentation review**: All docs audited for accuracy — version headers, agent names, model IDs, API endpoint listings, and feature descriptions are now consistent throughout.
- **Roadmap updated**: Auto-Updater milestone marked complete; v0.5 active development goals promoted to completed milestones section; v0.6 goals outlined.

---

## [0.4.3] - 2026-03-09

### Added

- **Built-in Auto-Updater**: Check for updates and apply them without re-cloning. Available via Web UI Update panel, REST API (`GET /api/update/check`, `POST /api/update/apply`, `GET/PUT /api/update/remote`), and `make update`.
- **Update panel in Web UI header**: Persistent panel with check/apply controls, version display, and configurable remote URL.
- **Docker update support**: Uses `git ls-remote` and `VERSION` file for environments without full git history; git is now included in the Docker image.
- **`MAESTRO_UPDATE_REMOTE` env var**: Configure the update remote URL for Docker and custom deployments.
- **System prompts for all agents**: Current date injected into every agent system prompt to prevent models from hallucinating outdated information.

### Fixed

- **Session history blank page**: API response is now correctly unwrapped before rendering in the frontend.
- **SSE streaming task lookup**: Switched from `asyncio.as_completed` to `asyncio.wait` for reliable task-to-agent mapping during streaming.
- **Update panel error UX**: Friendly error messages with styled cards instead of raw error strings; graceful handling when git is missing.

### Changed

- Version bumped to v0.4.3 across readme, frontend, roadmap, and changelog.

---

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
- Key management REST endpoints: `GET /api/keys`, `PUT /api/keys/{provider}`, `DELETE /api/keys/{provider}`, `POST /api/keys/{provider}/validate`, `POST /api/keys/validate`
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
