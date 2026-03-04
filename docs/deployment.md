# Deployment Guide - Maestro-Orchestrator

This guide walks you through deploying Maestro-Orchestrator in local, containerized, or production environments.

---

## Local Development

### Backend (FastAPI)

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Add your OpenAI / Anthropic / Google API keys
   ```

4. Start the backend server:
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

The backend will be available at `http://localhost:8000/api/ask`.

---

### Frontend (React + Vite)

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install frontend dependencies:
   ```bash
   npm install
   ```

3. Start the dev server:
   ```bash
   npm run dev
   ```

Frontend will run at `http://localhost:5173`.

---

### Interactive CLI (local)

```bash
python -m maestro.cli
```

This opens a REPL where you can type prompts and see the full orchestration pipeline output (agent responses, consensus, dissent, NCG benchmark, R2 grade) directly in the terminal.

---

## Docker Deployment (Recommended)

### Prerequisites
- Docker
- Docker Compose v2+

### Quick Start

```bash
python setup.py          # works on Windows, macOS, and Linux
```

On macOS/Linux you can also use `make setup`.

This builds the container, waits for the health check to pass, and opens your browser to `http://localhost:8000`. No `.env` file is required -- API keys can be configured through the Web-UI and persist across container restarts.

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

### CLI Mode

Set the `MAESTRO_MODE` environment variable to launch the interactive terminal REPL:

```bash
MAESTRO_MODE=cli docker compose up --build
```

### Health Check

The container includes a built-in health check that polls `GET /api/health`. Docker reports the container as `healthy` once the API is ready to accept requests. You can check status with:

```bash
docker compose ps
# or on macOS/Linux: make status
```

---

### Docker File Summary

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

In production, make sure to:
- Disable `--reload`
- Set `DEBUG=False`
- Configure external logging and monitoring

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
- Use `make build` (or `docker compose build --no-cache`) if frontend isn’t updating

---

For architecture overview, see: [`architecture.md`](./architecture.md)  
For quorum logic, see: [`quorum_logic.md`](./quorum_logic.md)
