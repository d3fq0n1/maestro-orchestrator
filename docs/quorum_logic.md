# Quorum Logic – Maestro-Orchestrator

**Version:** v0.2-webui
**Last Updated:** 2025-06-05
**Author:** defcon

Maestro-Orchestrator uses a structured quorum system to synthesize multiple AI model responses into a single representative answer while preserving meaningful dissent.

This approach prevents groupthink and fosters dynamic interplay among models.

---

## Quorum Threshold

- The system requires a **66% supermajority** to mark a consensus.
- If 3 out of 4 agents agree, the response is marked as **agreed**.
- Dissenting outputs are stored and displayed in the UI for transparency.

---

## Why 66%?

- A simple majority (50%) is insufficient to represent strong consensus.
- 66% ensures diversity of opinion while allowing convergence.
- Prevents ties in small agent groups (e.g., 2 vs. 2).

---

## Agreement Criteria

Agreement between agents is determined by:

1. **Semantic similarity** — token overlap, structural alignment
2. **Intent convergence** — do the models arrive at similar conclusions?
3. **Tone and framing** — aggressive vs. reflective vs. skeptical modes are normalized

The system uses lightweight heuristics for now, with plans to integrate LLM-based self-evaluation in future releases.

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
    "sol": "...",
    "aria": "...",
    "prism": "...",
    "tempagent": "..."
  },
  "consensus": {
    "agreement_ratio": 0.75,
    "agreed": true,
    "summary": "Consensus reached on ethical concerns."
  }
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
- Dissent weighting (track dissent frequency per agent)
- Self-voting agents (models critique peer responses)
- Public consensus ledger (decentralized append-only record)
- NCG-informed quorum scoring (weight consensus by drift distance from headless baseline)
