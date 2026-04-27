# Context Router — Distance, Admission, and Trust Annotation

The **Context Router** is the component that assembles per-agent
context bundles from the three tiers (Librarian Cartridges, Whirlpool
vortex items, Weight priors) on every orchestration query. It
computes a composite distance between the query and each candidate
claim, applies an admission function, injects a stochastic long-shot
tail, renders a trust-annotated preamble the Weight is instructed to
parse, and calls the R2 engine's new pre-hoc gatekeeping interface
to audit admission.

This document specifies: the composite distance metric, the admission
function, the bundle-composition algorithm, the stochastic long-shot
tail, the trust-annotation preamble format, and R2's pre-hoc role.
No code.

---

## Conflicts with existing design

Three decisions were defaulted in the absence of explicit operator
input. Each is a structural choice that should be reviewed before
the skeleton-code step (Task 8). Reversing any of them after
implementation will be more expensive.

1. **Distance-metric scope day 1.** The task brief names four
   components (embedding, graph, causal, counterfactual). Only
   **embedding distance** is computed from live data day 1. The
   other three are **interface stubs returning configurable
   constants** that MAGI can tune from pre-admit ledger trends.
   Rationale: causal and counterfactual proxies are a research
   project and cannot be speed-shipped without substituting
   plausibility for rigor. The stubs preserve the composite shape
   so later components slot in without reshaping the Router. This
   default can be overridden by replacing the stubs with
   data-driven implementations; no API change is required.

2. **Per-agent τ resolution.** The admission threshold `τ` has a
   **global default per tier** plus optional **per-agent overrides**
   declared on `WeightHost.admission_policy`. An agent without an
   override inherits the global default; an override cascades a
   single tier-value or the full per-tier triple. Rationale: mirrors
   the existing `data/runtime_config.json` overlay pattern used by
   `maestro/applicator.py` — known, tested, and compatible with the
   existing snapshot/rollback machinery.

3. **Trust-preamble delimiter.** The preamble is an **XML-style
   fenced block** (`<context-bundle>…</context-bundle>`) with inner
   JSON, prepended to the prompt. Rationale: (a) frontier Weights
   (GPT-4o, Claude, Gemini, Llama) all handle XML-style tags
   robustly; (b) Markdown triple-backtick fencing collides with
   quoted JSON content; (c) a plain-sentinel scheme has no escape
   story if the user prompt contains the sentinel literally. XML
   tags can be escaped with `&lt;` / `&gt;` on the rare collision;
   the Router sanitizes inbound user prompts before rendering.

---

## Composite Distance Metric

For a query `Q` and a candidate claim `C`, the Router computes:

```
distance(Q, C) = w_e · d_embed(Q, C)
              + w_g · d_graph(Q, C)
              + w_c · d_causal(Q, C)
              + w_x · d_counter(Q, C)
```

where all components are normalized to `[0, 1]` and the weights sum
to 1.0. Defaults: `w_e = 0.7`, `w_g = 0.15`, `w_c = 0.1`, `w_x = 0.05`.

`distance(Q, C) = 0` means "effectively identical"; `distance = 1`
means "maximally distant under the composite." The admission function
uses `distance + ε` (ε = 0.01) as the denominator to avoid division
by zero at perfect similarity.

### `d_embed(Q, C)` — Embedding distance

Cosine distance `1 − cos(θ)` between embedding vectors of the query
and the candidate's canonical claim form. Embeddings come from the
provider-neutral embedder already in use for dissent and NCG drift
(`maestro/dissent.py`, `maestro/ncg/drift.py`). The Router does not
introduce a new embedding client.

This is the only component computed from live data day 1.

### `d_graph(Q, C)` — Graph distance (stubbed day 1)

Structural distance over a graph that connects:

- Cartridges by `supersedes` / `revokes` edges (from
  [`librarian.md`](./librarian.md) §Manifest Schema)
- Cartridges to vortex items by shared canonical claim hashes
- Items to items by shared corroborator sources
- Anything to anything by shared `domain_tags` (flat and dotted)

Day 1 interface returns a configurable constant (default 0.5).
Replacement with a live graph traversal is an additive change; no
caller is affected.

### `d_causal(Q, C)` — Causal proxy distance (stubbed day 1)

An operational proxy for "how far would I have to intervene on
variables in `C` to change `Q`'s answer." In full form this would
rest on a structural causal model over the Weights' working domain,
which Maestro does not have. The day 1 interface returns a configurable
constant (default 0.5).

The interface is preserved so a later implementation (for example,
co-occurrence-with-flip-sentiment over the R2 ledger) can slot in
without Router refactoring.

### `d_counter(Q, C)` — Counterfactual proxy distance (stubbed day 1)

An operational proxy for "how similar is `C` to a counterfactual
version of `Q`." In full form this would sample perturbed queries and
measure how much `C`'s relevance shifts. Day 1 interface returns a
configurable constant (default 0.5).

### MAGI-tunable component weights

`w_e, w_g, w_c, w_x` are stored in the same overlay used by
`InjectionGuard` bounds (`data/runtime_config.json`). MAGI can
propose changes; `AdmissionGuard` bounds-checks them the same way
InjectionGuard bounds-checks threshold strategies
(`maestro/injection_guard.py:99–121`).

---

## Trust and Relevance

### `trust(C)`

Per-tier:

- **Tier 1 Cartridge**: `trust = base_cartridge_trust (= 0.95) − revocation_penalty − supersession_penalty`.
  `revocation_penalty = 1.0` if any sig is invalid or the manifest is
  revoked (effectively evicts); `supersession_penalty = 0.1` if the
  Cartridge is superseded and the successor was not admitted (rare —
  should not happen under normal operation).
- **Tier 2 Whirlpool item**: `trust = f(ring, corroborators, domain_match)`.
  Default: `trust = min(1.0, 0.25 + 0.15·ring + 0.05·n_corroborators)`,
  clipped to `[0, 0.9]` (Whirlpool items never reach Cartridge trust
  without promotion).
- **Tier 3 Weight prior**: fixed `trust = 0.5` baseline, operator-tunable.
  The Router does not "admit" Weight-prior claims; this scalar exists
  so the preamble can flag to the Weight which claims are external
  and which are from its own training.

### `relevance(Q, C)`

Combines topic alignment and query-type alignment:

```
relevance(Q, C) = w_topic · cos(emb(Q), emb(C))
                + w_type  · tag_match(Q, C)
```

Defaults: `w_topic = 0.7`, `w_type = 0.3`. `tag_match` is:

- 1.0 on exact-string tag intersection OR dotted prefix match when
  both sides use dotted form
- 0.5 on any-tag overlap between the query's Whirlpool-routed set
  and the candidate's tags
- 0.0 otherwise

---

## Admission Function

```
admit(C, agent) iff
    (trust(C) · relevance(Q, C)) / (distance(Q, C) + ε)  ≥  τ(agent, tier(C))
```

The `τ(agent, tier)` lookup:

1. If `WeightHost.admission_policy` for this agent contains a
   per-tier value, use it.
2. Else if it contains a scalar, use it for all tiers.
3. Else use the global default: `τ[cartridge] = 0.8`,
   `τ[whirlpool] = 0.4`, `τ[weight_prior] = 0.3`.

Global defaults and per-agent overrides both live in
`data/runtime_config.json`.

Admitted claims from the three tiers are merged, deduplicated by
canonical claim hash (Cartridge hash wins over Whirlpool item on
collision), and truncated to a **per-tier budget**:

- Cartridges: no per-request cap; bounded by the candidate set.
- Whirlpool items: `k_max = 8` per agent per request.
- Weight-prior tags: `k_max = 3`.

---

## Stochastic Long-Shot Tail

After the budgeted admission set is assembled, the Router admits a
small **tail** of candidates that failed `admit(...)` but carry
non-trivial `trust(C) · relevance(Q, C)`.

Procedure:

1. Partition rejected candidates into "high-distance, non-trivial-
   product" (trust·relevance ≥ 0.3, distance > median of admitted).
2. Sample `k_tail` candidates from that partition with probability
   proportional to `trust · relevance`.
3. Mark each sampled claim with `tier_annotation.long_shot = true`
   in the preamble so the Weight knows it should weigh the claim
   more skeptically.

Defaults: `k_tail = 2`, sampled without replacement. The tail is
per-agent; different agents in the council may see different long
shots, which is the point — forced diversity of priors.

`k_tail` is one of the signals MAGI observes in the pre-hoc ledger.
High-R2 sessions where tail items correlated with the consensus are
evidence to raise `k_tail`; low-R2 sessions where tail items
correlated with silent collapse are evidence to lower it. See
[`distance-dissent.md`](./distance-dissent.md) for how tail items
interact with the forced rotating dissent mechanism.

---

## Bundle-Composition Algorithm

For each query `Q` and each agent:

1. **Infer query tags.** The Router derives `query_tags` from `Q`:
   a cheap classifier (today: bag-of-tags over recent R2 consensus
   answers matched to stored `domain_tags`) plus any tags attached
   by the `pre_orchestration` hook context.
2. **Collect candidates.**
   - Librarian: `Librarian.candidates(query_tags, kind_filter=None)`
     returns `CartridgeRef`s whose `domain_tags` match.
   - Whirlpools: each Whirlpool whose `domain_tags` match is called
     with `Whirlpool.query(emb(Q), query_tags, k=50)`; returned items
     are normalized to the same candidate shape.
   - Weight priors: a fixed tag-derived summary is added as a
     synthetic candidate per relevant tag (one per tag, carrying
     `trust = 0.5`).
3. **Score.** For each candidate: compute `d_embed`, `d_graph`,
   `d_causal`, `d_counter`, `trust`, `relevance`, and the admission
   criterion.
4. **Admit with budget.** Keep admitted claims up to per-tier
   `k_max`.
5. **Draw long-shot tail.** Sample `k_tail` claims from rejected.
6. **Render preamble** (see next section).
7. **Call R2 pre-admit.** Write the pre-hoc ledger entry with the
   admitted set, rejected set summary, tail selection, `τ` and
   weight values in force, and any threat flags carried from
   Whirlpool items.
8. **Call AdmissionGuard.gate** (see
   [`context-tiers.md`](./context-tiers.md) §Admission guard
   module). If gate refuses (bounds violation, rate limit, disabled),
   the bundle is downgraded to empty and the preamble is rendered as
   an explicit "no context admitted" block — the Weight is told why.
9. **Return to orchestrator.** The orchestrator prepends the
   rendered preamble to the prompt string before calling
   `agent.fetch()`.

All of this runs inside the `pre_orchestration` hook
(`maestro/plugins/manager.py:47–57`, fired at
`maestro/orchestrator.py:126–131` and `:411–417`), in keeping with
the decision recorded in
[`context-tiers.md`](./context-tiers.md) §Conflicts.

---

## Trust-Annotation Preamble Format

The Weight receives the preamble as an XML-style fenced block
prepended to the user prompt. The Weight's system instruction
(stamped by `Agent.build_system_prompt()`,
`maestro/agents/base.py:16–25`) is extended with a short clause
instructing the Weight to parse the block and reason over its
contents as trust-annotated context. Agents that do not support
system-instruction edits at the wire level receive the clause as a
leading sentence of the user prompt.

### Block shape

```
<context-bundle version="1">
  <admission>
    {
      "session_id": "…",
      "agent": "…",
      "tau": {"cartridge": 0.8, "whirlpool": 0.4, "weight_prior": 0.3},
      "distance_weights": {"embed": 0.7, "graph": 0.15, "causal": 0.1, "counter": 0.05},
      "long_shot_k": 2
    }
  </admission>
  <claims>
    [
      {
        "tier": "cartridge",
        "id": "sha256:…",           // manifest_hash
        "kind": "statute_text",
        "trust": 0.95,
        "relevance": 0.87,
        "distance": 0.22,
        "domain_tags": ["law.us.federal.statute"],
        "provenance": ["scribe:…", "issued_at:…"],
        "body_excerpt": "…",
        "long_shot": false
      },
      {
        "tier": "whirlpool",
        "id": "sha256:…",           // item_id
        "whirlpool_id": "…",
        "trust": 0.55,
        "relevance": 0.71,
        "distance": 0.34,
        "ring": 3,
        "corroborators": 5,
        "provenance": [{"source_id": "…", "fetched_at": "…"}],
        "claim_summary": "…",
        "long_shot": false
      },
      {
        "tier": "weight_prior",
        "id": "tag:…",
        "trust": 0.5,
        "tag": "…",
        "long_shot": false
      }
    ]
  </claims>
</context-bundle>
<user-prompt>
  … original user prompt …
</user-prompt>
```

### Semantics the Weight is instructed to observe

- **Trust is explicit.** A claim with `trust = 0.95` carries more
  weight than one with `trust = 0.55`; the Weight should say so when
  the claims disagree.
- **Long-shot claims.** A claim with `long_shot: true` is deliberately
  distant; the Weight should *consider* it but should not treat it
  as evidence against a high-trust claim.
- **Provenance is first-class.** The Weight should cite provenance
  ids in its reasoning when it uses an admitted claim, so R2 can
  post-hoc verify.
- **Absence is informative.** An empty `<claims>` block means
  "AdmissionGuard refused or no candidates matched"; the Weight
  should reason from its training priors and say so, not fabricate.

### Size and truncation

Claim `body_excerpt` is truncated to 1 KiB per claim, configurable
per deployment. Full body bytes are not included; the Weight can
request them via a follow-up tool-call in deployments that wire
tool use. Truncation decisions are recorded in the pre-admit ledger.

### Input sanitization

The Router sanitizes the user prompt before rendering: occurrences
of `<context-bundle`, `</context-bundle>`, `<claims>`, `</claims>`,
and `<user-prompt>` in the user input are replaced with entity
escapes. This prevents a user from injecting a fake admission
record. The NCG headless baseline receives the *unsanitized original
prompt*, by design — the baseline must see exactly what the user
typed for silent-collapse detection to remain valid.

---

## R2 Pre-Hoc Gatekeeping

### New interface

`R2Engine` gains a single new method:

```
R2Engine.pre_admit(
    session_id: str,
    agent_name: str,
    admitted: list[AdmittedClaim],
    rejected_summary: dict,
    tail: list[AdmittedClaim],
    tau: dict,
    distance_weights: dict,
    threat_flags: list[str],
) -> PreAdmitEntry
```

The returned `PreAdmitEntry` carries an `entry_id` that the Router
embeds in the preamble's `admission.session_id`/`agent` compound key
so post-hoc scoring can join the two ledgers.

### Storage

Pre-hoc entries live at `data/r2/preadmit/{entry_id}.json`, a sibling
tree to the existing `data/r2/` post-hoc ledger. No schema collision
with post-hoc entries. The post-hoc `R2LedgerEntry` gains a single
additive field, `pre_admit_ref: str`, linking to the pre-hoc entry.

### What the entry records

- `session_id`, `agent_name`, `timestamp`
- `tau` and `distance_weights` in force (so later runs can replay
  with the same tunings)
- For each admitted / tail claim: `tier`, `id`, `trust`, `relevance`,
  `distance` (per-component breakdown), `long_shot`
- For each rejected tier: count and summary statistics
  (`max_product`, `mean_product`, `count_above_tail_cutoff`)
- Threat flags from Whirlpool items
- Whether `AdmissionGuard.gate` approved or downgraded the bundle

### MAGI consumption

MAGI cross-session analysis reads pre-admit entries alongside
post-hoc entries. New cross-analysis questions:

- Which Cartridges, admitted, correlated with the strongest R2
  grades? (Positive Cartridge-impact trend.)
- Which Whirlpool items, admitted, preceded silent-collapse flags?
- Are long-shot items ever present in healthy-dissent sessions?
  If not, `k_tail` may be too conservative.
- Does a specific `agent_name` consistently reject high-trust
  Cartridges (per-agent `τ` too high)?

These questions become new `Recommendation` categories in MAGI:
`context_admission_tuning` (info), `long_shot_imbalance`
(warning), `cartridge_impact_trend` (info).

---

## Interaction with Existing Signals

- **Dissent.** Dissent analysis runs on final agent responses and is
  unaffected by the preamble. However, if two agents receive
  different long-shot tails and produce different outputs, dissent
  may increase; this is the intended mechanism explored in
  [`distance-dissent.md`](./distance-dissent.md).
- **NCG silent collapse.** The headless baseline is generated from
  the *unsanitized original prompt* with no preamble. This preserves
  the silent-collapse detector's reference point; a drift between
  the preamble-bearing agents and the bare-prompt baseline remains a
  valid signal.
- **Deliberation.** Deliberation rounds share peer responses
  (`maestro/deliberation.py:86–123`). The deliberation prompt builder
  does not parse or reproduce the preamble; each round's prompt is
  freshly built, and the Router runs only on the first round's
  fetches.
- **Self-improvement.** `InjectionGuard` is untouched. The new
  `AdmissionGuard` composes with R2's pre-hoc interface and uses the
  same bounds / rate-limit / opt-in primitives, but writes to a
  separate ledger and gates a separate blast radius.

---

## Open Questions (deferred)

- Live implementations for `d_graph`, `d_causal`, `d_counter`
  (currently stubs). Will be driven by MAGI trend data from the
  pre-admit ledger.
- Query-tag inference quality. The bag-of-tags classifier is a
  placeholder; a stronger classifier (embedding-based k-NN over
  stored `domain_tags`) is worth considering once pre-admit data
  exists.
- Tool-call escape hatch for claim body expansion. Out of scope
  until deployments wire Weight tool-use.

---

## See Also

- [`context-tiers.md`](./context-tiers.md) — Three-tier overview
- [`librarian.md`](./librarian.md) — Cartridge candidates
- [`whirlpool.md`](./whirlpool.md) — Whirlpool candidates and query
  interface
- [`distance-dissent.md`](./distance-dissent.md) — How long-shot
  tails and moderate-distance material interact with forced
  rotating dissent
- [`vortex-threat-model.md`](./vortex-threat-model.md) — Threats to
  admission integrity (preamble injection, Cartridge poisoning)
- [`../r2-engine.md`](../r2-engine.md) — R2 post-hoc scoring
- [`../architecture.md`](../architecture.md) — System overview
