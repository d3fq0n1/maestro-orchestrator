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

# Install backend dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application
COPY backend/ ./backend/

# Copy maestro orchestration package (agents, NCG, R2, sessions, etc.)
COPY maestro/ ./maestro/

# Create persistent data directories
RUN mkdir -p data/sessions data/r2

# Copy environment template as fallback (override via env_file or -e flags)
COPY .env.example ./backend/.env

# Copy Vite frontend build output into the path expected by backend/main.py
COPY --from=frontend-builder /app/frontend/dist ./backend/frontend/dist

EXPOSE 8000

# Launch from the backend directory so relative imports resolve correctly
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
