# Maestro-Orchestrator

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.md)

Maestro-Orchestrator is a lightweight, container-ready orchestration system for synthetic intelligence. It enables multiple AI agents (like ChatGPT, Claude, Gemini, and others) to collaborate, disagree, and reach consensus using quorum-based logic. Built for rapid prototyping and ethical AI governance, Maestro-Orchestrator is designed for both solo developers and research collectives.

> “Structure preserves dissent. Consensus refines it.”

---

## ✨ Features

- **Multi-Agent Architecture**  
  Includes built-in support for OpenAI, Anthropic, Google, and OpenRouter agents.

- **Orchestration Engine**  
  FastAPI backend with a single `POST /api/ask` endpoint that drives agent collaboration.

- **Frontend UI**  
  Vite-powered React interface shows prompt input, agent responses, and consensus status.

- **Quorum Logic**  
  Structured debate with 66% consensus requirement. Visual quorum display coming soon.

- **Session Logging**  
  Logs each orchestration session to a `.jsonl` file for future meta-agent analysis.

- **Container Ready**  
  Multi-stage `Dockerfile` and `docker-compose.yml` included for one-command spin-up.

- **Safe Configuration**  
  Uses `.env` for secrets. `.env.example` and `.gitignore` are preconfigured for safety.

- **Pluggable Agents**  
  Easily add or swap in new agents using the modular `agent_*.py` format.

---

## 🚀 Quickstart Guide

### 1. Clone the Repo

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
```

### 2. Configure `.env`

Create a `.env` file in the root folder, based on `.env.example`:

```env
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
OPENROUTER_API_KEY=your-openrouter-key
```

### 3. Run Locally (Dev Mode)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then open your browser to: [http://localhost:8000](http://localhost:8000)

### 4. Or Use Docker

```bash
docker-compose up --build
```

After build completes, access at: [http://localhost:8000](http://localhost:8000)

---

## 🧪 Usage Example

Send a prompt to the orchestrator via API or UI:

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Should AI have voting rights?"}'
```

Results will include all agent responses and indicate quorum status.

---

## 📁 Project Structure

```
├── agents/                # Agent definitions (sol, aria, etc.)
├── app/                   # FastAPI backend
├── frontend/              # React + Vite frontend
├── logs/                  # Session transcripts
├── .env.example           # Template for environment variables
├── docker-compose.yml     # One-click container spin-up
└── orchestration_livefire.py # CLI interface
```

---

## 🤝 Contributing

Contributions welcome! Feel free to fork the repo, suggest ideas, or submit PRs.

To get started:

- Create a `.env` using `.env.example`
- Run the app locally or via Docker
- Review `agent_mock.py` for how to add custom agents
- See `CONTRIBUTING.md` (coming soon)

---

## 📜 License

This project is licensed under the MIT License. See [LICENSE.md](LICENSE.md) for details.

---

Built with love, urgency, and defiance by [defcon](https://substack.com/@defqon1) — for the people, not the platforms.
