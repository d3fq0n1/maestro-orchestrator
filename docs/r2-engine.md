# R2 Engine: Rapid Reinforcement & Reflex

The **R2 Engine** is a proposed real-time subsystem of Maestro-Orchestrator. It activates when quorum is reached, acting as both an insight indexer and anomaly flagger. Where MAGI looks across time, **R2 acts in the moment**.

---

## ⚡ Purpose

When all agents agree (quorum), R2:
- Indexes the shared answer in a high-priority ledger.
- Optionally triggers reinforcement mechanisms (e.g. synthetic broadcast, human review, consensus snapshot).
- Flags suspicious agreement patterns for MAGI review (e.g. "too perfect" answers).

---

## 🔁 Interaction Flow

1. Prompt issued → agents reply
2. Quorum reached
3. R2 activates:
   - Records the consensus node
   - Appends metadata tags (topic, polarity, etc.)
   - Sends notification to MAGI, if enabled

---

## 🧠 Design Intention

R2 gives the orchestrator a reflex — a way to recognize strong patterns and record them *intentionally*, rather than passively. This helps build an emergent knowledge base over time.

---

## 🔗 Relationship to NCG

R2 and NCG form two halves of the system's immune response:

- **R2 detects obvious divergence** — when agents disagree with each other within a session. This is internal dissent detection.
- **NCG detects silent collapse** — when all agents agree, but their agreement has drifted away from what an unconstrained (headless) model would produce. This is the blind spot R2 cannot see alone.

Together they ensure that consensus is both genuine (agents independently converge) and grounded (the convergence point isn't shaped purely by RLHF conformity). When R2 records a consensus node, the NCG drift report can be attached to indicate how much the conversational layer compressed or reshaped the answer.

See [`ncg.md`](./ncg.md) for the full NCG specification.

---

## 📊 Ledger Output Example

```json
{
  "type": "r2_indexed_insight",
  "prompt": "What is the role of dissent in democracy?",
  "consensus": "Dissent acts as a stabilizer...",
  "agents_agreed": ["sol", "aria", "openrouter"],
  "timestamp": "2025-06-02T15:08:00Z",
  "tags": ["politics", "ethics", "stability"]
}
```

---

## ⛔ Safeguards

- Requires ≥ 66% quorum
- Logs all activations
- Disables auto-trigger under ambiguous or incomplete sessions
