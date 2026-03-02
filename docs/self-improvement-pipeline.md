# Self-Improvement Pipeline

The self-improvement pipeline is Maestro-Orchestrator's mechanism for identifying and validating optimizations to its own code. It bridges the gap between MAGI's cross-session pattern detection and concrete, testable code changes.

This is the "rapid recursion" described in the whitepaper: the system observes its own behavior, identifies where it can improve, tests those improvements in isolation, and proposes the changes for promotion.

---

## Overview

The pipeline runs in six phases:

```
1. MAGI Analysis     — Cross-session pattern detection from R2 ledger
2. Code Introspection — Map signals to specific source code locations
3. Proposal Generation — Produce concrete optimization proposals
4. VIR Validation     — Test proposals in isolated sandbox
5. Promote/Reject     — Record results and update proposal status
6. Human Review       — Approved proposals applied to production
```

Each phase produces structured output that feeds into the next. The pipeline is stateless between cycles — all persistence is handled by the underlying components (R2 ledger, session logger, improvement log).

---

## Modules

### Code Introspection Engine (`maestro/introspect.py`)

The introspection engine gives MAGI the ability to analyze Maestro's own source code. It operates in three tiers:

**Tier 1: Static Source Analysis**
- Discovers all Python files in the `maestro/` package
- Parses each file into an AST (Abstract Syntax Tree)
- Computes cyclomatic complexity for every function and class
- Identifies complexity hotspots (functions scoring above 0.3)

**Tier 2: Signal-to-Code Mapping**
- Maps R2 improvement signal types to specific code locations using `_SIGNAL_CODE_MAP` rules
- Each rule connects a signal type (e.g., `suspicious_consensus`) to target modules, functions, and parameters
- Resolves dotted module names to file paths and uses AST search to find exact line numbers and current values

| Signal Type | Target Modules | Optimization Category |
|---|---|---|
| `persistent_outlier` | `maestro.agents`, `maestro.dissent` | agent_config, threshold |
| `suspicious_consensus` | `maestro.orchestrator`, `maestro.ncg.drift`, `maestro.aggregator` | pipeline, threshold |
| `compression` | `maestro.ncg.generator`, `maestro.agents` | prompt, agent_config |
| `agent_degradation` | `maestro.agents`, `maestro.orchestrator` | agent_config, pipeline |
| `drift_trend` | `maestro.ncg.drift`, `maestro.ncg.generator` | architecture, token_tuning |

**Tier 3: Token-Level Behavior Analysis**
- Analyzes R2 ledger entries for token-level patterns (when logprob data is available)
- Detects high token uncertainty ratios that suggest prompt restructuring
- Identifies compression signatures (high agreement + low confidence)
- Produces `CodeTarget` objects for token-level optimizations

### Optimization Engine (`maestro/optimization.py`)

Translates introspection results into actionable `OptimizationProposal` objects. Encodes strategy rules that map observed patterns to specific changes.

**Proposal Categories:**
- `threshold` — Adjust numeric thresholds (quorum, similarity, drift)
- `agent_config` — Model versions, temperature, timeout adjustments
- `prompt` — Restructure prompts for better token efficiency
- `pipeline` — Adjust sequence/parallelism of analysis steps
- `token_tuning` — Adjust generation parameters based on logprob data
- `architecture` — Decompose complex functions (only when MAGI flags issues)

**Threshold Strategies:**

| Target | Signal | Direction | Step | Bounds |
|---|---|---|---|---|
| `QUORUM_THRESHOLD` | `suspicious_consensus` | raise | 0.05 | 0.5–0.9 |
| `QUORUM_THRESHOLD` | `agent_degradation` | lower | 0.05 | 0.5–0.9 |
| `SIMILARITY_THRESHOLD` | `persistent_outlier` | raise | 0.05 | 0.3–0.8 |
| `SIMILARITY_THRESHOLD` | `suspicious_consensus` | lower | 0.05 | 0.3–0.8 |

**Temperature Strategies:**

| Signal | Direction | Step | Bounds |
|---|---|---|---|
| `suspicious_consensus` | raise | 0.1 | 0.3–1.5 |
| `compression` | raise | 0.1 | 0.3–1.5 |
| `agent_degradation` | lower | 0.05 | 0.3–1.5 |

**R2 Trend Escalation:** When R2 detects declining confidence trends, medium-priority proposals are escalated to high priority.

Each proposal has a lifecycle: `proposed` → `testing` → `validated`/`rejected` → `promoted`/`rolled_back`.

### MAGI_VIR — Virtual Instance Runtime (`maestro/magi_vir.py`)

The sandboxed testing environment for optimization proposals. Provides an airgap between "proposed" and "promoted."

**Isolation Tiers:**
1. **Local sandbox** — Runs in an ephemeral temp directory with modified config/parameters. Fast, cheap, good for threshold tuning and config changes.
2. **Compute node** — Runs a full Maestro instance on a remote node with proposed code changes. Used for architecture changes and full pipeline modifications.

**Validation Flow:**
1. Create isolated sandbox with ephemeral data directories
2. Run benchmark prompts through baseline configuration
3. Apply proposed changes (threshold overrides, config overrides)
4. Run the same benchmarks through optimized configuration
5. Compare results: confidence delta, drift delta, grade improvement, collapse fixes
6. Produce VIRReport with promotion recommendation

**Recommendation Logic:**
- `promote` — Overall improvement > 0.05
- `reject` — Overall improvement < -0.05
- `needs_review` — Marginal change (between -0.05 and 0.05)

**Benchmark Prompts:** Default set of 5 prompts known to exercise key behaviors (consciousness, ethics, quantum computing, AGI risks, philosophy). Configurable per validation run.

### Self-Improvement Orchestrator (`maestro/self_improve.py`)

Top-level coordinator for the complete rapid recursion loop.

```python
from maestro.self_improve import SelfImprovementEngine

engine = SelfImprovementEngine(
    compute_node="local",           # or a registered node ID
    benchmark_prompts=["..."],      # custom benchmarks (optional)
)

# Full cycle: MAGI → Introspect → Propose → Validate → Promote/Reject
cycle = engine.run_cycle()

# Analysis only (no VIR validation)
result = engine.run_analysis_only()

# History
cycles = engine.list_cycles(limit=10)
cycle_data = engine.load_cycle(cycle_id)
```

**ImprovementCycle fields:**
- `cycle_id`, `timestamp`, `phase`, `outcome`
- `magi_report` — Serialized MAGI analysis
- `introspection_summary` — Human-readable summary
- `proposals` — Serialized optimization proposals
- `vir_report` — Serialized VIR validation results
- `promoted_proposals` / `rejected_proposals` — Proposal IDs by outcome
- `compute_node`, `duration_ms`, `metadata`

**Outcomes:** `no_proposals`, `promoted`, `rejected`, `needs_review`, `failed`

### Compute Node Registry

JSON-based registry for distributed MAGI_VIR validation.

```python
from maestro.magi_vir import ComputeNodeRegistry, ComputeNode

registry = ComputeNodeRegistry()
registry.register(ComputeNode(
    node_id="gpu-node-1",
    host="192.168.1.100",
    port=8000,
    capabilities=["local_sandbox", "full_pipeline"],
))

node = registry.select_node(required_capabilities=["full_pipeline"])
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/self-improve` | Status and recent improvement cycles |
| POST | `/api/self-improve/cycle` | Trigger a full self-improvement cycle |
| POST | `/api/self-improve/analyze` | Run analysis + introspection (no validation) |
| GET | `/api/self-improve/cycle/{id}` | Load a specific cycle record |
| GET | `/api/self-improve/introspect` | MAGI analysis with code introspection |
| GET | `/api/self-improve/nodes` | List available compute nodes |
| POST | `/api/self-improve/nodes` | Register a new compute node |

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `/improve` | Run a full self-improvement cycle |
| `/introspect` | Run analysis + introspection (no validation) |
| `/cycles` | Show recent improvement cycles |

---

## Data Storage

- `data/improvements/cycle_{id}.json` — Complete cycle records
- `data/compute_nodes/{id}.json` — Registered compute nodes
- MAGI_VIR sandbox directories are ephemeral (created in `/tmp/magi_vir_*`, cleaned up after validation)

---

## Ethical Design

The self-improvement pipeline follows Maestro's core ethical principles:

1. **No auto-apply**: Optimization proposals are never automatically applied to the running system. All validated proposals require human review before promotion.
2. **Isolated validation**: MAGI_VIR operates in a sandboxed environment with ephemeral data. It never touches production session data or the R2 ledger.
3. **Bounded changes**: Threshold strategies have hard min/max bounds to prevent runaway parameter changes (e.g., quorum threshold bounded to 0.5–0.9).
4. **Evidence-based**: Every proposal includes the R2 signals that triggered it, the introspection rationale, and the VIR validation results. Nothing is proposed without evidence.
5. **Reproducible**: Given the same R2 ledger and session data, the pipeline produces the same proposals.

---

## Test Coverage

The pipeline has 49 tests across 7 test classes in `tests/test_self_improvement.py`:

- `TestCodeIntrospector` (11 tests) — Source analysis, signal mapping, token patterns, deduplication
- `TestOptimizationEngine` (8 tests) — Threshold/agent/architecture proposals, deduplication, bounds
- `TestMagiVIR` (8 tests) — VIR validation, comparison fields, sandbox cleanup, grade ranking
- `TestComputeNodeRegistry` (7 tests) — Register, list, select, unregister, status
- `TestSelfImprovementEngine` (8 tests) — Empty/populated cycles, persistence, analysis-only
- `TestMagiCodeOptimization` (5 tests) — MAGI introspection integration
- `TestSelfImprovementIntegration` (2 tests) — Full pipeline collapse scenario and healthy system

---

## See Also

- [`magi.md`](./magi.md) — MAGI meta-agent governance
- [`r2-engine.md`](./r2-engine.md) — R2 Engine (signals that drive the pipeline)
- [`architecture.md`](./architecture.md) — System overview
