# Setup Guide

For complete setup instructions, see:

- [Quickstart](./quickstart.md) -- minimal steps to get running
- [Deployment Guide](./deployment.md) -- local, Docker, and production deployment
- [Developer Guide](./Maestro%20Orchestrator%20Developer%20Guide.md) -- full developer reference

## Quick Reference

### Backend

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt
cp .env.example .env  # add your API keys
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker (Recommended)

```bash
docker-compose up --build
```

Backend: `http://localhost:8000/api/ask`
Frontend: `http://localhost:5173`
