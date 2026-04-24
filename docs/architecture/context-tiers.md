# Context Tiers — Three-Tier Epistemology

Maestro-Orchestrator's Weights (the council of agents) currently reason
over a single opaque prompt string plus whatever their training priors
carry. This document specifies the three-tier context model that
replaces that arrangement: **Cartridges** (canonized known-truths),
**Whirlpool** (live decaying context), and **Weight Priors** (training).
The **Context Router** composes an admission bundle from the three tiers
for every query, and the R2 engine gains a pre-hoc gatekeeping role
alongside its existing post-hoc scoring role.

This document describes the model and the integration points. It
specifies no algorithms, storage formats, or code. Those are in the
per-tier documents (`librarian.md`, `whirlpool.md`,
`router-distance.md`).

---

## Conflicts with existing design

Four integration decisions were resolved before drafting. They are
recorded here so the architecture is legible to future readers.

1. **Wire format for trust-annotated context.** `Agent.fetch(prompt:
   str) -> str` remains the universal contract. It crosses an RPC
   boundary for `ShardAgent` (`maestro/agents/shard.py`). Trust
   annotations travel as a structured preamble *inside* the prompt
   string — a fenced, machine-readable block the Weight is instructed
   to parse. No change to the `Agent` ABC, no change to the node RPC
   protocol.

2. **Admission-gate location.** `R2Engine` today is strictly post-hoc
   (`maestro/r2.py:340–376`), and `InjectionGuard`
   (`maestro/injection_guard.py`) guards code mutation, not context. A
   new module, `maestro/admission.py`, composes with both: it calls
   into a new pre-hoc interface on `R2Engine`, and shares the opt-in /
   rate-limit / audit primitives already proven in `InjectionGuard`.
   Neither existing module is renamed or refactored.

3. **Naming.** The task brief says "WeightNode" throughout; the code
   uses `WeightHost` (`maestro/shard_registry.py:37`, with a
   backward-compatible `StorageNode` alias). All three-tier documents
   and code use `WeightHost`. Cartridge-awareness and Whirlpool-domain
   fields are added to `WeightHost`.

4. **Per-agent pre-fetch hook.** The Router admits context per agent,
   because trust and distance can differ per Weight. Rather than
   introduce a new hook point, the Router runs inside the existing
   `pre_orchestration` hook
   (`maestro/plugins/manager.py:47–57`, fired at
   `maestro/orchestrator.py:126–131` and `:411–417`) and attaches
   per-agent bundles to a dict on the hook context. The orchestrator
   reads that dict before `agent.fetch()` and prepends the rendered
   preamble to the prompt.

---

## The Three Tiers

### Tier 1 — Cartridges (Librarian)

A **Cartridge** is an immutable, content-addressed, signed context
module representing a known-truth that has been canonized. It is the
Librarian's unit of output.

Examples:
- Unit definitions (SI, imperial)
- Statute text at a specific enactment version
- Protocol specifications (RFC 9110 §3.4)
- Schema versions

Properties:
- **Immutable.** Addressed by the hash of its content plus manifest.
  Once published, never mutated.
- **Signed.** Attested by MAGI (or a delegated canonization authority)
  before it enters the Librarian.
- **Zero-freshness.** Not subject to decay. Superseded by a new
  Cartridge that explicitly references the predecessor; never edited
  in place.
- **Revocable.** A revocation record propagates across federated
  Librarian instances. Routers refuse to admit a revoked Cartridge
  even if it is still present in local storage.
- **Cheap to load.** Loaded by reference, not by retrieval-and-rank.
  A Weight asked about SI units should *always* have the relevant
  Cartridge admitted; trust is already adjudicated.

MAGI gatekeeps canonization. See `librarian.md` for the nomination /
review / anchoring / supersession pipeline.

### Tier 2 — Whirlpool

A **Whirlpool** is a live-ingesting agent (or a set of domain-scoped
agents) that maintains a vortex of fresh context. Material enters at
the periphery as raw feed, spirals inward as it accumulates
corroboration and structure, and either:

- is promoted toward Cartridge candidacy (inner-most ring, referred
  to the Librarian), or
- is flung out via centrifugal decay if corroboration does not
  accumulate in its decay window.

Each Whirlpool has:
- an **ingest policy** (what sources, how often, how much)
- a **decay profile** (time-to-expiry as a function of ring depth and
  corroboration count)
- a **domain scope** (a set of tags the Router uses to select Whirlpools
  for a query)

The vortex topology itself is a signal. Density clusters (many pieces
of material corroborating the same claim near the center) indicate
"hot" topics that the Router weights toward admission.

Whirlpools are distinct from agents. A Whirlpool does not answer
prompts; it maintains a ranked, decaying store that the Router queries.
See `whirlpool.md`.

### Tier 3 — Weight Priors

What the Weights already carry from training. This tier is not
changed by this work, and Maestro does not mediate its contents. It is
explicitly named as the third source the Router composes from so that:

- trust annotations can indicate "this claim came from the Weight
  itself, not from an admitted Cartridge or Whirlpool excerpt";
- the Router can account for the Weight's priors when scoring
  distance (a Cartridge that merely restates a Weight prior adds
  little value and can be de-weighted);
- R2 can detect drift between Weight priors and higher-trust tiers,
  flagging where training knowledge has fallen out of date relative
  to canonized or live context.

The Weight's training date is already stamped in
`Agent.build_system_prompt()` (`maestro/agents/base.py:16–25`). That
stamping continues unchanged.

---

## The Context Router

### Admission function

For a query `Q` and a candidate claim `C` drawn from any tier, the
Router admits `C` into the per-agent bundle iff

```
(trust(C) × relevance(Q, C)) / distance(Q, C) ≥ τ
```

where:

- `trust(C) ∈ [0, 1]` is tier-dependent: Cartridges inherit the
  Librarian's attested trust; Whirlpool material inherits its ring
  depth and corroboration count; Weight-prior claims inherit a fixed
  baseline tunable per deployment.
- `relevance(Q, C) ∈ [0, 1]` is topic and query-type alignment,
  computed over embeddings and structural features.
- `distance(Q, C) ∈ (0, ∞)` is a composite metric over embedding,
  graph, causal, and counterfactual proxies. It is *not* monotonic
  with embedding similarity alone — distant-but-relevant material
  exists. The full composition is specified in `router-distance.md`.
- `τ` is the admission threshold, per-agent and per-tier tunable
  from MAGI review data.

### Stochastic long-shot tail

The Router also admits a small fraction of candidates with high
`distance(Q, C)` but non-trivial `trust(C) × relevance(Q, C)`. This
preserves long-shot inclusions — material the embedding metric would
ordinarily reject but that might reframe the query. The tail size is
tunable; its contribution is audited via R2.

### Trust annotations reach the Weight

Admitted claims travel into the prompt string as a structured preamble
the Weight is instructed to parse. Each claim carries its tier, its
trust, its source, and a short provenance chain. The Weight reasons
over trust-annotated context, not flattened blobs. The exact preamble
schema is specified in `router-distance.md`.

---

## Interlock with Existing Maestro

### Pipeline position

```
User prompt
    │
    ▼
[ModManager pre_orchestration hook]
    │   ├─ ContextRouter.assemble(prompt, agents) per agent
    │   └─ AdmissionGuard.gate(bundle) per agent
    │
    ▼
[Orchestrator: for each agent, prepend bundle preamble to prompt]
    │
    ▼
asyncio.gather(agent.fetch(prompt_with_preamble) for agent in agents)
    │
    ▼
[deliberation → dissent → NCG → aggregation → R2 post-hoc scoring]
```

The Router runs inside `pre_orchestration`. The orchestrator reads
per-agent bundles from the hook context and prepends the rendered
preamble string before calling `agent.fetch()`. No change to the
`Agent` ABC.

### Admission guard module

`maestro/admission.py` is a new module. It:

- exposes `AdmissionGuard.gate(bundle) -> (admitted, reason)`
- calls a new pre-hoc method on `R2Engine` (`R2Engine.pre_admit`)
  that logs admission events to a sibling pre-hoc ledger at
  `data/r2/preadmit/` keyed by session and agent
- reuses the opt-in / rate-limit / audit primitives already proven in
  `InjectionGuard` (category whitelist, bounds, rate-limit window)
  by importing and composing, not by subclassing or renaming

The two guards (`InjectionGuard` for code mutation, `AdmissionGuard`
for context admission) remain separate modules with separate on-disk
ledgers. They share nothing except the primitives. This is deliberate:
code mutation and context admission have different blast radii.

### WeightHost capability extensions

`WeightHost` (`maestro/shard_registry.py:37`) gains three additive
fields. No existing fields are removed or renamed.

- `loaded_cartridges: list[str]` — content addresses of Cartridges
  this host has pre-loaded into its context working memory
- `whirlpool_subscriptions: list[str]` — domain scopes this host
  subscribes to (overlap with `domain_affinity` is expected; they
  are not merged — see `whirlpool.md` for why)
- `admission_policy: dict` — per-host overrides for `τ`, long-shot
  tail size, and tier weights

These fields inform the Router's per-agent bundle composition so that
material already resident on a host is preferred where trust and
relevance are otherwise equal.

### R2 pre-hoc role

R2 today scores what happened. It will also log what *was allowed to
happen*:

- `R2Engine.pre_admit(session_id, agent, bundle) -> PreAdmitEntry`
  writes a record of the admitted claims, their trust annotations, the
  threshold `τ` in force, and the long-shot tail. Stored at
  `data/r2/preadmit/{entry_id}.json`.
- Post-hoc `R2LedgerEntry` gains an optional `pre_admit_ref: str`
  field linking to the pre-hoc entry for the session. No existing
  field is renamed.

MAGI reads both tracks to tune `τ` and the long-shot tail size.

### No change to other components

The following run unchanged on admitted context:
- Deliberation (`maestro/deliberation.py`). Agents deliberate over
  peer responses produced from preamble-enriched prompts. The
  deliberation prompt builder does not parse the preamble.
- Dissent analysis (`maestro/dissent.py`). Operates on final
  responses regardless of admitted context.
- NCG (`maestro/ncg/`). The headless baseline is generated from the
  bare user prompt *without* preamble, by design — this preserves
  the silent-collapse detector's reference point.
- Aggregation (`maestro/aggregator.py`). Unchanged.

---

## Data Flow

```
                    User prompt Q
                          │
                          ▼
               ContextRouter.assemble(Q)
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   Librarian         Whirlpool(s)     Weight-prior
   (Cartridge hits) (decayed vortex)  baseline tag
        │                 │                 │
        └────────────┬────┴─────────────────┘
                     ▼
         candidate claim set {C_i}
                     │
                     ▼
     admit iff (trust·relevance)/distance ≥ τ
     + stochastic long-shot tail
                     │
                     ▼
         per-agent trust-annotated bundle
                     │
                     ▼
              AdmissionGuard.gate
                     │
                     ▼
            R2.pre_admit(session, bundle)
                     │
                     ▼
    orchestrator prepends preamble to prompt
                     │
                     ▼
              agent.fetch(prompt + preamble)
                     │
                     ▼
        [existing pipeline: deliberation …
                 dissent … NCG … R2 post-hoc]
                     │
                     ▼
     R2 post-hoc entry links pre_admit_ref
                     │
                     ▼
     MAGI reads both tracks → tune τ, tail,
     τ per tier, cartridge revocation review
```

---

## Open Questions (deferred to per-tier documents)

- Cartridge manifest schema and content-addressing scheme → `librarian.md`
- Whirlpool ingest policy interface and decay profile → `whirlpool.md`
- Composite distance metric and stochastic tail tuning → `router-distance.md`
- How forced rotating dissent consumes moderate-distance context →
  `distance-dissent.md`
- Threat model for vortex manipulation and cartridge poisoning →
  `vortex-threat-model.md`
- Evaluation methodology → `testing-context-tiers.md`

---

## See Also

- [`architecture.md`](../architecture.md) — System overview
- [`r2-engine.md`](../r2-engine.md) — R2 post-hoc scoring (unchanged; gains
  pre-hoc sibling)
- [`magi.md`](../magi.md) — Meta-Agent Governance (canonization authority
  for Cartridges)
- [`deliberation.md`](../deliberation.md) — Cross-agent deliberation (runs
  unchanged on admitted context)
- [`ncg.md`](../ncg.md) — Novel Content Generation (headless baseline runs
  on bare prompt, by design)
- [`storage-network.md`](../storage-network.md) — WeightHost registry and
  locality routing (gains Cartridge / Whirlpool fields)
