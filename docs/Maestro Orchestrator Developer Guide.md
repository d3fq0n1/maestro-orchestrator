# Maestro Orchestrator Developer Guide

**Version**: v0.2
**Last Updated**: June 2025
**Maintainer**: [defcon](https://github.com/d3fq0n1)

---

## Overview

Maestro is an orchestration engine designed to coordinate multiple LLMs in a live deliberation format. It introduces structured dissent, rotating roles, historical logging, and agent-aware consensus mechanisms. Designed for researchers, developers, and experimenters interested in meta-intelligence and synthetic governance.

---

## Directory Structure

```text
maestro-orchestrator/
├── backend/
│   ├── main.py                          # FastAPI app (entry point)
│   ├── orchestrator_foundry.py          # Foundry orchestration logic
│   ├── orchestration_livefire.py        # Live CLI session runner
│   ├── orchestration_livefire_rotating.py # Variant with rotating agent roles
│   └── maestro_cli.py                   # CLI interface for local testing
├── maestro/                             # Core orchestration package
│   ├── orchestrator.py                  # Async orchestration engine
│   ├── aggregator.py                    # Consensus computation and result collation
│   ├── dissent.py                       # Pairwise dissent analysis
│   ├── r2.py                            # R2 Engine (scoring, ledger, signals)
│   ├── session.py                       # Session persistence
│   ├── agents/                          # Agent adapters (sol, aria, prism, tempagent)
│   │   └── base.py                      # Shared async agent interface
│   └── ncg/                             # Novel Content Generation module
│       ├── generator.py                 # Headless generators
│       └── drift.py                     # Drift detection
├── frontend/                            # React + Vite UI
│   └── src/maestroUI.tsx                # Main UI component
├── scripts/
│   ├── orchestrator.py                  # Batch orchestration with CSV input
│   ├── run_maestro.py                   # Quick launch script
│   ├── model_adapters.py                # Model adapter utilities
│   └── council_session/                 # Council session runner
│       └── council_config.py            # Quorum and role structure
├── data/
│   ├── sessions/                        # Persisted session JSON logs
│   └── r2/                              # R2 Engine ledger entries
├── .env.example                         # API key template
├── CONTRIBUTING.md / LICENSE.md         # Project metadata
```

---

## Setup

### Requirements

- Python 3.8+
- Create a `.env` file with:
  ```ini
  OPENAI_API_KEY=sk-...
  ANTHROPIC_API_KEY=sk-ant...
  GOOGLE_API_KEY=AIza...
  OPENROUTER_API_KEY=...
  ```

### Installation

```bash
git clone https://github.com/d3fq0n1/maestro-orchestrator
cd maestro-orchestrator
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

---

## Usage

### Backend API

```bash
uvicorn backend.main:app --reload --port 8000
```

### CLI

```bash
python backend/maestro_cli.py
```

### Full Orchestration

```bash
python scripts/run_maestro.py
```

### With Rotating Agent Roles

```bash
python backend/orchestration_livefire_rotating.py
```

---

## Workflow

1. **Initialization**: Models are instantiated using agent adapters in `maestro/agents/`.
2. **Prompt Handling**: Input prompt is distributed to agents via the shared async interface.
3. **Deliberation**: Each model generates responses; dissent and agreement are recorded.
4. **NCG Baseline**: A headless generator produces an unconstrained baseline for drift comparison.
5. **Consensus**: Aggregator module scores, filters, and returns unified output with NCG benchmark.
6. **R2 Scoring**: R2 Engine grades the session, detects improvement signals, and indexes to ledger.
7. **Logging**: Sessions are saved to `data/sessions/` as structured JSON.

---

## Customizing

### Agents

Add or modify agent adapters in `maestro/agents/`. Each agent extends `maestro/agents/base.py`.

### Dissent Thresholds

Modify quorum settings in `scripts/council_session/council_config.py`:
```python
MINIMUM_QUORUM = 3
CONSENSUS_THRESHOLD = 2/3
```

---

## Developer Notes

- Persistent logging enables replay and auditing.
- Modular design enables hot-swapping of models or consensus algorithms.
- Agent classes share an async `fetch(prompt)` interface defined in `maestro/agents/base.py`.

---

## Troubleshooting

- **API Errors**: Ensure `.env` is correctly configured and rate limits are respected.
- **Sync Scripts**: Use PowerShell scripts only on Windows (`combo-sync.ps1`).

---

## Future Work

- MAGI loop for meta-agent audits reading R2 ledger
- Token-level NCG drift analysis via logprobs
- NCG feedback loops reshaping prompts based on drift
- Streamlined onboarding wizard

---

## Contributions

See `CONTRIBUTING.md` for more.

---

## License

Custom open-use license (see `LICENSE.md`). Commercial use requires agreement (see `commercial_license.md`).
