# Maestro-Orchestrator Quickstart

## Prerequisites
- Docker & Docker Compose v2+

## Docker (Recommended)

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
make setup
```

The setup script builds the container, waits for the health check to pass, and opens your browser to `http://localhost:8000`. The API Key settings panel opens automatically on first launch -- paste at least one provider key and start querying the council.

Keys are saved through the Web-UI and persist across container restarts. No `.env` file is needed.

After initial setup, use `make up` / `make down` to start and stop the container. Run `make` to see all available commands.

> **CLI mode:** `MAESTRO_MODE=cli docker compose up --build`

## Local Development

### Web-UI (Backend + Frontend)

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your API keys
make dev               # starts backend + frontend together
```

Or start services individually:
```bash
uvicorn backend.main:app --reload --port 8000   # backend
cd frontend && npm install && npm run dev        # frontend (separate terminal)
```

The UI will be available at `http://localhost:5173` and proxies API calls to the backend.

### CLI Mode

```bash
python -m maestro.cli
```

Type prompts at the `maestro>` prompt. Results include agent responses, consensus, dissent analysis, NCG benchmark, and R2 grade. Type `/help` for available commands.

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Customizing Agents

Agent implementations live in `maestro/agents/`. Each agent extends the shared base class in `maestro/agents/base.py`.

## Contribute

Check `CONTRIBUTING.md` to learn how to help build Maestro-Orchestrator.
