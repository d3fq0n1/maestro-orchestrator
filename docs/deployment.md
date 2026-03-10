# Setup & Deployment Guide - Maestro-Orchestrator

This guide covers everything from first-run quickstart to production deployment.

---

## Quick Start (Docker, Recommended)

### Prerequisites
- Docker & Docker Compose v2+

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python setup.py        # works on Windows, macOS, and Linux
```

On macOS/Linux you can also use `make setup`.

The setup script builds the container, waits for the health check to pass, and opens your browser to `http://localhost:8000`. The API Key settings panel opens automatically on first launch -- paste at least one provider key and start querying the council.

Keys are saved through the Web-UI and persist across container restarts. No `.env` file is needed.

After initial setup, use `docker compose up -d` / `docker compose down` to start and stop the container (or `make up` / `make down` on macOS/Linux).

> **CLI mode:** `MAESTRO_MODE=cli docker compose up --build`

### Common Commands

| Task | `make` (macOS/Linux) | Direct command (all platforms) |
|------|---------------------|-------------------------------|
| First-time setup | `make setup` | `python setup.py` |
| Start container | `make up` | `docker compose up -d --build` |
| Stop container | `make down` | `docker compose down` |
| Tail logs | `make logs` | `docker compose logs -f` |
| Container status | `make status` | `docker compose ps` |
| Rebuild (no cache) | `make build` | `docker compose build --no-cache` |
| Remove all data | `make clean` | `docker compose down -v` |
| Update to latest | `make update` | `git pull && docker compose up -d --build` |
| Local dev (no Docker) | `make dev` | `python setup.py --dev` |

### Health Check

The container includes a built-in health check that polls `GET /api/health`. Docker reports the container as `healthy` once the API is ready to accept requests. You can check status with:

```bash
docker compose ps
# or on macOS/Linux: make status
```

---

## Local Development (No Docker)

### Web-UI (Backend + Frontend)

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python -m venv venv
source venv/bin/activate        # macOS/Linux
# .\venv\Scripts\activate       # Windows (PowerShell)
pip install -r requirements.txt
cp .env.example .env            # add your API keys
python setup.py --dev           # starts backend + frontend together
```

Or start services individually:

```bash
uvicorn backend.main:app --reload --port 8000   # backend
cd frontend && npm install && npm run dev        # frontend (separate terminal)
```

Backend API: `http://localhost:8000/api/ask`
Frontend dev server: `http://localhost:5173` (proxies API calls to the backend)

### Interactive CLI

```bash
python -m maestro.cli
```

Type prompts at the `maestro>` prompt. Results include agent responses, consensus, dissent analysis, NCG benchmark, and R2 grade. Type `/help` for available commands.

---

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

---

## Customizing Agents

Agent implementations live in `maestro/agents/`. Each agent extends the shared base class in `maestro/agents/base.py`. See [`agents.md`](./agents.md) for the full agent architecture and how to add new agents.

---

## Environment Configuration

API keys can be configured in two ways:

1. **Web-UI** (recommended): Paste keys in the settings panel on first launch. Keys persist in a Docker volume across restarts.

2. **`.env` file**: Copy `.env.example` to `.env` and fill in your keys. This is optional -- the container starts without it.

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
```

### Storage Network (v0.6)

The following environment variables configure storage nodes (used when running a standalone node server):

```env
MAESTRO_NODE_ID=gpu-node-1              # Unique node identifier
MAESTRO_SHARD_CONFIG=data/node_shards.json  # Path to shard declarations
```

To start a storage node:
```bash
MAESTRO_NODE_ID=gpu-node-1 \
uvicorn maestro.node_server:app --host 0.0.0.0 --port 8001
```

See [`storage-network.md`](./storage-network.md) for full storage network documentation.

In production, make sure to:
- Disable `--reload`
- Set `DEBUG=False`
- Configure external logging and monitoring

---

## Docker File Summary

- **`Dockerfile`** (root):
  - Multi-stage build: Stage 1 builds the Vite frontend, Stage 2 sets up the Python backend and copies the built frontend as static assets
  - Installs `dialog` for the ncurses startup GUI
  - Includes a `HEALTHCHECK` instruction that polls `/api/health`
  - Uses `entrypoint.py` as the default CMD (unified startup wrapper)

- **`docker-compose.yml`**:
  - `.env` file is optional (`required: false`) -- keys can be set via the Web-UI
  - Maps port `8000:8000`
  - Health check with 30s start period
  - `restart: unless-stopped` for crash recovery
  - Named volumes for session, R2, and key persistence

- **`Makefile`**: Common operations for macOS/Linux (setup, up, down, logs, status, build, clean, dev)

- **`setup.py`**: Cross-platform setup script (dep check, build, health wait, browser open). Works on Windows, macOS, and Linux

---

## Production Hosting Options

Maestro-Orchestrator can be hosted on:

- **Fly.io** -- lightweight, easy container hosting
- **Render** or **Railway** -- zero-config backend + static frontend
- **VPS** (e.g., DigitalOcean, Linode) -- manual deployment via `docker-compose`
- **Bare metal** -- for private or localnet deployment

Ensure proper firewall rules are in place for ports `8000` (API) and `80/443` (frontend if reverse proxied).

---

## Deployment Tips

- Use `nginx` or `Caddy` as a reverse proxy
- Monitor API rate limits from OpenAI / Claude / Gemini
- Rotate API keys securely and store them in `.env`
- Use `make build` (or `docker compose build --no-cache`) if frontend isn't updating

---

## Updating

Maestro includes a built-in auto-updater so you don't need to re-clone the repo. The remote URL defaults to `https://github.com/d3fq0n1/maestro-orchestrator.git` and can be changed in the Web-UI or via the `MAESTRO_UPDATE_REMOTE` environment variable.

### From the Web-UI

Open the **System Update** panel from the header. The panel shows available commits, lets you apply updates with a progress bar, and offers a **Restart server** button to reload changes after a successful update.

### From the CLI

```
maestro> /update
```

This checks the remote for new commits, shows you what changed, and asks before applying.

### From the shell

```bash
make update          # pulls latest + rebuilds Docker
```

### Automatic startup check

Set `MAESTRO_AUTO_UPDATE=1` in your environment (or `.env`) to get a notification on startup when new commits are available. This is non-blocking -- it only prints a notice, it won't apply changes without your confirmation.

---

For architecture overview, see: [`architecture.md`](./architecture.md)
For troubleshooting, see: [`troubleshooting.md`](./troubleshooting.md)
