# Maestro-Orchestrator Documentation

Welcome to the official documentation hub for **Maestro-Orchestrator**, an ensemble AI framework that coordinates multiple language models, facilitates structured dissent, and iteratively refines truth through consensus mechanisms.

This system is built for researchers, engineers, and visionaries working at the edge of synthetic intelligence, governance, and collective cognition.

---

## Modules Overview

### [Agents](agents.md)
Modular definitions of participating language model agents (Sol, Aria, Prism, TempAgent). Describes how each agent is invoked, structured, and rotated in a session.

### [Livefire Orchestration](livefire.md)
The live orchestration pipeline that runs real-time API calls through the full analysis stack: dissent, NCG drift, semantic quorum, R2 scoring, and session persistence.

### [Dissent Analysis](architecture.md)
Pairwise semantic distance between agents, outlier detection, and cross-session trend tracking. Produces the `internal_agreement` score that feeds into NCG's silent collapse detector.

### [NCG: Novel Content Generation](ncg.md)
Parallel diversity benchmark track. Headless models generate content without conversational framing, serving as a control group against which agent outputs are measured for drift. Catches silent collapse -- when all agents agree but their consensus reflects RLHF conformity rather than genuine reasoning.

### [R2 Engine](r2-engine.md)
Session scoring, consensus ledger indexing, and structured improvement signal generation. Grades each session as strong/acceptable/weak/suspicious based on dissent, NCG drift, and quorum data. Produces signals for MAGI consumption.

### [MAGI Meta-Agent Governance](magi.md)
Cross-session pattern analysis that reads the R2 ledger and session history to detect drift, track agent health, and produce structured recommendations. Available on-demand via `GET /api/magi`. All analysis is read-only.

### [Session Logging](logging.md)
Persistent JSON-based session records with unified data layer for cross-session analysis. Every orchestration session is captured as structured JSON in `data/sessions/`.

### [Quorum Logic](quorum_logic.md)
Semantic similarity clustering for consensus detection with 66% supermajority threshold.

---

## System Design Philosophy

Maestro-Orchestrator is built on three foundational principles:

- **Pluralism**: No single model governs truth; insights emerge through structured consensus.
- **Transparency**: Every session is logged. Every choice can be traced and evaluated.
- **Dissent as Signal**: Disagreement is not a failure mode -- it is a data stream.

---

## Repository Structure

```
maestro/                  # Core orchestration package
  orchestrator.py         # Async orchestration engine (full pipeline)
  aggregator.py           # Semantic quorum logic and response synthesis
  dissent.py              # Pairwise dissent analysis, outlier detection
  r2.py                   # R2 Engine (scoring, ledger, signals)
  magi.py                 # MAGI meta-agent governance and recommendations
  session.py              # Session persistence
  keyring.py              # API key management
  api_sessions.py         # Session history REST API
  api_magi.py             # MAGI analysis REST API
  api_keys.py             # Key management REST API
  agents/                 # Agent wrappers (base, sol, aria, prism, tempagent, mock)
  ncg/                    # Novel Content Generation (generator, drift)
backend/                  # FastAPI backend
  main.py                 # API entry point, static UI mount
  orchestrator_foundry.py # Live agent council builder
frontend/                 # React/Vite frontend
  src/
    maestroUI.tsx          # Main UI with full analysis rendering
tests/                    # Unit and integration tests
data/
  sessions/               # Persisted session JSON logs
  r2/                     # R2 Engine ledger entries
docs/                     # Documentation hub
Dockerfile                # Multi-stage Docker build
docker-compose.yml        # Docker Compose orchestration
.env.example              # Environment variable template
```

---

## Additional Documentation

- [Architecture](architecture.md)
- [Deployment Guide](deployment.md)
- [Quickstart](quickstart.md)
- [Setup Guide](setup_guide.md)
- [Troubleshooting](troubleshooting.md)
- [UI Guide](ui-guide.md)

---

## Get Started

For setup and usage, refer to the [README](https://github.com/d3fq0n1/maestro-orchestrator).

To contribute, see [CONTRIBUTING.md](../CONTRIBUTING.md).
