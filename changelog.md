# 📜 Changelog — Maestro-Orchestrator

All notable changes to this project will be documented in this file.

---

## \[v0.2-webui] — 2025-06-03

### Added

* Fullstack Docker container (FastAPI + Vite React UI)
* `/api/ask` endpoint for orchestration prompts
* Static frontend mount via FastAPI with CORS
* Agent emoji rendering and error handling in UI
* `.env.template` support and Docker runtime injection

### Fixed

* TypeScript JSX build issues (`--jsx` flag added)
* Request model mismatch between frontend and backend
* Broken API call path from `run_orchestration` → `/api/ask`

---

## \[v0.1] — 2025-05-30

### Added

* Initial orchestration agent logic
* `orchestrator_foundry.py` with placeholder agents
* CLI: `orchestration_livefire.py`
* `.env` parsing and key loading
* Manual session loop for debug use

---

> This project follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and semantic versioning.
