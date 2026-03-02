# Maestro-Orchestrator Quickstart

## Prerequisites
- Python 3.8+
- Internet access (for API calls)
- API keys for at least one provider (OpenAI, Anthropic, Google, or OpenRouter)

## Installation

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

## Running the Backend

```bash
uvicorn backend.main:app --reload --port 8000
```

## Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI will be available at `http://localhost:5173`.

## Running via CLI

```bash
python backend/orchestration_livefire.py
```

## Batch Orchestration

```bash
python scripts/orchestrator.py --input-file path/to/questions.csv
```

## Customizing Agents

Agent implementations live in `maestro/agents/`. Each agent extends the shared base class in `maestro/agents/base.py`.

## Contribute

Check `CONTRIBUTING.md` to learn how to help build Maestro-Orchestrator.
