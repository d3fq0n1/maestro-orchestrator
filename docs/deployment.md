# Deployment Guide - Maestro-Orchestrator

This guide walks you through deploying Maestro-Orchestrator in local, containerized, or production environments.

---

## 🧪 Local Development

### Backend (FastAPI)

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. Install backend dependencies:
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
   uvicorn app.main:app --reload --port 8000
   ```

The backend will be available at:  
➡️ `http://localhost:8000/api/ask`

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

Frontend will run at:  
➡️ `http://localhost:3000`

---

## 🐳 Docker Deployment (Recommended)

### Prerequisites
- Docker
- Docker Compose

### Quick Start

```bash
docker-compose up --build
```

This builds both the backend (Uvicorn) and frontend (Vite) in a production-ready containerized environment.

---

### Docker File Summary

- **`Dockerfile`**:
  - Multi-stage build
  - Installs Python backend and builds static frontend
  - Uses Uvicorn to serve FastAPI

- **`docker-compose.yml`**:
  - Defines `web` service for backend
  - Mounts frontend static files
  - Maps port `8000:8000` for external access

---

## 🔒 Environment Configuration

Copy `.env.example` to `.env` and fill out:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
DEBUG=True
```

In production, make sure to:
- Disable `--reload`
- Set `DEBUG=False`
- Configure external logging and monitoring

---

## 🌍 Production Hosting Options

Maestro-Orchestrator can be hosted on:

- 🟢 **Fly.io** – lightweight, easy container hosting
- 🟣 **Render** or **Railway** – zero-config backend + static frontend
- 🔵 **VPS** (e.g., DigitalOcean, Linode) – manual deployment via `docker-compose`
- 🟠 **Bare metal** – for private or localnet deployment

Ensure proper firewall rules are in place for ports `8000` (API) and `80/443` (frontend if reverse proxied).

---

## 🛠️ Deployment Tips

- Use `nginx` or `Caddy` as a reverse proxy
- Monitor API rate limits from OpenAI / Claude / Gemini
- Rotate API keys securely and store them in `.env`
- Use `--no-cache` with Docker builds if frontend isn’t updating

---

For architecture overview, see: [`architecture.md`](./architecture.md)  
For quorum logic, see: [`quorum_logic.md`](./quorum_logic.md)
