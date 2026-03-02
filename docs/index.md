# Maestro-Orchestrator Documentation

Welcome to the official documentation hub for **Maestro-Orchestrator**, an ensemble AI framework that coordinates multiple language models, facilitates structured dissent, and iteratively refines truth through consensus mechanisms.

This system is built for researchers, engineers, and visionaries working at the edge of synthetic intelligence, governance, and collective cognition.

---

## Modules Overview

### [Agents](agents.md)
Modular definitions of participating language model agents (Sol, Aria, Prism, TempAgent). Describes how each agent is invoked, structured, and rotated in a session.

### [Livefire CLI](livefire.md)
The command-line orchestrator that runs a real-time consensus loop with multiple agents, logs session data, and evaluates agreement thresholds.

### [Dissent Analysis](architecture.md)
Pairwise semantic distance between agents, outlier detection, and cross-session trend tracking. Produces the `internal_agreement` score that feeds into NCG's silent collapse detector.

### [NCG: Novel Content Generation](ncg.md)
Parallel diversity benchmark track. Headless models generate content without conversational framing, serving as a control group against which agent outputs are measured for drift. Catches silent collapse — when all agents agree but their consensus reflects RLHF conformity rather than genuine reasoning.

### [R2 Engine](r2-engine.md)
Session scoring, consensus ledger indexing, and structured improvement signal generation. Grades each session as strong/acceptable/weak/suspicious based on dissent, NCG drift, and quorum data. Produces signals for MAGI consumption.

### [Session Logging](logging.md)
Persistent JSON-based session records with unified data layer for cross-session analysis. Every orchestration session is captured as structured JSON in `data/sessions/`.

### [MAGI Meta-Agents](magi.md)
Forthcoming subsystem: autonomous agents that analyze session data and R2 ledger entries across multiple sessions to detect drift, reinforce stable patterns, and suggest improvements to quorum logic.

### [Roadmap](roadmap.md)
Tracks current development milestones, upcoming features, and long-term visionary goals.

---

## System Design Philosophy

Maestro-Orchestrator is built on three foundational principles:

- **Pluralism**: No single model governs truth; insights emerge through structured consensus.
- **Transparency**: Every session is logged. Every choice can be traced and evaluated.
- **Dissent as Signal**: Disagreement is not a failure mode—it is a data stream.

---

## Repository Structure

```
├── maestro/              # Core orchestration package
│   ├── orchestrator.py   # Multi-agent orchestration with NCG integration
│   ├── aggregator.py     # Response aggregation with drift benchmarks
│   ├── dissent.py        # Pairwise dissent analysis and outlier detection
│   ├── r2.py             # R2 Engine (scoring, ledger, signals)
│   ├── session.py        # Session persistence
│   ├── api_sessions.py   # Session history REST endpoints
│   ├── agents/           # Agent wrappers (base, sol, aria, prism, tempagent, mock)
│   └── ncg/              # Novel Content Generation module
│       ├── generator.py  # Headless generator implementations
│       └── drift.py      # Drift detector and collapse detection
├── backend/              # FastAPI backend
│   ├── main.py           # API entry point
│   ├── orchestrator_foundry.py  # Live agent council runner
│   └── orchestration_livefire.py  # CLI entrypoint
├── frontend/             # React/Vite frontend
│   └── src/              # TypeScript source
├── tests/                # Unit and integration tests
├── data/
│   ├── sessions/         # Persisted session JSON logs
│   └── r2/               # R2 Engine ledger entries
├── agents/               # Legacy standalone agent definitions
├── scripts/              # Utility and bootstrap scripts
├── docs/                 # Documentation hub
├── .env.example          # Environment variable structure
└── readme.md             # Top-level project overview
```

---

## Get Started

For setup and usage, refer to the [README](https://github.com/d3fq0n1/maestro-orchestrator).

To contribute, see [CONTRIBUTING.md](../CONTRIBUTING.md).

