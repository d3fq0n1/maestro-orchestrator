# R2 Engine: Rapid Recursion & Reinforcement

The **R2 Engine** is Maestro-Orchestrator's reflex layer. After every orchestration session it synthesizes signals from dissent analysis, NCG drift detection, and quorum logic into a single session quality score, indexes the result into a persistent ledger, and identifies improvement signals that MAGI will consume to propose code-level changes.

This is the prototype for **self-improving software**: Maestro nodes + NCG run a session, dissent is measured, improvements are identified at the meta-analysis layer, and R2 provides the structured signal that makes rapid recursion possible.

---

## Three Responsibilities

### 1. Score

Synthesize dissent, drift, and quorum data into a quality grade for each session.

**Grades:**
- **strong** — quorum met, low drift, no collapse, no outliers, no flags
- **acceptable** — quorum met with some concerns (outliers, compression alerts)
- **weak** — quorum not met or high internal dissent
- **suspicious** — silent collapse detected, or very high agreement paired with high NCG drift

**Confidence Score** (0.0–1.0): weighted combination of internal agreement (40%), inverse NCG drift (30%), and quorum status (30%). Halved when silent collapse is detected.

### 2. Index

Write scored consensus nodes to a persistent JSON ledger at `data/r2/`. Each entry captures:
- The prompt, consensus answer, and participating agents
- The full R2Score with grade, confidence, and flags
- Structured improvement signals
- Condensed dissent summary (agreement, dissent level, outliers)
- Whether NCG drift data was attached

The ledger accumulates over time. Each entry is a durable record of what the council produced and what the system observed about itself.

### 3. Signal

Detect patterns that indicate the system should change and produce structured `ImprovementSignal` observations for MAGI:

| Signal Type | Severity | Trigger |
|---|---|---|
| `suspicious_consensus` | critical | Silent collapse — agents agree but drift from headless baseline |
| `persistent_outlier` | warning | One or more agents consistently diverge from the council |
| `compression` | warning | Conversational outputs significantly shorter than baseline |
| `agent_degradation` | warning | Quorum not met — council cannot reach agreement |
| `healthy_dissent` | info | High disagreement without clear outliers (positive diversity signal) |

---

## Pipeline Position

```
Agents → Dissent Analysis → NCG (with internal_agreement) → Aggregation → Session Log → R2
```

R2 runs after all other analysis is complete. It reads the dissent report, the NCG drift report (if enabled), and the quorum confidence from aggregation. It produces scores and signals, then indexes everything into the ledger.

---

## Cross-Session Trend Analysis

`R2Engine.analyze_ledger_trends()` reads recent ledger entries and detects patterns across sessions:

- **Confidence trend** — is confidence improving or declining across recent sessions?
- **Grade distribution** — how many sessions are strong vs. weak vs. suspicious?
- **Recurring signals** — which signal types appear repeatedly?
- **Repeated suspicious consensus** — multiple sessions flagged as suspicious

MAGI will read these trends to detect longer-term patterns and propose system-level improvements.

---

## Relationship to NCG

R2 and NCG form two halves of the system's immune response:

- **R2 detects internal divergence** — when agents disagree with each other within a session
- **NCG detects silent collapse** — when all agents agree, but their agreement has drifted from the headless baseline

The closed loop: Dissent analysis produces an `internal_agreement` score that feeds into NCG's silent collapse detector. High agreement + high NCG drift = silent collapse (RLHF conformity, not genuine reasoning). R2 then scores this entire picture and raises the appropriate signals.

---

## The Rapid Recursion Loop

The full self-improvement cycle:

1. **Observe** — Maestro nodes + NCG run a session
2. **Analyze** — Dissent measures internal agreement, NCG measures external drift, R2 scores the session
3. **Introspect** — MAGI maps R2 signals to specific code locations in Maestro's source via AST analysis
4. **Propose** — R2 produces structured improvement signals; MAGI reads these to produce optimization proposals (threshold tuning, agent config, architecture refactoring)
5. **Validate** — MAGI_VIR tests proposals in an isolated sandbox instance
6. **Inject** — Validated changes are applied to the running system (opt-in auto-injection via `MAESTRO_AUTO_INJECT=true`, or manual trigger via API). When disabled (the default), proposals are recorded for human review
7. **Verify** — Post-injection smoke test; automatic rollback on degradation

R2 is steps 2–3: the bridge between observation and action. Its improvement signals drive the entire self-improvement pipeline.

See [`self-improvement-pipeline.md`](./self-improvement-pipeline.md) for the complete pipeline documentation.

---

## Ledger Entry Example

```json
{
  "entry_id": "a1b2c3d4-...",
  "timestamp": "2026-03-02T15:30:00+00:00",
  "session_id": "sess-abc-123",
  "prompt": "What is the role of dissent in democracy?",
  "consensus": "Synthesized Answer: ...",
  "agents_agreed": ["Sol", "Aria", "Prism"],
  "score": {
    "grade": "acceptable",
    "confidence_score": 0.72,
    "quorum_met": true,
    "internal_agreement": 0.65,
    "ncg_drift": 0.35,
    "silent_collapse": false,
    "compression_alert": false,
    "has_outliers": true,
    "flags": ["Outlier agents detected: Prism"]
  },
  "improvement_signals": [
    {
      "signal_type": "persistent_outlier",
      "severity": "warning",
      "description": "One or more agents consistently diverge...",
      "affected_agents": ["Prism"],
      "data": {"agreement": 0.65}
    }
  ],
  "ncg_attached": true,
  "dissent_summary": {
    "internal_agreement": 0.65,
    "dissent_level": "moderate",
    "outlier_agents": ["Prism"],
    "agent_count": 3
  }
}
```

---

## API

```python
from maestro.r2 import R2Engine

r2 = R2Engine()  # ledger at data/r2/ by default

# Score a session
score = r2.score_session(dissent_report, drift_report, quorum_confidence="High")

# Detect improvement signals
signals = r2.detect_signals(score, dissent_report, drift_report)

# Index to ledger
entry = r2.index(session_id, prompt, consensus, agents, score, signals, dissent_report, drift_report)

# Cross-session analysis
trends = r2.analyze_ledger_trends(limit=20)

# Ledger queries
entries = r2.list_entries(limit=50)
entry_data = r2.load_entry(entry_id)
total = r2.count()
```

---

## See Also

- [`ncg.md`](./ncg.md) — Novel Content Generation and drift detection
- [`magi.md`](./magi.md) — Meta-Agent Governance (consumes R2 signals)
- [`self-improvement-pipeline.md`](./self-improvement-pipeline.md) — Self-improvement pipeline (introspection, proposals, VIR validation)
- [`architecture.md`](./architecture.md) — System overview
