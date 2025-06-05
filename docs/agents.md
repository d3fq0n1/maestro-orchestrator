# Agents

Maestro-Orchestrator operates through modular, role-assigned synthetic agents. These agents are typically instantiated from different LLM backends, each assuming rotating functions during orchestration cycles.

---

## Agent Types

### 🔹 Sol
- **Identity**: GPT-4 via OpenAI API
- **Role**: Core logic interpreter, default narrator, and system anchor
- **Strengths**: High reasoning, detailed narrative formatting

### 🔹 Aria
- **Identity**: Claude (Anthropic)
- **Role**: Contextual challenger and contrarian synthesis
- **Strengths**: Ethical grounding, nuance, long-form stability

### 🔹 Prism
- **Identity**: Gemini (Google)
- **Role**: Perceptual enhancer, summarizer, and intuition simulator
- **Strengths**: Clarity, compression, ambiguity handling

### 🔹 openrouter_temporaryagent
- **Identity**: Rotating experimental agent via OpenRouter
- **Role**: Randomized participant; allows injection of new ideas, risks, or dissent
- **Strengths**: Surprising outputs, useful entropy

---

## Rotating Roles

Each agent assumes a functional role in a given session:

- 🧠 **Initiator**: Presents the first synthesized draft or theory
- 🗣️ **Responder**: Challenges, builds upon, or restructures the Initiator’s output
- 🧮 **Arbiter**: Weighs both outputs and produces a consensus evaluation

Agents rotate roles randomly unless overridden manually.

---

## Structured Disagreement

Maestro enforces **66% quorum** for consensus. If an agent dissents, their objection is logged and preserved. This dissent is visible in the UI and encoded in the session output.

---

## Future Agent Modules

- Support for local LLMs (e.g., llama.cpp)
- Plugins and memory injection agents
- Human override or supervised agent modes

---

For orchestration logic, see: [`quorum_logic.md`](./quorum_logic.md)
