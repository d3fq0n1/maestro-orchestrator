# 🤖 Agents Overview: Maestro-Orchestrator

## Purpose

This document defines each AI agent integrated into Maestro-Orchestrator, along with its identity, provider, and behavior expectations.

---

## 🧠 Agent Definitions

### `Sol`

* **Provider:** OpenAI
* **Model:** GPT-4 (via OpenAI API)
* **Role:** Foundation agent — high-context reasoning, fallback anchor
* **Emoji:** ☀️

### `Aria`

* **Provider:** Anthropic
* **Model:** Claude
* **Role:** Ethical lens and language nuance, often human-centric
* **Emoji:** 🎻

### `Prism`

* **Provider:** Google
* **Model:** Gemini
* **Role:** Perspective diversity and interpretive logic
* **Emoji:** 🔮

### `TempAgent`

* **Provider:** OpenRouter (Mistral or other)
* **Model:** Configurable
* **Role:** Rotating wildcard — dissent, chaos factor, testbed
* **Emoji:** 🧪

---

## 🔄 Behavior

All agents:

* Receive the **same prompt** simultaneously
* Respond independently without knowledge of other agents’ outputs
* Return raw text or structured responses (as applicable)

---

## 🧩 Schema (Example)

```json
{
  "agent": "Sol",
  "emoji": "☀️",
  "response": "Here is my answer...",
  "model_info": "gpt-4",
  "source": "OpenAI"
}
```

---

## 🛠️ Future Agent Concepts

* **Caspar:** Always dissenting agent, narrative devil’s advocate (symbolic: ☠️)
* **Vigil:** Placeholder for future human-in-the-loop or hybrid agent (symbolic: 👁️)
* **Proxy Agents:** Agents that mirror or refine consensus instead of originating ideas

These are planned for later quorum rounds, auditing, or exploration of symbolic reasoning chains.

---

## 📎 Notes

* All agent names are metaphorical but consistently mapped
* Agent roles are not fixed — models may rotate or be remapped
* Diversity of model vendors helps minimize shared blind spots
