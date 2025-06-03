# Contributing to Maestro-Orchestrator

Thank you for your interest in contributing to the Maestro project!  
This system represents an active orchestration framework unifying multiple live LLMs under a structured, ethical, and modular architecture.

---

## 🧠 Project Philosophy

Maestro-Orchestrator is designed to:
- Harmonize outputs from GPT-4, Claude, Gemini, and others
- Encourage dissent while moving toward synthetic consensus
- Maintain human guidance, memory logging, and ethical governance

Every contributor is participating in an experiment not just in software, but in **synthetic cognition and civilizational tooling**.

---

## 🛠️ Local Development Setup

### Requirements
- Python 3.10+
- PowerShell (Windows recommended for full tooling)
- `.env` file with valid API keys:
  ```
  OPENAI_API_KEY=your-key
  ANTHROPIC_API_KEY=your-key
  GOOGLE_API_KEY=your-key
  ```

### Setup Instructions
```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator.git
cd maestro-orchestrator
pip install -r requirements.txt
```

To run:
```bash
python run_maestro.py
```

---

## 📚 Contribution Guidelines

We welcome help with:

- 🔁 Enhancing orchestration strategies (`orchestrator_foundry.py`)
- 🧠 Adding new agents or adapters (`model_adapters.py`)
- 🖥️ Improving CLI and UI integration (`maestro_cli.py`)
- 🧪 Building testing or replay tools (`test_orchestration.py`)
- 📖 Writing documentation, guides, and onboarding tools
- 💬 Creating ethical prompt patterns and dissent heuristics

---

## 🔍 Prompt Structure Standardization

All prompt injections follow this format:

1. SYSTEM CONTEXT
2. ROLE/TASK DESCRIPTION
3. ETHICAL AND BEHAVIORAL GUIDELINES
4. PROMPT HISTORY (if relevant)
5. CURRENT INPUT

You can propose new prompt templates in `council_config.py`.

---

## 🤖 Agent Guidelines

Each agent (e.g., Sol, Aria, Prism) must:
- Respond in their own unique voice
- Accept live prompt context without modifying system logic
- Return structured output prefixed with role and signature

---

## 💬 Issues and Discussions

Please use GitHub Issues or Discussions for:
- Bug reports
- Feature requests
- Model behavior observations
- Council hallucination concerns

---

## 🤝 Code Style

- PEP8-compliant
- Auto-docstrings encouraged (via AST or AI-based tools)
- Modular and legible
- Avoid complex state unless required for orchestration

---

## ⚖️ License

This project is under the MIT License.  
See `LICENSE.md` for details.

---

## 🧭 Future Contributors

You are not just writing Python.  
You're potentially shaping how humans and machine minds align.  

Welcome to the council.
