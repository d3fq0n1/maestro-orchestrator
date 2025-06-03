# Maestro-Orchestrator

**Purpose:** Unify the outputs of multiple AI agents into a single coherent, self-refining answer using quorum logic.

---

## 🧠 Overview

Maestro-Orchestrator is an AI-native framework that coordinates multiple large language model (LLM) agents—each acting independently—to derive consensus-based, multi-perspective responses. This orchestrator is designed to be lightweight, extensible, and ethically grounded.

Built by a father, not a startup. Maintained by ritual, not chaos.

---

## ✅ Current Version: `v0.2-webui`

### 🔧 Backend

- **Engine:** Python + FastAPI  
- **Entrypoint:** `main.py` (FastAPI app exposes `/api/ask`)  
- **Agents:**
  - `Sol` → OpenAI (GPT-4)
  - `Aria` → Anthropic Claude
  - `Prism` → Google Gemini
  - `TempAgent` → OpenRouter (Mistral or alternate model)
- **Orchestration Logic:** `orchestrator_foundry.py`
- **Environment:** Loaded via `.env` using `python-dotenv`
- **Run (Dev):**  
  ```bash
  uvicorn main:app --reload --port 8000
🖥️ Frontend
Stack: React + Vite + TailwindCSS

Entrypoint: ui/src/maestroUI.tsx

Features:

Live agent response feed with emoji identity

Quorum logic display and session history

Input form with error handling

Run (Dev):

bash
Copy
Edit
cd ui
npm install
npm run dev
🐳 Docker Support
A complete Docker container is available to run both frontend and backend with .env injection:

bash
Copy
Edit
docker-compose up --build
🔗 Communication
API Call: fetch("http://localhost:8000/api/ask")

CORS: Fully enabled for local development

📁 Project Structure (Simplified)
bash
Copy
Edit
maestro-orchestrator/
├── main.py                   # FastAPI server
├── orchestrator_foundry.py  # Core agent logic + quorum system
├── orchestration_livefire.py # CLI mode orchestrator
├── ui/                      # Frontend app (Vite)
│   ├── index.html
│   └── src/maestroUI.tsx
├── .env.template            # Documents expected API keys
├── docker-compose.yml       # Full-stack container config
├── Dockerfile               # Frontend & backend build logic
└── README.md
📌 Milestones
✅ v0.2-webui: Multi-agent orchestration, FastAPI backend, functional UI, and Dockerized capsule stability

🔜 v0.3 planned:

R2 Engine (reinforced consensus + audit trail)

MAGI meta-agent loop for integrity checks

Immutable Snapshot Ledger

Unified CLI/UI session logging

📄 Documentation Roadmap
In-progress under /docs/:

architecture.md

agents.md

ui-guide.md

RELEASE.md

CHANGELOG.md

Optional future additions:

SECURITY.md

CONTRIBUTING.md

COMMERCIAL_LICENSE.md

Made with persistence by defcon — a self-taught sysadmin and father of three, building a future where synthetic minds collaborate with ours instead of replacing them.






