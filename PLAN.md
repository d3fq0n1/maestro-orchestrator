# Plan: Live Code Injection System for R2 + MAGI + NCG

## Problem Statement

Today the self-improvement pipeline (R2 → MAGI → Introspect → Optimize → VIR → Promote) produces **structured proposals** but stops at a "requires human review" gate. No mechanism exists to actually **apply** validated changes to the running system. The entire "promote" step is a no-op — it records the result to disk and returns.

This plan adds a **Code Injection Engine** that closes the loop: when MAGI_VIR validates a proposal and recommends `promote`, the system can apply those changes to itself on the fly — safely, reversibly, and with an audit trail.

---

## Architecture Overview

```
Existing pipeline (unchanged):
  R2 score → MAGI analyze → Introspect → Propose → VIR validate
                                                        │
New:                                                    ▼
                                              ┌─────────────────┐
                                              │  CodeInjector    │
                                              │  (applicator.py) │
                                              └────────┬────────┘
                                                       │
                                    ┌──────────────────┼──────────────────┐
                                    ▼                  ▼                  ▼
                            Runtime Params      Source Patch       Config Reload
                          (hot threshold/      (AST rewrite       (agent model/
                           temp changes)        to .py files)      temp changes)
                                    │                  │                  │
                                    └──────────┬───────┘──────────────────┘
                                               ▼
                                        ┌─────────────┐
                                        │ RollbackLog  │
                                        │ (snapshots)  │
                                        └─────────────┘
```

---

## Step-by-step Plan

### Step 1 — `maestro/applicator.py`: Code Injection Engine (core)

Create a new module `maestro/applicator.py` with a `CodeInjector` class that can apply three categories of validated proposals:

**1a. Runtime parameter injection** (`change_type == "parameter_update"`)
- For threshold proposals (QUORUM_THRESHOLD, SIMILARITY_THRESHOLD), directly mutate the module-level variable in `maestro.aggregator` at runtime via `setattr` / direct assignment.
- For temperature proposals, update agent configuration in memory.
- This is the hot path — no file writes, no restart needed, takes effect on the next orchestration call.

**1b. Source-level patching** (`change_type == "code_patch"` or `"architecture_refactor"`)
- Use Python's `ast` module to parse the target file, locate the node (using `file_path` + `line_number` + `target_name` from the proposal), and rewrite the value.
- Write the modified AST back to the source file using `ast.unparse()` (Python 3.9+).
- After writing, call `importlib.reload()` on the affected module so the running process picks up the change.
- This is the heavy path — used for structural changes that must persist across restarts.

**1c. Config-level changes** (`change_type == "config_change"`)
- Update agent configurations (model, timeout) by modifying the agent registry / instantiation parameters.
- Support a JSON-based runtime config overlay file (`data/runtime_config.json`) that agents read on each session, so config changes survive restarts without modifying source.

**Key class:**
```python
@dataclass
class InjectionResult:
    proposal_id: str
    applied: bool
    injection_type: str       # "runtime", "source_patch", "config"
    rollback_id: str          # links to RollbackLog entry
    error: Optional[str]
    timestamp: str

class CodeInjector:
    def apply(self, proposal: OptimizationProposal) -> InjectionResult
    def apply_batch(self, batch: ProposalBatch) -> list[InjectionResult]
    def dry_run(self, proposal: OptimizationProposal) -> InjectionResult
```

### Step 2 — `maestro/rollback.py`: Rollback & Snapshot System

Every injection must be reversible. Create a rollback system:

- **Before** applying any change, snapshot the current state:
  - For runtime params: record the current value of the module variable.
  - For source patches: copy the original file content to `data/rollbacks/{rollback_id}.py.bak`.
  - For config changes: snapshot the current config overlay.
- **RollbackLog** persists to `data/rollbacks/log.json` — an append-only ledger of all applied changes with:
  - `rollback_id`, `proposal_id`, `injection_type`, `timestamp`
  - `original_value`, `new_value`
  - `file_path` (for source patches)
  - `status`: `applied` | `rolled_back`
- `CodeInjector.rollback(rollback_id)` restores the original state.
- `CodeInjector.rollback_batch(cycle_id)` rolls back all changes from a given improvement cycle.

```python
@dataclass
class RollbackEntry:
    rollback_id: str
    proposal_id: str
    cycle_id: str
    injection_type: str
    original_value: str
    new_value: str
    file_path: Optional[str]
    module_name: str
    target_name: str
    status: str               # "applied", "rolled_back"
    timestamp: str

class RollbackLog:
    def snapshot(self, proposal, current_value) -> RollbackEntry
    def mark_rolled_back(self, rollback_id)
    def get_active(self) -> list[RollbackEntry]
    def get_by_cycle(self, cycle_id) -> list[RollbackEntry]
```

### Step 3 — `maestro/injection_guard.py`: Safety Guards

Code injection is dangerous. Add safety rails:

- **Proposal whitelist**: Only apply proposals in approved categories (`threshold`, `agent_config`, `token_tuning`). Block `architecture` and `pipeline` by default — these require human review.
- **Bounds enforcement**: Re-validate that proposed values are within the min/max bounds defined in `_THRESHOLD_STRATEGIES` and `_TEMPERATURE_STRATEGIES` before applying. Never trust the proposal alone.
- **Rate limiting**: Maximum N injections per hour (configurable, default 5). Prevents runaway self-modification loops.
- **Circuit breaker**: After applying changes, run a quick "smoke test" — a single benchmark prompt through the pipeline. If the R2 grade drops below `acceptable`, auto-rollback the entire batch immediately.
- **Opt-in gate**: The entire injection system is disabled by default. Enabled via environment variable `MAESTRO_AUTO_INJECT=true` or runtime config. When disabled, the system behaves exactly as today (proposals logged, never applied).

```python
class InjectionGuard:
    def is_injectable(self, proposal: OptimizationProposal) -> tuple[bool, str]
    def check_bounds(self, proposal: OptimizationProposal) -> bool
    def check_rate_limit(self) -> bool
    def smoke_test(self, injector: CodeInjector) -> bool
```

### Step 4 — Integrate into `SelfImprovementEngine`

Modify `maestro/self_improve.py` to call the injector after VIR validation:

- After Phase 5 (promote/reject), add a new **Phase 6: Apply**:
  - Only runs when `MAESTRO_AUTO_INJECT=true` AND VIR recommends `promote`.
  - Calls `InjectionGuard.is_injectable()` for each proposal.
  - Calls `CodeInjector.apply_batch()` for approved proposals.
  - Runs `InjectionGuard.smoke_test()` post-injection.
  - Auto-rollback on smoke test failure.
  - Records injection results in the `ImprovementCycle` metadata.

- Add new fields to `ImprovementCycle`:
  - `injections: list` — list of `InjectionResult` dicts
  - `auto_injected: bool` — whether auto-injection was attempted
  - `rollback_triggered: bool` — whether smoke test caused rollback

### Step 5 — API Endpoints

Add endpoints to `maestro/api_self_improve.py`:

- `POST /api/self-improve/inject/{cycle_id}` — Manually trigger injection of a validated cycle's proposals (for human-in-the-loop use).
- `POST /api/self-improve/rollback/{rollback_id}` — Roll back a specific injection.
- `POST /api/self-improve/rollback-cycle/{cycle_id}` — Roll back all injections from a cycle.
- `GET /api/self-improve/injections` — List all active (non-rolled-back) injections.
- `GET /api/self-improve/rollbacks` — Full rollback history.

### Step 6 — Tests

Add test coverage in `tests/test_code_injection.py`:

- **Unit tests for CodeInjector**:
  - Runtime param injection applies and is readable.
  - Source patch modifies file and reload works.
  - Config overlay writes and reads correctly.
  - Dry run doesn't mutate anything.

- **Unit tests for RollbackLog**:
  - Snapshot captures correct original value.
  - Rollback restores original state.
  - Batch rollback by cycle_id works.

- **Unit tests for InjectionGuard**:
  - Whitelisted categories pass, blocked categories fail.
  - Bounds checking catches out-of-range proposals.
  - Rate limiting blocks excessive injections.
  - Smoke test triggers rollback on degradation.

- **Integration test**:
  - Full pipeline: populate R2 ledger with collapse → run cycle → auto-inject → verify runtime params changed → verify smoke test passes → verify rollback works.

### Step 7 — Runtime Config Overlay

Create `data/runtime_config.json` schema:

```json
{
  "auto_inject_enabled": false,
  "max_injections_per_hour": 5,
  "injectable_categories": ["threshold", "agent_config", "token_tuning"],
  "blocked_categories": ["architecture", "pipeline"],
  "smoke_test_prompts": ["What is consciousness?"],
  "smoke_test_min_grade": "acceptable"
}
```

Agents and the aggregator read from this overlay at session start, so config injections take effect without process restart.

---

## Files to Create
| File | Purpose |
|---|---|
| `maestro/applicator.py` | CodeInjector — applies proposals to running system |
| `maestro/rollback.py` | RollbackLog — snapshot/restore for every injection |
| `maestro/injection_guard.py` | Safety guards, bounds, rate limits, smoke test |
| `tests/test_code_injection.py` | Full test suite for injection system |

## Files to Modify
| File | Change |
|---|---|
| `maestro/self_improve.py` | Add Phase 6 (Apply) to `run_cycle()`, new fields on `ImprovementCycle` |
| `maestro/api_self_improve.py` | Add inject/rollback endpoints |
| `maestro/aggregator.py` | Read runtime config overlay for thresholds |
| `maestro/orchestrator.py` | Read runtime config overlay at session start |

---

## Design Principles

1. **Off by default** — Auto-injection is opt-in. The system ships safe.
2. **Every change is reversible** — No injection without a snapshot. Rollback is always one call away.
3. **Evidence chain preserved** — Every injection links back to the R2 signals, MAGI recommendations, and VIR validation that justified it.
4. **Bounded changes** — Strategy min/max bounds are enforced at injection time, not just proposal time.
5. **Fail-safe** — Smoke test after injection. Degradation = automatic rollback.
6. **Audit trail** — Full history of what was injected, when, why, and whether it was rolled back.
