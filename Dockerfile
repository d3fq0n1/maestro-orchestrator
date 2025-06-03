# ─────────────────────────────────────────────────────────────
# Stage 1: Build Vite Frontend
# ─────────────────────────────────────────────────────────────
FROM node:20 AS frontend-builder

WORKDIR /app/ui
COPY ui/ ./
RUN npm install && npm run build


# ─────────────────────────────────────────────────────────────
# Stage 2: Assemble Backend + Serve Static UI
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend logic
COPY main.py orchestrator_foundry.py ./
COPY agents/ ./agents/
COPY .env.template .env

# Copy Vite build output from frontend stage
COPY --from=frontend-builder /app/ui/dist ./ui/dist

# Expose FastAPI port
EXPOSE 8000

# Start unified API + frontend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
