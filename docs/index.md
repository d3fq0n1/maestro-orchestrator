# Maestro-Orchestrator Documentation

Welcome to the official documentation hub for **Maestro-Orchestrator**, an ensemble AI framework that coordinates multiple language models, facilitates structured dissent, and iteratively refines truth through consensus mechanisms.

This system is built for researchers, engineers, and visionaries working at the edge of synthetic intelligence, governance, and collective cognition.

---

## Modules Overview

### [Agents](agents.md)
Modular definitions of participating language model agents (GPT-4o, Claude Sonnet 4.6, Gemini 2.5 Flash, Llama 3.3 70B, ShardNet). Describes how each agent is invoked, structured, and rotated in a session.

### [Deliberation Engine](deliberation.md)
Cross-agent response sharing. After initial parallel collection, each agent reads its peers' answers and produces a refined reply before any analysis runs. Configurable rounds, default on, non-fatal. Full API and SSE event documentation.

### [System Architecture](architecture.md)
Modular architecture overview covering the orchestration pipeline, agent layer, quorum logic, NCG, R2 Engine, MAGI governance, self-improvement pipeline, CLI, frontend UI, and Docker deployment.

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

### [Self-Improvement Pipeline](self-improvement-pipeline.md)
Complete rapid recursion loop: MAGI analysis, code introspection (AST + signal mapping), optimization proposals, MAGI_VIR sandboxed validation, and promote/reject lifecycle. All proposals require human approval.

### [Storage Network](storage-network.md)
Proof-of-storage distributed inference layer. Storage nodes hold weight shards and prove residency through cryptographic challenges. The ShardAgent constructs inference pipelines across nodes. Reputation scoring integrates with R2 for trust management.

### [Mod Manager](mod-manager.md)
Modular plugin architecture with full lifecycle management (discover, validate, load, enable, disable, unload, hot-reload). 8 pipeline hook points, event bus for inter-plugin communication, weight state snapshots for configuration management.

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
  deliberation.py         # Deliberation engine (cross-agent response sharing)
  aggregator.py           # Semantic quorum logic and response synthesis
  dissent.py              # Pairwise dissent analysis, outlier detection
  r2.py                   # R2 Engine (scoring, ledger, signals)
  magi.py                 # MAGI meta-agent governance and recommendations
  session.py              # Session persistence
  keyring.py              # API key management
  cli.py                  # Interactive CLI (REPL)
  introspect.py           # Code introspection engine (AST, signal mapping)
  optimization.py         # Optimization proposal system
  magi_vir.py             # Virtual Instance Runtime (sandboxed validation)
  self_improve.py         # Self-improvement orchestrator
  api_sessions.py         # Session history REST API
  api_magi.py             # MAGI analysis REST API
  api_keys.py             # Key management REST API
  api_self_improve.py     # Self-improvement pipeline REST API
  api_storage.py          # Storage network REST API
  api_plugins.py          # Plugin system REST API
  storage_proof.py        # Storage proof engine
  shard_registry.py       # Storage node registry
  node_server.py          # Standalone node server (separate process)
  plugins/                # Plugin system (base protocol, mod manager)
  agents/                 # Agent wrappers (base, sol, aria, prism, tempagent, shard, mock)
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
  improvements/           # Self-improvement cycle records
  compute_nodes/          # Compute node registry
  storage_nodes/          # Storage node registry
  storage_proofs/         # Proof challenge records and reputation data
  plugins/                # Plugin system (installed, disabled, snapshots)
docs/                     # Documentation hub
Dockerfile                # Multi-stage Docker build
docker-compose.yml        # Docker Compose orchestration
.env.example              # Environment variable template
```

---

## Additional Documentation

- [Architecture](architecture.md)
- [Deliberation Engine](deliberation.md)
- [Storage Network](storage-network.md)
- [Mod Manager](mod-manager.md)
- [Self-Improvement Pipeline](self-improvement-pipeline.md)
- [Setup & Deployment](deployment.md)
- [Troubleshooting](troubleshooting.md)
- [UI Guide](ui-guide.md)
- [Roadmap](roadmap.md)
- [Vision](vision.md)

---

## Get Started

For setup and usage, refer to the [README](https://github.com/d3fq0n1/maestro-orchestrator).

To contribute, see [CONTRIBUTING.md](../CONTRIBUTING.md).
