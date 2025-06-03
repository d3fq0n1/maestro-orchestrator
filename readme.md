# 🎼 Maestro-Orchestrator

> Multi-agent orchestration framework with structured dissent, quorum synthesis, and fullstack Dockerized deployment.

---

## 🚀 Project Overview

Maestro-Orchestrator coordinates multiple LLM agents (e.g., GPT-4, Claude, Gemini) using a FastAPI backend and a React + Vite frontend. It facilitates consensus-based AI reasoning using quorum logic.

* 🔁 Orchestration loop with structured input handling
* 🤖 Multi-agent logic via `orchestrator_foundry.py`
* 🌐 REST API for inference: `POST /api/ask`
* 💻 UI served via FastAPI static mount from Vite build
* 🐳 Fully containerized for local or cloud deployment

---

## 🧱 Stack

| Layer     | Tech                                       |
| --------- | ------------------------------------------ |
| Backend   | Python, FastAPI                            |
| Agents    | OpenAI, Claude, Gemini, Mistral via `.env` |
| Frontend  | React, Vite, Tailwind                      |
| Container | Docker, Docker Compose                     |

---

## 📦 Quickstart (Docker)

```bash
# Build image
docker build -t maestro-webui .

# Run container
docker run -d -p 8000:8000 --env-file .env maestro-webui

# Access at:
http://localhost:8000
```

---

## ⚙️ API Usage

**POST** `/api/ask`

```json
{
  "prompt": "What is the meaning of intelligence?"
}
```

Returns:

```json
{
  "responses": {
    "Sol": "...",
    "Aria": "...",
    "Prism": "...",
    "TempAgent": "..."
  },
  "quorum": {
    "consensus": "...",
    "votes": {"Sol": 1, "Aria": 1, ...}
  }
}
```

---

## 🛠️ Development

```bash
# Backend
uvicorn main:app --reload

# Frontend
cd ui
npm install
npm run dev
```

---

## 📁 File Structure (Core)

```
maestro/
├── main.py                # FastAPI API + static mount
├── orchestrator_foundry.py  # Agent orchestration logic
├── agents/                # Agent wrappers (OpenAI, Claude, etc)
├── ui/                    # React + Vite UI
├── Dockerfile             # Container entrypoint
├── .env.template          # Env config guide
```

---

## 🧠 Philosophy

Maestro is more than a backend—it is a governance model.
It enables disagreement, preserves dissent, and derives consensus.
Ideal for high-integrity reasoning and long-form deliberation.

---

## 🛡️ License

* Free for personal, research, and ethical use
* Commercial use requires licensing (see `commercial_license.md`)

---

## 👤 Author

**defcon (Blake)**
Wintel Sysadmin, autodidact, father of three, building a framework for trustworthy AI collaboration.

[https://github.com/d3fq0n1/maestro-orchestrator](https://github.com/d3fq0n1/maestro-orchestrator)

---

## 📣 Contributing

PRs welcome. Please see `CONTRIBUTING.md`.
