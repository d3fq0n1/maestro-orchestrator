# Standalone backend Dockerfile
# Build context must be the repository root:
#   docker build -f backend/Dockerfile .
#
# For the recommended setup, use docker-compose with the root Dockerfile instead.

# Stage 1: Build frontend
FROM node:20-alpine AS builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install
COPY frontend ./
RUN npm run build

# Stage 2: Serve FastAPI + UI
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application
COPY backend/ ./backend/

# Copy maestro orchestration package
COPY maestro/ ./maestro/

# Create persistent data directories
RUN mkdir -p data/sessions data/r2

# Copy environment template as fallback
COPY .env.example ./backend/.env

# Copy frontend build output into the path expected by backend/main.py
COPY --from=builder /app/frontend/dist ./backend/frontend/dist

EXPOSE 8000

WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
