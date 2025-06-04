# Stage 1: Build frontend
FROM node:20-alpine as builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install
COPY frontend .
RUN npm run build

# Stage 2: Serve FastAPI + UI
FROM python:3.11-slim

WORKDIR /app

RUN echo "=== DEBUG: Context before COPY ===" && ls -la

COPY backend/requirements.txt .

RUN echo "=== DEBUG: After COPY ===" && ls -la && pip install --no-cache-dir -r requirements.txt

COPY backend .

COPY --from=builder /app/dist ./frontend/dist

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
