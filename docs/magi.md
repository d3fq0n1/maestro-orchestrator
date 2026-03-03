# MAGI: Meta-Agent Governance and Insight

**MAGI** (Meta-Agent Governance and Insight) is Maestro-Orchestrator's long-term memory. It reads the R2 ledger and session history to detect patterns that span many sessions, producing structured Recommendations for system-level changes.

Where R2 scores a single session, and NCG catches silent collapse in the moment, MAGI watches for gradual drift, recurring blind spots, and systematic conformity pressure over time.

---

## Core Responsibilities

- **Agent Health Tracking**: Monitor per-agent outlier rates across sessions to distinguish valuable dissent from noise
- **Trend Detection**: Track confidence trends (improving/declining/stable) across the R2 ledger
- **Collapse Monitoring**: Measure how frequently silent collapse occurs and flag systematic patterns
- **Signal Aggregation**: Identify recurring R2 signals that indicate persistent systemic issues
- **Recommendation Generation**: Produce human-readable proposals for system-level changes
- **Code Introspection**: Map R2 improvement signals to specific code locations in Maestro's own source via the self-improvement pipeline
- **Optimization Proposals**: Generate concrete, actionable proposals for threshold tuning, agent config adjustments, and architecture refactoring

---

## System Role

MAGI agents exist *above* the per-session analysis. They read the accumulated data and propose structural changes.

MAGI works alongside two complementary subsystems:
- **R2 Engine** -- Scores each session in real time, detects dissent and improvement signals
- **NCG (Novel Content Generation)** -- Provides headless baseline for drift and silent collapse detection

Where R2 catches problems in a single session and NCG catches conformity in the moment, MAGI detects patterns that only become visible across many sessions.

---

## Inputs

- `data/r2/` -- R2 Engine ledger entries with scores, signals, and dissent summaries
- `data/sessions/` -- Persisted session JSON records
- R2 trend analysis (`analyze_ledger_trends()`)

---

## Recommendation Types

| Category | Severity | Example |
|----------|----------|---------|
| `agent` | warning | "Prism is a persistent outlier (80% outlier rate across 10 sessions)" |
| `system` | warning | "Confidence is declining across sessions (mean: 45%)" |
| `system` | critical | "Frequent silent collapse detected (60% of recent sessions)" |
| `system` | warning | "Recurring signal: suspicious_consensus (5 occurrences)" |
| `positive` | info | "No silent collapse detected across 20 sessions" |
| `positive` | info | "Healthy dissent is common (observed in 8 sessions)" |
| `positive` | info | "Confidence is improving (trending upward)" |
| `code_optimization` | warning | "Code optimization available: threshold (3 proposals)" |
| `code_optimization` | info | "Code optimization available: agent_config (1 proposal)" |

---

## API

```python
from maestro.magi import Magi

magi = Magi()  # uses default R2Engine and SessionLogger
report = magi.analyze(ledger_limit=50, session_limit=50)

# Report fields
report.sessions_analyzed        # int
report.ledger_entries_analyzed  # int
report.confidence_trend         # "improving", "declining", "stable"
report.mean_confidence          # float 0.0-1.0
report.grade_distribution       # {"strong": N, "weak": N, ...}
report.agent_health             # {name: {sessions, outlier_count, outlier_rate}}
report.collapse_frequency       # float 0.0-1.0
report.recurring_signals        # {signal_type: count}
report.recommendations          # list of Recommendation
```

### Code Introspection API

```python
result = magi.analyze_with_introspection()

# Result includes standard report plus:
result["code_targets"]              # list of identified code locations
result["optimization_proposals"]    # concrete change proposals
result["introspection_summary"]     # human-readable summary
result["proposal_batch"]            # ProposalBatch object for VIR validation
```

### REST Endpoints

```
GET /api/magi?ledger_limit=50&session_limit=50
```

Returns the full MAGI analysis as JSON, including all recommendations.

```
GET /api/self-improve/introspect
```

Returns MAGI analysis with code introspection targets and optimization proposals.

---

## The Rapid Recursion Loop

The full self-improvement cycle:

1. **Observe** -- Maestro runs sessions, NCG generates baselines
2. **Score** -- R2 grades each session, detects signals, indexes the ledger
3. **Analyze** -- MAGI reads the ledger across sessions, detects patterns
4. **Introspect** -- MAGI maps signals to Maestro's own source code via AST analysis and signal-to-code rules
5. **Propose** -- MAGI produces structured Recommendations and concrete optimization proposals (threshold tuning, agent config, architecture refactoring)
6. **Validate** -- MAGI_VIR tests proposals in an isolated sandbox on a separate compute node
7. **Inject** -- Validated proposals are applied to the running system (opt-in auto-injection, or manual trigger via API)
8. **Verify** -- Post-injection smoke test; automatic rollback if system health degrades

MAGI is steps 3-5: the bridge between accumulated observation and proposed action. Steps 7-8 are handled by the Code Injection Engine (`maestro/applicator.py`) with safety guards (`maestro/injection_guard.py`). See [`self-improvement-pipeline.md`](./self-improvement-pipeline.md) for the full pipeline documentation.

---

## Ethical Design

MAGI is read-only by design. It never modifies the R2 ledger, session records, or orchestrator configuration. All recommendations are proposals that require human review. This prevents the emergence of unseen control structures within the orchestrator.

The self-improvement pipeline extends this principle: optimization proposals are validated in an isolated MAGI_VIR sandbox before promotion. Auto-injection is opt-in (`MAESTRO_AUTO_INJECT=true`) and disabled by default. When enabled, injected changes are smoke-tested and automatically rolled back if system health degrades. Every injection is reversible and auditable.

Every MAGI analysis is reproducible: given the same ledger and session data, it produces the same recommendations.

---

## See Also

- [`self-improvement-pipeline.md`](./self-improvement-pipeline.md) -- Full self-improvement pipeline documentation
- [`r2-engine.md`](./r2-engine.md) -- R2 Engine (per-session scoring and signals)
- [`ncg.md`](./ncg.md) -- Novel Content Generation and drift detection
- [`architecture.md`](./architecture.md) -- System overview
