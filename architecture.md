# 🏗️ Architecture: Maestro-Orchestrator

## System Overview

Maestro-Orchestrator is designed as a modular, agent-based framework for conducting multi-model conversations and synthesizing responses through structured quorum logic.

### 🎯 Core Principles

* **Agent Independence:** Each AI agent responds in isolation, unaware of the others’ output.
* **Quorum Consensus:** The orchestrator uses configurable quorum thresholds (default: 2/3) to determine agreement.
* **Structured Dissent:** Minority opinions are preserved alongside majority answers for transparency.

---

## 🔧 Backend Components

### `main.py`

* FastAPI app
* Exposes `POST /api/ask` for client queries
* Loads API keys from `.env`
* Calls orchestration engine with prompt

### `orchestrator_foundry.py`

* Initializes all agents (Sol, Aria, Prism, TempAgent)
* Dispatches the prompt in parallel (async)
* Aggregates agent responses
* Computes quorum consensus + dissent
* Returns a structured payload with all outputs

---

## 🧠 Agent Model

Each agent has:

* A distinct identity and source (e.g., OpenAI, Anthropic)
* An assigned emoji (for UI display)
* A shared schema for input/output handling

> All agents respond to the same prompt with no knowledge of peer outputs.

---

## 🖥️ Frontend Components

### `ui/index.html`

* HTML shell for Vite app

### `ui/src/maestroUI.tsx`

* React root with TailwindCSS styling
* Submits prompt to `/api/ask`
* Displays each agent's response with emoji
* Renders consensus and dissent states

---

## 🧪 Data Flow

```
[User Prompt] → /api/ask → [Orchestrator] → [All Agents]
                                        ↓
                                  [Responses]
                                        ↓
                            [Consensus + Dissent]
                                        ↓
                                 [Frontend Render]
```

---

## 🔒 Quorum Calculation Logic

```python
# Pseudocode
if matching_responses >= quorum_threshold:
    result = "Consensus"
else:
    result = "No consensus"
    preserve all responses for user
```

---

## ⚙️ Config

* `.env` file for API keys (template provided)
* CORS enabled in FastAPI

---

## 📈 Extensibility

Future modules (v0.3+) include:

* R2 Engine: Enforce response scoring and reinforcement
* Snapshot Ledger: Immutable history anchoring
* MAGI Loop: Meta-agent audits for drift detection and ethics monitoring
* CLI ↔ UI shared session history
