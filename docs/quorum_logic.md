# Quorum Logic – Maestro-Orchestrator

**Version:** v0.3
**Last Updated:** 2026-03-02
**Author:** defcon

Maestro-Orchestrator uses a structured quorum system to synthesize multiple AI model responses into a single representative answer while preserving meaningful dissent.

This approach prevents groupthink and fosters dynamic interplay among models.

---

## Quorum Threshold

- The system requires a **66% supermajority** to mark a consensus.
- Agreement is determined by **semantic similarity clustering**, not exact string matching.
- If 3 out of 4 agents cluster together (pairwise distance < 0.5), the response is marked as **agreed**.
- Dissenting outputs are stored and displayed in the UI for transparency.
- The API returns a numeric `agreement_ratio` (0.0-1.0) alongside "High"/"Medium"/"Low" confidence labels.

---

## Why 66%?

- A simple majority (50%) is insufficient to represent strong consensus.
- 66% ensures diversity of opinion while allowing convergence.
- Prevents ties in small agent groups (e.g., 2 vs. 2).

---

## Agreement Criteria

Agreement between agents is determined by semantic similarity clustering:

1. The dissent analyzer computes pairwise semantic distance between all agent responses
2. The aggregator groups agents into clusters where members have mean pairwise distance below 0.5
3. The largest cluster is the "majority" -- its size divided by total agents is the `agreement_ratio`
4. If `agreement_ratio >= 0.66`, quorum is met

The pairwise distance function uses sentence-transformers embeddings when available, falling back to Jaccard token distance.

---

## Example

### Prompt:
> What are the societal risks of autonomous policing?

### Responses:

- `Sol`: Expresses concern over surveillance abuse
- `Aria`: Highlights ethical dilemmas and biases
- `Prism`: Warns of systemic reinforcement of inequality
- `TempAgent`: Supports deployment with safeguards

Only Sol, Aria, and Prism align — **consensus is reached** (3/4).

---

## Output Structure

```json
{
  "responses": {
    "Sol": "...",
    "Aria": "...",
    "Prism": "...",
    "TempAgent": "..."
  },
  "consensus": "Synthesized Answer: ...",
  "confidence": "High",
  "agreement_ratio": 0.75,
  "quorum_met": true,
  "quorum_threshold": 0.66
}
```

---

## NCG as Quorum Validation

Quorum logic tells you *whether* agents agree. The NCG (Novel Content Generation) module tells you *whether that agreement is meaningful*.

When quorum is reached, the NCG drift detector compares the agreed-upon output against a headless baseline — content generated without conversational framing. If the drift is high, consensus may reflect RLHF conformity rather than genuine reasoning convergence. The aggregator attaches this as `ncg_benchmark` data alongside the quorum result.

This means quorum is no longer binary (agreed/dissented). It now has a quality dimension: agreement that is both internally consistent (agents converge) and externally grounded (convergence point isn't artificially compressed).

See [`ncg.md`](./ncg.md) for details.

---

## Future Enhancements

- LLM-based response comparator (contextual evaluation)
- Dissent weighting (MAGI tracks per-agent outlier rates across sessions)
- Self-voting agents (models critique peer responses)
- Public consensus ledger (decentralized append-only record)
- NCG-informed quorum scoring (weight consensus by drift distance from headless baseline)
- Embedding-based clustering upgrade (use full sentence embeddings instead of token overlap for higher accuracy)
