# Agent Architecture

Maestro-Orchestrator operates through modular agents—encapsulated logic modules representing distinct language models or personalities. Each agent contributes independently to a session before quorum logic determines the final synthesized response.

---

## 🧩 Core Agent Roles

- **Sol**: Acts as the grounding and synthesis layer. Sol typically initiates or summarizes interactions and helps maintain philosophical and ethical consistency.
- **Aria**: A supporting agent with a different style or personality, offering complementary insight to Sol.
- **OpenRouter_TemporaryAgent**: A placeholder for any third-party or experimental model connected via API (e.g., Claude, Gemini, Grok).

---

## ⚙️ Agent Definition Format

Each agent follows a standardized Python class format located in the `agents/` directory:

```python
class SolAgent(BaseAgent):
    def __init__(self):
        self.name = "sol"
        self.prompt_style = "structured"
        # Define model behavior or API config here

    def call(self, prompt: str) -> str:
        # Generate response using model or stub
        return openai_call(prompt)
```

---

## 🔁 Agent Rotation

Agents participate in rounds. Each round, agents receive the same prompt and generate independent responses. These are later evaluated by a vote mechanism or synthesis pass.

---

## 🔒 Extending Agents

To add a new agent:
1. Create a new Python file in `agents/`.
2. Inherit from `BaseAgent`.
3. Implement a `.call()` method.
4. Register the agent in the orchestrator loop.

---

## 🧠 Philosophy of Design

Agents are intentionally diverse in origin and behavior. This diversity increases robustness and makes the system less susceptible to monoculture logic traps.

