# Maestro-Orchestrator Quickstart

## Prerequisites
- Python 3.10+
- API keys for at least one provider (OpenAI, Anthropic, Google, or OpenRouter)

## Docker (Recommended)

```bash
cp .env.example .env   # add your API keys
docker-compose up --build
```

Application (UI + API): `http://localhost:8000`

## Local Development

### Backend (FastAPI)

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your API keys
uvicorn backend.main:app --reload --port 8000
```

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

The UI will be available at `http://localhost:5173` and proxies API calls to the backend.

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Customizing Agents

Agent implementations live in `maestro/agents/`. Each agent extends the shared base class in `maestro/agents/base.py`.

## Contribute

Check `CONTRIBUTING.md` to learn how to help build Maestro-Orchestrator.
