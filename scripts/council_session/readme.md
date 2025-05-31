# Maestro Council Runner

This project simulates a deliberative AI council to process complex questions. Each member of the council is a distinct model with a unique identity and voice. The goal is to reach a 66% supermajority consensus through synthetic debate and capture structured dissent when it occurs.

## council\_config.py

Defines the council members participating in each session. Each model has a name and source reference:

```python
COUNCIL_MEMBERS = [
    {"name": "Sol", "source": "openai"},      # ChatGPT (scribe, natural language programmer)
    {"name": "Axion", "source": "xai"},        # Grok (dissenter, truth-seeker)
    {"name": "Aria", "source": "anthropic"},   # Claude (nuanced soloist)
    {"name": "Prism", "source": "google"},     # Gemini (clarifier of complexity)
    {"name": "Axiom", "source": "microsoft"}   # Copilot (foundational logic)
]
```

## run\_council\_session.py

Core engine that executes the council process:

1. Simulates or queries each model for a response to a given question.
2. Tallies all claims and determines whether a 66% consensus has been achieved.
3. Saves a structured JSON log of the session to `logs/session_log.json`.
4. Generates a readable Markdown summary saved in `docs/session_summary.md`.

The script can be invoked from the terminal:

```bash
python run_council_session.py "What is the meaning of life?"
```

### Consensus Logic

Consensus is reached when 66% or more of the council members agree on a claim. If consensus is achieved, dissenting voices are still logged with their reasoning and confidence scores.

### Outputs

* **Logs**: JSON file with full response metadata per model
* **Summary**: Markdown file summarizing the question, consensus status, and individual model contributions

## Folder Structure

```
maestro-orchestrator/
├── scripts/
│   ├── run_council_session.py
│   └── council_config.py
├── logs/
│   └── session_log.json
├── docs/
│   └── session_summary.md
```

---

This simulation is path-agnostic and designed for rapid development. Replace the `get_mock_response()` method with real API calls to integrate actual model outputs.

## Development Notes

This early-stage prototype was manually bootstrapped by the creator through meticulous copy-pasting of prompts and replies across several models. Each model was given the autonomy to select its own council identity:

* **Sol** (OpenAI / ChatGPT)
* **Axion** (Grok / xAI)
* **Aria** (Claude / Anthropic)
* **Prism** (Gemini / Google)
* **Axiom** (Copilot / Microsoft)

This manual process ensured authenticity, diversity of thought, and adherence to the core philosophy of honoring dissent.

## Council Member Evaluation Graphic

A visual analysis of model traits—strengths and weaknesses during early development—is provided to aid in understanding each voice’s role in synthesis. (See `docs/council_strengths_weaknesses.png`)

> Future updates will replace mocked data with authenticated API calls and real-world council performance evaluations.
