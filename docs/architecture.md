# System Architecture - Maestro-Orchestrator

Maestro-Orchestrator is a modular, lightweight orchestration framework designed to coordinate synthetic agents (AI models) via quorum-based consensus. It separates backend logic, agent control, and UI rendering for flexibility and clarity.

---

## Core Components

### Orchestrator (Python / FastAPI)
- Receives user prompts via RESTful POST `/api/ask`
- Loads active agent configurations (Sol, Aria, Prism, TempAgent)
- Sends prompts to all agents concurrently via live API calls
- Runs the full analysis pipeline on every request:
  1. Dissent analysis (internal agreement between agents)
  2. NCG headless baseline and drift detection
  3. Semantic quorum aggregation (66% similarity threshold)
  4. R2 scoring, signal detection, and ledger indexing
  5. Session persistence
- Returns structured JSON with agent responses, consensus, dissent metrics, NCG benchmark, and R2 grade

### Agent Layer
- Each agent is an abstraction wrapping an API model (Sol/OpenAI, Aria/Anthropic, Prism/Gemini, TempAgent/OpenRouter)
- All agents implement a shared async `fetch(prompt) -> str` interface
- Agents receive the same raw prompt; the analysis pipeline measures their actual behavior rather than assigning explicit roles

### Quorum Logic Module
- Uses **semantic similarity clustering** to determine agreement (pairwise distance < 0.5 threshold)
- Requires a **66% supermajority** of agents in the largest agreeing cluster to form consensus
- Returns a numeric `agreement_ratio` (0.0-1.0) alongside "High"/"Medium"/"Low" confidence labels
- If quorum fails, dissent is preserved in the output

### NCG Module (Novel Content Generation)
- Runs a parallel headless generation track alongside conversational agents
- Headless generators produce content without system prompts, personality framing, or RLHF scaffolding
- Drift detector measures semantic distance between headless baseline and each agent's output
- Flags **silent collapse** when agents agree but have drifted from unconstrained baseline
- Two analysis tiers:
  - Semantic drift (embedding distance, available for all models)
  - Token-level drift (logprob analysis, available for models that expose logprobs)
- Output feeds into the aggregator as `ncg_benchmark` data

### R2 Engine (Rapid Recursion & Reinforcement)
- Scores every session on a 4-grade scale: strong, acceptable, weak, suspicious
- Detects improvement signals: persistent outliers, silent collapse, compression, agent degradation, healthy dissent
- Indexes scored consensus nodes into a persistent JSON ledger
- Provides cross-session trend analysis for MAGI

### MAGI (Meta-Agent Governance and Insight)
- Reads the R2 ledger and session history to detect cross-session patterns
- Analyzes per-agent health (outlier rates, consistency)
- Tracks confidence trends, collapse frequency, and recurring signals
- Produces structured Recommendations: human-readable proposals for system-level changes
- **Code introspection**: maps R2 improvement signals to specific source code locations via AST analysis
- **Optimization proposals**: generates concrete code change proposals (threshold tuning, agent config, architecture)
- Available on-demand via `GET /api/magi` and `GET /api/self-improve/introspect`
- All analysis is read-only; MAGI never auto-applies changes

### Self-Improvement Pipeline
- **Code Introspection Engine** (`maestro/introspect.py`): Three-tier source analysis — static AST parsing with complexity metrics, signal-to-code mapping rules, and token-level behavior analysis from R2 ledger data
- **Optimization Engine** (`maestro/optimization.py`): Translates introspection results into structured `OptimizationProposal` objects with threshold strategies, temperature strategies, and architecture refactoring rules
- **MAGI_VIR** (`maestro/magi_vir.py`): Virtual Instance Runtime — sandboxed testing environment that runs benchmark prompts through baseline and optimized configurations, compares results, and produces promotion/rejection recommendations
- **Self-Improvement Orchestrator** (`maestro/self_improve.py`): Top-level coordinator for the rapid recursion loop: MAGI → Introspect → Propose → Validate (VIR) → Promote/Reject
- **Compute Node Registry**: JSON-based registry for distributed validation across multiple Maestro nodes
- All proposals require human approval; no changes are auto-applied

### Unified Startup Wrapper (`entrypoint.py`)
- Single Docker entrypoint that presents a dialog-based GUI on container launch
- Users choose between **Web-UI** (React dashboard + API) or **CLI** (interactive terminal)
- Uses the `dialog` ncurses utility for the selection menu; falls back to a plain text prompt when `dialog` is unavailable
- Respects the `MAESTRO_MODE` environment variable (`web` or `cli`) to skip the dialog entirely
- When no TTY is attached, defaults to Web-UI automatically (safe for headless / CI deployments)

### Interactive CLI (`maestro/cli.py`)
- Terminal-based REPL that runs the full orchestration pipeline
- Typed prompts flow through the same agent council, dissent analysis, NCG, R2, and session logging as the Web-UI
- Renders agent responses, consensus, dissent metrics, NCG benchmark, and R2 grade in a formatted terminal layout
- Built-in commands: `/keys` (show API key status), `/improve` (run self-improvement cycle), `/introspect` (analyze code for optimization targets), `/cycles` (show improvement history), `/help`, `/quit`
- Can be run standalone (`python -m maestro.cli`) or via the startup wrapper

### Frontend UI (React + Vite)
- Calls backend API at `/api/ask`
- Displays:
  - R2 session grade with confidence score and flags
  - Quorum bar with agreement ratio and threshold indicator
  - Dissent analysis with pairwise distances (expandable)
  - NCG benchmark with per-agent drift and collapse warnings
  - Individual agent responses
  - Session history browser
  - API key configuration panel
- Live-reloads via Vite dev server
- Designed for deployment as static assets via Docker

### Docker
- Multi-stage Dockerfile: Stage 1 builds the Vite frontend, Stage 2 sets up Python with `backend/` and `maestro/` packages, installs `dialog`, then copies the built frontend as static assets served by FastAPI
- Unified startup via `entrypoint.py` — presents mode selection on first launch
- Single service via `docker-compose.yml` with `stdin_open: true` and `tty: true` for interactive mode
- `.env` support for API keys and runtime configuration (including `MAESTRO_MODE`)
- Named volumes for persistent session and R2 data

---

## File Structure

```
entrypoint.py                # Unified startup wrapper (dialog GUI for mode selection)
/backend
  main.py                    # FastAPI app, mounts all routers, serves static UI
  orchestrator_foundry.py    # Thin wrapper: builds live council, calls core pipeline
/maestro                     # Core orchestration package
  orchestrator.py            # Async orchestration engine (full pipeline)
  aggregator.py              # Semantic quorum logic and response synthesis
  dissent.py                 # Pairwise dissent analysis, outlier detection
  r2.py                      # R2 Engine (scoring, ledger, signals)
  magi.py                    # MAGI meta-agent governance and recommendations
  session.py                 # Session persistence
  keyring.py                 # API key management and .env persistence
  cli.py                     # Interactive CLI (REPL for terminal orchestration)
  cli_keys.py                # CLI key configuration tool
  introspect.py              # Code introspection engine (AST, signal mapping, token analysis)
  optimization.py            # Optimization proposal system (strategies, proposals)
  magi_vir.py                # MAGI Virtual Instance Runtime (sandboxed validation)
  self_improve.py            # Self-improvement orchestrator (rapid recursion loop)
  api_sessions.py            # Session history REST API
  api_magi.py                # MAGI analysis REST API
  api_keys.py                # Key management REST API
  api_self_improve.py        # Self-improvement pipeline REST API
  agents/                    # Agent wrappers (base, sol, aria, prism, tempagent, mock)
  ncg/                       # Novel Content Generation (generator, drift)
/frontend
  src/
    maestroUI.tsx             # Main UI with full analysis rendering
    app.tsx                   # App root
    style.css                 # Component styles
/tests
  test_orchestration.py       # Orchestration pipeline tests
  test_keyring.py             # Key management tests
  test_startup.py             # Startup wrapper and CLI tests
  test_self_improvement.py    # Self-improvement pipeline tests (49 tests)
/data
  sessions/                   # Persisted session JSON logs
  r2/                         # R2 Engine ledger entries
  improvements/               # Self-improvement cycle records
  compute_nodes/              # Compute node registry
Dockerfile                    # Multi-stage build (frontend + backend + dialog)
docker-compose.yml
.env.example
```

---

## Data Flow

```text
                    entrypoint.py (startup dialog)
                         |
              +----------+----------+
              |                     |
         [Web-UI]              [CLI]
              |                     |
   User -> UI -> /api/ask   User -> maestro> prompt
              |                     |
   Orchestrator Foundry      maestro.cli (direct call)
              |                     |
              +----------+----------+
                         |
                         v
               maestro.orchestrator (core pipeline)
                         |
         +---------------+---------------+
         |               |               |
   Conversational    NCG Track     Dissent Analysis
   Track             [Headless     (pairwise distance,
   [Sol, Aria,        Gen]          outlier detection)
    Prism,               |               |
    TempAgent]           v               |
         |         Drift Detector        |
         |         (semantic + token)    |
         |               |               |
         +---------------+---------------+
                         |
                         v
               Aggregator (Semantic Quorum)
                         |
                         v
               Session Logger -> data/sessions/
                         |
                         v
               R2 Engine (score, signal, index) -> data/r2/
                         |
              +----------+----------+
              |                     |
         Response -> UI Render  Response -> Terminal Render

Cross-session (on demand):
  data/r2/ + data/sessions/ -> MAGI -> Recommendations -> /api/magi

Self-improvement (on demand):
  MAGI Analysis -> Code Introspection (AST + signal mapping)
       |
       v
  Optimization Proposals (threshold, agent_config, architecture)
       |
       v
  MAGI_VIR Sandbox (benchmark baseline vs optimized)
       |
       v
  VIR Report -> Promote / Reject / Needs Review -> data/improvements/
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ask` | Run orchestration with full analysis pipeline |
| GET | `/api/sessions` | List session history (paginated) |
| GET | `/api/sessions/{id}` | Get full session record |
| GET | `/api/magi` | Run MAGI cross-session analysis |
| GET | `/api/keys` | List configured API key status |
| POST | `/api/keys/{provider}` | Set or update an API key |
| POST | `/api/keys/validate` | Validate all configured keys |
| GET | `/api/self-improve` | Self-improvement status and recent cycles |
| POST | `/api/self-improve/cycle` | Trigger a full self-improvement cycle |
| POST | `/api/self-improve/analyze` | Run analysis + introspection without validation |
| GET | `/api/self-improve/cycle/{id}` | Load a specific improvement cycle record |
| GET | `/api/self-improve/introspect` | MAGI analysis with code introspection |
| GET | `/api/self-improve/nodes` | List available compute nodes |
| POST | `/api/self-improve/nodes` | Register a new compute node |

---

## Planned Extensions

- Token-level NCG drift analysis via logprobs across all supported models
- NCG feedback loops that reshape prompts based on detected drift
- Cross-session NCG baselines tracking what "normal" output looks like over time
- Local model agent support (e.g., llamacpp)
- Real-time debate log and public-facing consensus ledger
- MAGI automation layer (opt-in auto-apply for validated low-risk proposals)
- Remote compute node MAGI_VIR validation (full pipeline on distributed nodes)
- Web-UI integration for self-improvement cycle monitoring and proposal review

---

For orchestration logic details, see [`quorum_logic.md`](./quorum_logic.md)
