# ──────────────────────────────────────────────
# Stage 1: Build Vite Frontend
# ──────────────────────────────────────────────
FROM node:20 AS frontend-builder

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
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend logic
COPY scripts/orchestrator_foundry.py ./orchestrator_foundry.py
COPY agents/ ./agents/
COPY .env.template .env

# Copy Vite frontend build output to a known path
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Debug: Confirm assets are present
RUN ls -la ./frontend/dist && ls -la ./frontend/dist/assets || echo "⚠️  Assets directory missing"

# Expose FastAPI port
EXPOSE 8000

# Launch Maestro backend
CMD ["uvicorn", "orchestrator_foundry:app", "--host", "0.0.0.0", "--port", "8000"]
