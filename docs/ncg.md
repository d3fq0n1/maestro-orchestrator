# NCG: Novel Content Generation

**NCG** is the parallel diversity benchmark track in Maestro-Orchestrator. Where MAGI detects drift across sessions and R2 detects dissent in the moment, NCG **prevents model collapse** by maintaining a headless baseline against which all conversational outputs are measured.

---

## The Problem NCG Solves

Conversational agents are shaped by RLHF — trained to be helpful, concise, safe. These are compression forces that push outputs toward homogeneity. When all agents in the council agree, that could mean genuine consensus — or it could mean they all learned the same reward-hacked shortcut.

R2 catches **obvious divergence** (agents disagreeing with each other).
NCG catches **silent collapse** (agents all agreeing on something shaped by conformity, not reasoning).

---

## Architecture

```
Conversational track:  Sol ───┐
                       Aria ───┼── compare among ── R2 (internal dissent)
                      Prism ───┘
                                     │
                                     ▼
NCG track:          headless ─── compare against ── DriftDetector
```

NCG runs as a parallel track. A headless generator produces content for the same prompt without conversational framing — no system prompt, no personality, no alignment shaping. The drift detector then measures the distance between the headless baseline and each conversational agent's output.

---

## Two Tiers of Analysis

### Tier 1: Semantic Drift (available now, all models)

Embedding-based distance measurement. Computes how far each conversational output is from the headless baseline in meaning-space. Available for every model regardless of API capabilities.

### Tier 2: Token-Level Drift (available for models with logprobs)

When the underlying API exposes log probabilities (e.g. OpenAI), the drift detector extracts:
- **Mean uncertainty**: How confident the headless model was across all tokens
- **Uncertain tokens**: Where the model had less than ~13% confidence
- **Contested tokens**: Where the chosen token barely beat its top alternative

This is the bridge between conversational metadata analysis and full token-level analysis.

---

## Key Signals

### Silent Collapse Detection

When the conversational agents show high internal agreement (R2 says they agree with each other) BUT high drift from the NCG baseline, the system flags **silent collapse**. This means the consensus may reflect RLHF conformity rather than genuine reasoning.

### Compression Alert

When conversational outputs are significantly shorter than the headless baseline, the models are compressing away nuance. The compression ratio measures `conversational_length / headless_length` — values below 0.5 trigger an alert.

---

## Integration Points

### Aggregator

The aggregator accepts an optional `ncg_drift_report` parameter. When present, the aggregated output includes:

```json
{
  "ncg_benchmark": {
    "ncg_model": "mock-headless-v1",
    "mean_drift": 0.42,
    "max_drift": 0.51,
    "silent_collapse": false,
    "compression_alert": false,
    "per_agent": [
      {"agent": "Sol", "drift": 0.42, "compression": 0.85, "tier": "semantic"},
      {"agent": "Aria", "drift": 0.51, "compression": 0.72, "tier": "semantic"}
    ]
  }
}
```

### Orchestrator

The orchestrator runs both tracks in sequence: conversational agents first, then NCG headless generation. The drift report feeds into aggregation. Enable/disable via `ncg_enabled` parameter.

---

## Headless Generators

| Generator | Model | Logprobs | Status |
|-----------|-------|----------|--------|
| `MockHeadlessGenerator` | mock-headless-v1 | No | Available (testing) |
| `OpenAIHeadlessGenerator` | gpt-3.5-turbo+ | Yes | Available (needs API key) |
| `AnthropicHeadlessGenerator` | claude-sonnet | No | Available (needs API key) |

The key contract for all generators: **no system prompt, no assistant framing, no conversational scaffolding**. Just the prompt and the weights.

---

## Relationship to MAGI and R2

- **R2** watches a single session: are agents disagreeing right now?
- **MAGI** watches across sessions: are patterns drifting over time?
- **NCG** provides the control group: what would the output look like without conversational pressure?

NCG is the immune system's antibody production — constantly generating diverse material so the system never becomes a monoculture. Maestro (via R2) is the immune response — catching collapse in real time. MAGI is the long-term immune memory.

---

## Future Direction

The current implementation operates primarily at Tier 1 (semantic drift). As token-level APIs become more widely available:

1. **Full logprob analysis** across all agents, not just OpenAI
2. **Attention-level drift** when model internals become accessible
3. **Feedback loops** where NCG drift signals reshape prompts before they hit the conversational agents
4. **Cross-session NCG** where the headless baseline evolves to track what "normal" looks like over time
