# ──────────────────────────────────────────────
# Stage 1: Build Vite Frontend
# ──────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install
COPY frontend ./
RUN npm run build


# ──────────────────────────────────────────────
# Stage 2: Serve FastAPI + Static UI
# ──────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Tell Python where its standard library lives so the
# "Could not find platform independent libraries <prefix>" warning
# does not appear on container startup.
ENV PYTHONHOME=/usr/local

# Install dialog for the startup mode-selection GUI
RUN apt-get update && apt-get install -y --no-install-recommends dialog git \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application
COPY backend/ ./backend/

# Copy maestro orchestration package (agents, NCG, R2, sessions, etc.)
COPY maestro/ ./maestro/

# Bake the current git commit into a VERSION file so the auto-updater
# knows which version is running even without a .git directory.
ARG GIT_COMMIT=unknown
RUN echo "$GIT_COMMIT" > VERSION

# Copy unified startup wrapper
COPY entrypoint.py ./entrypoint.py

# Create persistent data directories
RUN mkdir -p data/sessions data/r2 backend/env

# Copy environment template as fallback (override via env_file or -e flags)
COPY .env.example ./backend/.env
COPY .env.example ./backend/env/.env

# Point keyring at the volume-backed env file so keys survive rebuilds
ENV MAESTRO_ENV_FILE=/app/backend/env/.env

# Default to Web-UI so the container starts without an interactive dialog.
# Override with MAESTRO_MODE=cli to use the terminal REPL instead.
ENV MAESTRO_MODE=web

# Default remote URL for the auto-updater. Override via .env or
# docker-compose environment to point at a fork.
ENV MAESTRO_UPDATE_REMOTE=https://github.com/d3fq0n1/maestro-orchestrator.git

# Copy Vite frontend build output into the path expected by backend/main.py
COPY --from=frontend-builder /app/frontend/dist ./backend/frontend/dist

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Unified entrypoint — presents a mode-selection GUI on first launch.
# Override with MAESTRO_MODE=web or MAESTRO_MODE=cli to skip the dialog.
CMD ["python", "entrypoint.py"]
