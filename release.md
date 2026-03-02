# Maestro-Orchestrator Release Notes

A lightweight, AI-native orchestration engine enabling quorum-based collective reasoning across multiple language models. Built to stabilize synthetic conversation, preserve dissent, and render unified outputs through structured orchestration.

---

## v0.2-webui

**Release Date:** June 2025
**Status:** Stable

### Backend

- FastAPI server (`backend/main.py`) with `/api/ask` POST route
- Core orchestration logic in `orchestrator_foundry.py`
- CLI orchestration available via `backend/orchestration_livefire.py`
- Agent framework includes:
  - Sol (OpenAI GPT-4)
  - Aria (Claude / Anthropic)
  - Prism (Gemini / Google)
  - TempAgent (OpenRouter, e.g. Mistral)
- Environment variables handled via `.env` and `python-dotenv`

### Frontend

- React (Vite) + TailwindCSS stack
- Real-time display of agent responses with emoji identities
- Live quorum rendering and session history
- Input form with error handling
- Dark/light mode toggle
- Fully CORS-enabled for development

### Containerization

- Multi-stage Dockerfile: frontend build + backend serve
- `docker-compose.yml` orchestrates full stack with `.env` passthrough
- Successful build and test of full containerized environment

### Docker Workflow

```bash
# Build and run via Compose
docker-compose up --build

# Or build standalone
docker build -t maestro-webui .
docker run -d -p 8000:8000 --env-file .env maestro-webui
```

### API Keys Expected

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `OPENROUTER_API_KEY`

Use `.env.example` or `.env.template` to construct your own `.env` file.

### Testing & Validation

- Verified roundtrip I/O from frontend to backend
- Multi-agent responses rendered successfully in UI
- CLI orchestrator verified in local test mode
- Environment injection and Docker pathing confirmed functional

### Notable Changes Since v0.1

- Containerization of entire stack
- Removal of Flask remnants
- Unified endpoint `/api/ask`
- Vite JSX build errors fixed via tsconfig.json

---

## v0.1.0

**Release Date:** May 2025

### Added

- Initial proof-of-concept orchestrator script
- Manual prompt input and round-robin agent polling
- CLI-only prototype with JSON log output

---

## Author

**defcon (Blake)** -- Self-taught sysadmin and father, building ethically aware AI frameworks from first principles.

For updates and philosophy: [substack.com/@defqon1](https://substack.com/@defqon1)
