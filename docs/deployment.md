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
- Docker Compose

### Quick Start

```bash
cp .env.example .env   # add your API keys
docker-compose up --build
```

On startup, a mode-selection dialog will appear asking you to choose **Web-UI** or **CLI** mode. Choose the mode you want and press Enter.

- **Web-UI**: The dashboard + API will be available at `http://localhost:8000`
- **CLI**: An interactive terminal opens for running prompts directly

### Skipping the Startup Dialog

Set the `MAESTRO_MODE` environment variable to bypass the dialog:

```bash
# Always launch Web-UI (recommended for headless / CI / production)
MAESTRO_MODE=web docker-compose up --build

# Always launch CLI
docker-compose run maestro   # with MAESTRO_MODE=cli in .env
```

When no TTY is attached (e.g., `docker-compose up` without `-it`), the system defaults to Web-UI automatically.

---

### Docker File Summary

- **`Dockerfile`** (root):
  - Multi-stage build: Stage 1 builds the Vite frontend, Stage 2 sets up the Python backend and copies the built frontend as static assets
  - Installs `dialog` for the ncurses startup GUI
  - Copies `backend/`, `maestro/`, `entrypoint.py`, and built frontend into the container
  - Uses `entrypoint.py` as the default CMD (unified startup wrapper)

- **`docker-compose.yml`**:
  - Defines `maestro` service with `stdin_open: true` and `tty: true` for interactive mode
  - Loads API keys from `.env`
  - Maps port `8000:8000`
  - Uses named volumes for session and R2 data persistence

---

## Environment Configuration

Copy `.env.example` to `.env` and fill out:

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
- Use `--no-cache` with Docker builds if frontend isn’t updating

---

For architecture overview, see: [`architecture.md`](./architecture.md)  
For quorum logic, see: [`quorum_logic.md`](./quorum_logic.md)
