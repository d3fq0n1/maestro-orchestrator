# Maestro Orchestrator Developer Guide

**Version**: v0.2  
**Last Updated**: June 2025  
**Maintainer**: [defcon](https://github.com/d3fq0n1)

---

## 🧠 Overview

Maestro is an orchestration engine designed to coordinate multiple LLMs in a live deliberation format. It introduces structured dissent, rotating roles, historical logging, and agent-aware consensus mechanisms. Designed for researchers, developers, and experimenters interested in meta-intelligence and synthetic governance.

---

## 📁 Directory Structure

```text
maestro/
├── orchestrator_foundry.py           # Primary entry point for orchestration logic
├── orchestration_livefire.py         # Live execution loop for session-based orchestration
├── orchestration_livefire_rotating.py# Variant with rotating agent roles
├── council_config.py                 # Defines quorum, role structure, and dissent thresholds
├── sol.py / aria.py / prism.py      # Agent adapters for GPT-4, Claude, Gemini
├── aggregator.py                     # Consensus computation and result collation
├── maestro_cli.py                    # CLI interface for local testing
├── run_maestro.py                    # Quick launch script
├── history_log.jsonl                 # Logged results of prior sessions
├── .env                              # API key configuration (excluded from version control)
├── CONTRIBUTING.md / LICENSE.md      # Project metadata
```

---

## ⚙️ Setup

### Requirements

- Python 3.10+
- Create a `.env` file with:
  ```ini
  OPENAI_API_KEY=sk-...
  ANTHROPIC_API_KEY=sk-ant...
  GOOGLE_API_KEY=AIza...
  ```

### Installation

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator
cd maestro-orchestrator
pip install -r requirements.txt
```

---

## 🚀 Usage

### CLI

```bash
python maestro_cli.py
```

### Full Orchestration

```bash
python run_maestro.py
```

### With Rotating Agent Roles

```bash
python orchestration_livefire_rotating.py
```

---

## 🔁 Workflow

1. **Initialization**: Models are instantiated using agent adapters.
2. **Prompt Handling**: Input prompt is distributed to agents via a consistent interface.
3. **Deliberation**: Each model generates responses; dissent and agreement are recorded.
4. **Consensus**: Aggregator module scores, filters, and optionally returns unified output.
5. **Logging**: Sessions are saved to `history_log.jsonl`.

---

## 🧩 Customizing

### Agents

Add or modify adapters in:
- `sol.py`, `aria.py`, `prism.py`
- Extend via `model_adapters.py`

### Dissent Thresholds

Modify:
```python
MINIMUM_QUORUM = 3
CONSENSUS_THRESHOLD = 2/3
```
in `council_config.py`.

---

## 📚 Developer Notes

- Functions and classes are now fully documented with auto-generated docstrings.
- Persistent logging enables replay and auditing.
- Modular design enables hot-swapping of models or consensus algorithms.

---

## 🛠️ Troubleshooting

- **API Errors**: Ensure `.env` is correctly configured and rate limits are respected.
- **Broken UI**: See last known regression in `run_maestro()` linkage.
- **Sync Scripts**: Use PowerShell scripts only on Windows (`combo-sync.ps1`).

---

## 📈 Future Work

- Full web UI (React/Flask planned)
- Auto-consensus confidence scoring
- Integration with MAGI auditing layer
- Streamlined onboarding wizard

---

## 🤝 Contributions

See `CONTRIBUTING.md` for more.

---

## 🧾 License

MIT License (see `LICENSE.md`)

