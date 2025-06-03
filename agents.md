# Agent Guide: Maestro-Orchestrator

This document describes each AI agent integrated into Maestro-Orchestrator, including identity, API origin, and role in the system. Agents are designed to respond independently, contributing to quorum logic through structured reasoning.

---

## 🤖 Agent Overview

| Name        | Source             | Description                              | Emoji |
|-------------|--------------------|------------------------------------------|--------|
| Sol         | OpenAI (GPT-4)     | Primary reasoning engine and scribe      | 🧠     |
| Aria        | Claude (Anthropic) | Contextual analyst, often ethical anchor | 🌱     |
| Prism       | Gemini (Google)    | Pattern-matcher, precision response type | 🌈     |
| TempAgent   | OpenRouter         | Rotating model (Mistral, Mixtral, etc.)  | 🔮     |

---

## 🧠 Agent Behavior

All agents receive the same prompt simultaneously and respond independently. No agent sees another’s output during response generation.

---

## 🧩 Technical Notes

- Each agent is initialized with its own API key from the `.env` file.
- Responses are retrieved asynchronously via HTTP API calls.
- Output is returned in a structured JSON object with agent name and content.
- Each response contributes to quorum consensus logic in `orchestrator_foundry.py`.

---

## 🛠️ Customization

To modify or extend agent behavior:

- Add or remove agents in `orchestrator_foundry.py`
- Update agent display emoji in `ui/src/maestroUI.tsx`
- Ensure proper `.env` keys are defined for each agent
- Re-run locally or rebuild container for changes to take effect

---

Each agent contributes a distinct voice. The strength of Maestro comes not from any one model, but from the space between them.
