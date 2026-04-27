# Dissent via Distance — Forced Rotation and Counter-Claims

Maestro's aggregator requires a 66% supermajority for quorum
(`maestro/aggregator.py:158`), which by design preserves a dissenting
third as a counterpoint (see `docs/maestro-whitepaper.md:74`,
`docs/roadmap.md:110`). That invariant assumes dissent arises
naturally. This document specifies how the Context Router supports
the invariant when natural dissent would otherwise collapse — via
**forced rotating dissent**: admitting moderate-distance context to
a chosen agent on each session so its priors are perturbed without
fabricating disagreement.

It also addresses **counter-cartridges**: whether Cartridges that
oppose canonized claims need a dedicated Librarian concept.

---

## Conflicts with existing design

Three decisions resolved before drafting.

1. **Forced rotating dissent is new.** No existing Maestro primitive
   implements it. `maestro/r2.py:228` mentions "agent rotation
   adjustments" as a MAGI recommendation string only; nothing acts
   on it. This document specifies the mechanism from scratch and the
   implementation ships in the Task 8 skeleton under
   `router/distance.py` alongside the Router.

2. **Counter-cartridges are not a new Librarian concept.** No new
   `kind`, no `opposes` field, no parallel store. A "counter-
   cartridge" is any Cartridge admitted either with
   `long_shot: true` via the Router's stochastic tail
   (`router-distance.md` §Stochastic Long-Shot Tail) or via the
   forced-rotation mechanism specified below. The Librarian schema
   is unchanged.

3. **Dissenter selection is policy-driven.** The per-session
   dissenter is the agent whose recent R2 history shows the
   strongest correlation with the session majority — the most
   conformist Weight by measurement, not by random rotation. Full
   formula in §Dissenter Selection. This requires a new read path
   into the R2 ledger; the path is computed, cached per orchestrator
   process, and refreshed every N sessions (default N=5).

---

## The 33% Invariant

Maestro's aggregator uses `QUORUM_THRESHOLD = 0.66`
(`maestro/aggregator.py:158`): consensus proceeds only when ≥66% of
agents land in the largest agreeing cluster. The remaining ≤34% are
the **preserved dissent minority**. When fewer than 34% of agents
disagree, one of two things is happening:

- **Genuine convergence on a well-specified question** — fine.
- **Silent collapse** — agents have drifted together toward an
  attractor that the headless baseline does not share
  (`maestro/ncg/drift.py`, surfaced as `silent_collapse_detected` in
  `maestro/r2.py:47`).

The second case is the threat. NCG drift detection identifies it
post-hoc. The Router's forced-rotation mechanism is a *pre-hoc*
intervention: it increases the probability that at least one agent
reaches the fetch step with meaningfully different priors than its
peers, so that silent collapse either does not form or is visible
as genuine dissent in the pairwise analysis.

**The invariant the Router preserves**: forced rotation never
*lowers* the majority below 66% artificially. It only widens one
agent's admitted-context distribution. Whether that agent's final
response lands in the majority cluster is decided by the Weight
itself, which is the point.

---

## The Mechanism

### Dissenter selection

On each session the Router computes, per agent, a **conformity score**
from the R2 post-hoc ledger (`data/r2/`):

```
conformity(agent) =
    mean over last N sessions {
        1.0  if agent's response was in the majority cluster
        0.0  otherwise
    }
```

Majority-cluster membership per session is already recorded in
`R2LedgerEntry.dissent_summary.outlier_agents`
(`maestro/r2.py:365–370`): an agent is in the majority cluster for
that session iff it is not listed as an outlier. Default `N = 20`.
Agents with fewer than `N_min = 5` sessions of history default to
`conformity = 0.5` (neutral); forced rotation does not apply to them.

The dissenter for the current session is `argmax(conformity)`. Ties
are broken by the agent whose last forced-rotation session is
oldest (to maintain rotation); further ties broken by name sort.
Only one dissenter per session.

If the highest conformity is below a floor (default `0.6`), no
dissenter is selected — the council already has adequate natural
dissent, and forced rotation would add noise. This floor is tunable
via `data/runtime_config.json`.

The R2 lookup is cached per orchestrator process and recomputed every
5 sessions to bound ledger read cost.

### Moderate-distance bundle construction

When an agent is selected as the dissenter, the Router runs the
normal bundle-composition algorithm
(`router-distance.md` §Bundle-Composition Algorithm) with three
differences:

1. **Tier thresholds are lowered** for this agent only:
   `τ(dissenter, cartridge) = 0.5` (default 0.8)
   `τ(dissenter, whirlpool) = 0.2` (default 0.4)
   `τ(dissenter, weight_prior) = 0.2` (default 0.3)
   This widens the candidate set toward moderate-distance material.
2. **A moderate-distance window is preferred.** Admitted candidates
   with `distance(Q, C)` in the 50th–80th percentile of the
   candidate pool (moderate, not extreme) are boosted by an
   additive `+0.1` on their admission product before thresholding.
   High-distance (>80th percentile) items still enter via the
   stochastic tail at their normal rate.
3. **The long-shot tail size is raised** to `k_tail = 4` (default 2)
   for this agent.

The deliberate choice of *moderate* rather than high distance is the
point: very high-distance material tends to be irrelevant noise;
moderate-distance material is the nearest neighbor the standard
admission function declined. That neighbor is often a genuine
alternative perspective.

### Preamble annotation

The preamble sent to the dissenter agent includes a single extra
field in its `admission` block:

```
"forced_rotation": {
  "role": "dissenter",
  "policy": "max_conformity",
  "dissenter_threshold_tau": {...},
  "session_index_in_rotation": 3
}
```

The agent is *not* told to "disagree." It is told (via a short
clause appended to the system instruction) that it has been given a
widened context window and should weigh the additional claims on
their merits. The system never instructs a Weight to produce dissent
against its honest conclusion; it only manipulates the inputs.

### Non-dissenters

Every other agent in the session receives the ordinary bundle with
the global defaults from `router-distance.md`. The preamble for
those agents carries `"forced_rotation": null`.

---

## Counter-Cartridges

A counter-cartridge is a Cartridge whose canonical claim contradicts
another canonized Cartridge's claim. Three ways such material enters
a bundle without any Librarian schema change:

1. **As a long-shot tail draw.** The Router's stochastic tail (see
   `router-distance.md` §Stochastic Long-Shot Tail) can sample a
   Cartridge whose distance from the query pushed it below the
   admission threshold. If that Cartridge happens to contradict an
   admitted one, the preamble carries both with their normal
   metadata and `long_shot: true` on the sampled one.
2. **As a dissenter admission.** The lowered `τ` for the dissenter
   (above) widens the Cartridge candidate set, so a contradicting
   Cartridge the majority would have seen excluded may be admitted
   for the dissenter.
3. **As a supersession edge.** A Cartridge that supersedes another
   (`supersedes: [hash]` in `librarian.md` §Supersession) is by
   definition a counter-claim to the superseded material. The
   Librarian already handles this: the superseded hash is marked
   and the successor is admitted. No new concept needed.

The system handles the resulting juxtaposition two ways:

- **Weight-side**, the preamble schema already includes `trust`,
  `relevance`, and `distance` per claim; when two admitted Cartridges
  contradict, the Weight is instructed (by its system clause) to
  identify the disagreement explicitly in its response, so dissent
  analysis can see it.
- **Router-side**, an optional post-assembly pass detects contradictory
  pairs among admitted Cartridges (two Cartridges of the same `kind`
  sharing a `domain_tag` but carrying no `supersedes` link between
  them). Detected pairs are logged to R2's pre-admit ledger under
  `threat_flags: ["contradictory_admitted_cartridges"]`. No pruning —
  the Router deliberately does not pick a winner.

The detection pass is a heuristic, not a proof of contradiction;
false positives are expected. The point is to surface them for MAGI
to investigate, not to suppress them.

---

## Interaction with the 33% Threshold

The quorum threshold (`QUORUM_THRESHOLD = 0.66` in
`maestro/aggregator.py`) is untouched. Forced rotation cannot alter
it. What forced rotation changes:

- **Before** forced rotation: silent collapse, when it occurs, is
  detected post-hoc by NCG drift analysis. The Weight outputs have
  already been produced by the time the signal fires.
- **After** forced rotation: the dissenter's priors were perturbed
  pre-fetch. If the majority was a genuine attractor, the dissenter
  will likely still agree and the session looks unchanged. If the
  majority was silent collapse, the dissenter — now carrying
  moderate-distance Cartridges or Whirlpool items — has a higher
  probability of falling outside the majority cluster, making the
  collapse visible as *real* pairwise dissent rather than as an
  NCG drift gap.

Quantitatively, forced rotation aims to keep
`1 − QUORUM_THRESHOLD = 0.34` of capacity available for dissent, not
to guarantee it. On questions with genuine consensus, every agent
including the dissenter may still agree, and the dissenter's
moderate-distance admissions act as Cartridge-validation (its
response cites the admitted counter-claims and explains why it
still concurs). That outcome is equally valuable.

### What forced rotation does not do

- It does **not** inject claims the Weight must adopt.
- It does **not** re-weight dissent after the fact; the aggregator
  sees the same agents with the same responses.
- It does **not** lower the quorum threshold.
- It does **not** make a Weight produce specific output.

What it does do is move one Weight's input distribution per session
in a controlled way, and do so on the Weight most statistically
prone to agreeing.

---

## Interaction with R2

### Pre-hoc ledger

`R2Engine.pre_admit` (see `router-distance.md` §R2 Pre-Hoc
Gatekeeping) records the forced-rotation selection on every session:

- `forced_rotation.dissenter: str | null`
- `forced_rotation.conformity_scores: dict[agent_name, float]`
- `forced_rotation.tau_override: dict`
- `forced_rotation.moderate_distance_admits: int` (count of claims
  admitted because of the moderate-distance boost that would not
  have been under default `τ`)
- `threat_flags` including `contradictory_admitted_cartridges` if
  detected.

### Post-hoc ledger

`R2LedgerEntry` gains an optional `forced_rotation_summary: dict`
field (additive only, consistent with the `pre_admit_ref` addition
from `context-tiers.md`):

```
forced_rotation_summary {
  dissenter: str | null
  dissenter_in_majority: bool | null     // whether the dissenter
                                          // agreed with the majority
                                          // after the perturbed bundle
  dissenter_outlier: bool                 // per dissent analysis
  expected_collapse_mitigated: bool       // NCG drift was high AND
                                          // dissenter was out of majority
}
```

### New R2 improvement signals

Two new `ImprovementSignal.signal_type` values:

- `"forced_rotation_no_effect"` (severity `info`): dissenter has been
  in the majority for M consecutive sessions despite perturbation
  (default M=10). Evidence that either the topic space is genuinely
  settled or the moderate-distance threshold is too tight.
- `"forced_rotation_detected_collapse"` (severity `warning`):
  dissenter landed outside the majority *and* NCG drift was high
  on the same session. Evidence that the perturbation surfaced a
  real silent collapse that would otherwise have been post-hoc only.

MAGI consumes both signals and can recommend tuning `τ(dissenter, *)`,
the conformity floor, or the session window `N`.

---

## Interaction with the Rest of the Pipeline

- **Deliberation** (`maestro/deliberation.py`). The dissenter
  participates in deliberation rounds exactly like any other agent.
  In deliberation round 1 it sees the original peer responses;
  peer responses do not leak the dissenter's widened preamble into
  other agents' contexts (the deliberation prompt builder only
  carries prior responses, not preambles). This is intentional: the
  dissenter's *input* is perturbed; its *output* competes on equal
  terms.
- **Dissent analysis** (`maestro/dissent.py`). Unchanged. The outlier
  detector at `dissent.py:143–149` uses a `1.5x` mean-distance
  threshold, which already has robust behavior when one agent
  deviates. No adjustment.
- **NCG** (`maestro/ncg/`). Unchanged. Silent-collapse detection
  continues to operate; its complementary nature to forced rotation
  is the whole point.
- **Aggregator** (`maestro/aggregator.py`). Unchanged. Forced rotation
  does not alter `QUORUM_THRESHOLD` and does not inject a vote. The
  aggregator sees final responses and clusters them.

---

## Open Questions (deferred)

- **Conformity score with weighted history.** The flat mean is a
  starting point. Exponential decay over session age (recent sessions
  weighted higher) is a plausible MAGI-driven tuning target once
  pre-admit data accumulates.
- **Multi-dissenter sessions.** The current policy selects exactly
  one dissenter. If future MAGI data suggests two dissenters reveal
  more silent collapses than one, the scheme extends cleanly; until
  then, one keeps the intervention minimal.
- **Contradiction-detection quality.** The co-tag / no-supersession
  heuristic is coarse. A better detector (e.g. NLI over canonical
  claim forms) is worthwhile but out of scope for this document.
- **Topic-space settledness.** If forced rotation consistently
  produces no effect on a domain, that domain's Whirlpool is
  arguably over-decayed or the Cartridge coverage is saturated.
  MAGI should eventually surface this, but the signal shape is
  domain-specific.

---

## See Also

- [`context-tiers.md`](./context-tiers.md) — Three-tier overview
- [`router-distance.md`](./router-distance.md) — Admission function
  and long-shot tail that forced rotation extends
- [`librarian.md`](./librarian.md) — Cartridge schema (unchanged by
  counter-claim handling)
- [`vortex-threat-model.md`](./vortex-threat-model.md) — Attacks
  that target the dissenter-selection path
- [`../r2-engine.md`](../r2-engine.md) — R2 signals and post-hoc
  ledger (unchanged; gains additive fields)
- [`../quorum_logic.md`](../quorum_logic.md) — The 66% supermajority
  threshold that forced rotation preserves
- [`../ncg.md`](../ncg.md) — Silent-collapse detection that forced
  rotation complements
