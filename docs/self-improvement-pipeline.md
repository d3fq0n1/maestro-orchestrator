# Self-Improvement Pipeline

The self-improvement pipeline is Maestro-Orchestrator's mechanism for identifying and validating optimizations to its own code. It bridges the gap between MAGI's cross-session pattern detection and concrete, testable code changes.

This is the "rapid recursion" described in the whitepaper: the system observes its own behavior, identifies where it can improve, tests those improvements in isolation, and applies the changes — closing the loop.

---

## Overview

The pipeline runs in seven phases:

```
1. MAGI Analysis     — Cross-session pattern detection from R2 ledger
2. Code Introspection — Map signals to specific source code locations
3. Proposal Generation — Produce concrete optimization proposals
4. VIR Validation     — Test proposals in isolated sandbox
5. Promote/Reject     — Record results and update proposal status
6. Code Injection     — Apply validated proposals to the running system (opt-in)
7. Smoke Test        — Verify system health post-injection; auto-rollback on degradation
```

Phases 6–7 only run when auto-injection is enabled (`MAESTRO_AUTO_INJECT=true`). When disabled (the default), the pipeline stops at Phase 5 and records results for human review.

Each phase produces structured output that feeds into the next. The pipeline is stateless between cycles — all persistence is handled by the underlying components (R2 ledger, session logger, improvement log, rollback ledger).

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

# Full cycle: MAGI → Introspect → Propose → Validate → Promote/Reject → Inject
cycle = engine.run_cycle()

# Analysis only (no VIR validation)
result = engine.run_analysis_only()

# Manual injection of a previously validated cycle
result = engine.inject_cycle(cycle_id)

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
- `auto_injected` — Whether auto-injection was attempted
- `injections` — List of `InjectionResult` dicts (proposal_id, applied, injection_type, rollback_id, error)
- `rollback_triggered` — Whether the smoke test caused an automatic rollback
- `smoke_test_grade` — R2 grade from the post-injection smoke test
- `compute_node`, `duration_ms`, `metadata`

**Outcomes:** `no_proposals`, `promoted`, `rejected`, `needs_review`, `failed`

### Code Injection Engine (`maestro/applicator.py`)

Applies validated `OptimizationProposal` objects to the running system. Three injection modes:

1. **Runtime** (`parameter_update`) — Mutates module-level variables in the running process via `setattr`. No file writes, no restart needed. Used for threshold and temperature changes.
2. **Source patch** (`code_patch`, `architecture_refactor`) — Rewrites a value in a `.py` source file via AST transformation, then calls `importlib.reload()` so the change takes effect immediately and persists across restarts.
3. **Config overlay** (`config_change`, `prompt_rewrite`) — Writes to `data/runtime_config.json`, a JSON overlay that agents and the aggregator read at session start.

```python
from maestro.applicator import CodeInjector

injector = CodeInjector()

# Apply a single proposal
result = injector.apply(proposal, cycle_id="cycle-123")

# Apply a batch
results = injector.apply_batch(proposals, cycle_id="cycle-123")

# Dry run (validates through guard, no mutation)
result = injector.apply(proposal, dry_run=True)

# Rollback
injector.rollback(rollback_id)
injector.rollback_cycle(cycle_id)
```

**InjectionResult fields:** `proposal_id`, `applied`, `injection_type` (`"runtime"`, `"source_patch"`, `"config"`, `"skipped"`), `rollback_id`, `error`, `timestamp`

### Rollback System (`maestro/rollback.py`)

Every injection is paired with a snapshot of the original state. The `RollbackLog` is an append-only ledger persisted at `data/rollbacks/log.json`.

- **Runtime snapshots** record the previous in-memory value of the module variable.
- **Source snapshots** copy the original file content to `data/rollbacks/{rollback_id}.bak`.
- **Config snapshots** record the previous value in the config overlay.

```python
from maestro.rollback import RollbackLog

log = RollbackLog()

# Query
active = log.get_active()                     # all non-rolled-back entries
by_cycle = log.get_active_by_cycle(cycle_id)  # active entries for a cycle
history = log.list_all(limit=50)              # newest first

# Mark rolled back (actual restore done by CodeInjector)
log.mark_rolled_back(rollback_id)
```

**RollbackEntry fields:** `rollback_id`, `proposal_id`, `cycle_id`, `injection_type`, `module_name`, `target_name`, `original_value`, `new_value`, `file_path`, `backup_path`, `status` (`"applied"` | `"rolled_back"`), `timestamp`, `rolled_back_at`

### Injection Guard (`maestro/injection_guard.py`)

Safety rails for the injection system — the single chokepoint between "VIR says promote" and "the system actually changes."

- **Category whitelist**: Only `threshold`, `agent_config`, and `token_tuning` are injectable by default. `architecture` and `pipeline` are blocked.
- **Bounds enforcement**: Re-validates proposed values against strategy min/max bounds at injection time (never trusts the proposal alone).
- **Rate limiting**: Maximum 5 injections per hour (configurable). Prevents runaway self-modification.
- **Smoke test**: After injection, runs a benchmark prompt through the full pipeline. If the R2 grade drops below `acceptable`, the guard signals automatic rollback.
- **Opt-in gate**: The entire system is disabled by default. Enabled via `MAESTRO_AUTO_INJECT=true` environment variable or `GuardConfig.auto_inject_enabled`.

```python
from maestro.injection_guard import InjectionGuard

guard = InjectionGuard()

guard.is_enabled()                  # check opt-in gate
guard.is_injectable(proposal)       # (allowed, reason)
guard.check_bounds(proposal)        # verify min/max
guard.check_rate_limit()            # under the hourly cap?
guard.smoke_test()                  # (passed, grade)
```

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
| POST | `/api/self-improve/inject/{cycle_id}` | Manually inject proposals from a validated cycle |
| POST | `/api/self-improve/rollback/{rollback_id}` | Roll back a single injection |
| POST | `/api/self-improve/rollback-cycle/{cycle_id}` | Roll back all injections from a cycle |
| GET | `/api/self-improve/injections` | List all active (non-rolled-back) injections |
| GET | `/api/self-improve/rollbacks` | Full rollback history |

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `/improve` | Run a full self-improvement cycle |
| `/introspect` | Run analysis + introspection (no validation) |
| `/cycles` | Show recent improvement cycles |

---

## Data Storage

- `data/improvements/cycle_{id}.json` — Complete cycle records (including injection results)
- `data/compute_nodes/{id}.json` — Registered compute nodes
- `data/rollbacks/log.json` — Append-only injection rollback ledger
- `data/rollbacks/{rollback_id}.bak` — Source file backups for source-patch injections
- `data/runtime_config.json` — Runtime config overlay (created by config injections)
- MAGI_VIR sandbox directories are ephemeral (created in `/tmp/magi_vir_*`, cleaned up after validation)

---

## Ethical Design

The self-improvement pipeline follows Maestro's core ethical principles:

1. **Off by default**: Auto-injection is opt-in (`MAESTRO_AUTO_INJECT=true`). When disabled (the default), proposals are recorded but never applied. The system ships safe.
2. **Every change is reversible**: No injection without a snapshot. Rollback is always one call away — per injection or per entire cycle.
3. **Isolated validation**: MAGI_VIR operates in a sandboxed environment with ephemeral data. It never touches production session data or the R2 ledger.
4. **Bounded changes**: Threshold strategies have hard min/max bounds to prevent runaway parameter changes (e.g., quorum threshold bounded to 0.5–0.9). Bounds are enforced at injection time, not just proposal time.
5. **Evidence-based**: Every proposal includes the R2 signals that triggered it, the introspection rationale, and the VIR validation results. Every injection links back to the proposal and cycle that justified it.
6. **Fail-safe**: Post-injection smoke test runs a benchmark prompt through the full pipeline. If the R2 grade drops below `acceptable`, the entire batch is automatically rolled back.
7. **Rate-limited**: Maximum 5 injections per hour (configurable) to prevent runaway self-modification loops.
8. **Reproducible**: Given the same R2 ledger and session data, the pipeline produces the same proposals.
9. **Audit trail**: Full history of what was injected, when, why, and whether it was rolled back — all accessible via REST API.

---

## Test Coverage

The pipeline has **89 tests** across two test files:

### `tests/test_self_improvement.py` (49 tests)

- `TestCodeIntrospector` (11 tests) — Source analysis, signal mapping, token patterns, deduplication
- `TestOptimizationEngine` (8 tests) — Threshold/agent/architecture proposals, deduplication, bounds
- `TestMagiVIR` (8 tests) — VIR validation, comparison fields, sandbox cleanup, grade ranking
- `TestComputeNodeRegistry` (7 tests) — Register, list, select, unregister, status
- `TestSelfImprovementEngine` (8 tests) — Empty/populated cycles, persistence, analysis-only
- `TestMagiCodeOptimization` (5 tests) — MAGI introspection integration
- `TestSelfImprovementIntegration` (2 tests) — Full pipeline collapse scenario and healthy system

### `tests/test_code_injection.py` (40 tests)

- Code injection engine — runtime param injection, source patching, config overlay, dry run
- Rollback system — snapshot capture, single-entry rollback, batch rollback by cycle
- Injection guard — category whitelist, bounds checking, rate limiting, smoke test
- Integration — full pipeline from R2 ledger population through injection to rollback

---

## Mod Manager Integration (v0.6)

The injection guard's injectable categories have been extended in v0.6 to support the storage network and plugin system:

- **New injectable categories**: `storage`, `module`
- **New blocked categories**: `shard_eviction`

This means the self-improvement pipeline can now propose and apply optimizations to storage network thresholds and plugin configurations, subject to the same safety rails (bounds enforcement, rate limiting, smoke test, automatic rollback).

---

## See Also

- [`magi.md`](./magi.md) — MAGI meta-agent governance
- [`r2-engine.md`](./r2-engine.md) — R2 Engine (signals that drive the pipeline)
- [`storage-network.md`](./storage-network.md) — Storage network (R2 node integration)
- [`mod-manager.md`](./mod-manager.md) — Plugin architecture (pipeline hooks)
- [`architecture.md`](./architecture.md) — System overview
