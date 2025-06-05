
# 🧠 Agent Roles – Maestro-Orchestrator

**Version:** v0.2-webui  
**Status:** Containerized and Modular  
**Last Updated:** 2025-06-05  
**Maintainer:** defcon

Maestro-Orchestrator integrates multiple LLM agents via a containerized backend and frontend system. This document outlines the roles and routing logic for each agent within the orchestrated council.

---

## 🧱 Containerized Deployment Context

As of `v0.2-webui`, agents operate within a modular, container-friendly system:

- The **FastAPI backend** routes prompts to individual agents based on configuration
- The **React/Vite frontend** displays all agent responses and quorum status
- Agents are defined in Python as modular handlers with consistent schema
- Role randomization is handled within container execution, not hardcoded

---

## 🎭 Current Agent Council

| ID          | Codename     | Backed By           | Description                                  |
|-------------|--------------|---------------------|----------------------------------------------|
| `sol`       | Sol          | OpenAI (GPT-4)      | Language-first anchor and orchestrator       |
| `aria`      | Aria         | Claude (Anthropic)  | Moral and philosophical lens                 |
| `prism`     | Prism        | Gemini (Google)     | Analytical and pattern-focused perspective   |
| `tempagent` | TempAgent    | OpenRouter (varied) | Rotating agent for external model injection  |

---

## 🔁 Role Randomization Logic

- **Session-based rotation** prevents static role alignment
- Ensures **epistemic dynamism** and reduces echo chamber effects
- Implemented in orchestration logic, not frontend or fixed backend mapping

---

## 🔄 API Behavior

Each agent receives the same prompt via `/api/ask`, responds independently, and contributes to:

- **Raw response log**
- **Quorum evaluation**
- **Consensus summary**

All responses are displayed in the frontend UI alongside a computed consensus outcome.

---

## 🚧 Future Agents

- 🔡 Multilingual agents (French, Spanish, etc.)
- 🖼️ Image-captioning or visual interpretation models
- 🔊 Audio transcription or multimodal comprehension agents
- 🤖 Simulated agents for adversarial testing

---

## 🧩 Notes for Devs

- Defined in `agents_config.py`
- Loaded dynamically into containerized FastAPI app
- Must conform to response schema:
```json
{
  "agent_name": "sol",
  "response": "string",
  "token_usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

---

Build for contradiction. Code for convergence.
