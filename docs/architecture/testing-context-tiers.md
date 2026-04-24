# Testing the Three-Tier Context System

This document specifies how the three-tier context epistemology is
evaluated: what to test, what constitutes passing, what to measure,
and how the tests compose with the existing Maestro test suite.

It covers Cartridge integrity, Whirlpool decay correctness, Router
admission quality, and the adversarial stress matrix derived from
[`vortex-threat-model.md`](./vortex-threat-model.md). Every section
names concrete checks that the Task 8 scaffold must satisfy once
its stubs are implemented.

No code. This is a test plan.

---

## Conflicts with existing design

Two items to flag.

1. **Framework.** Existing tests live under `tests/` using pytest
   (see `tests/test_orchestration.py`, `tests/test_code_injection.py`,
   and 14 other `test_*.py` files). All new tests described here
   land in `tests/` under a consistent naming convention
   (`test_librarian_*.py`, `test_whirlpool_*.py`,
   `test_router_*.py`). No new test framework.

2. **Admission quality ground truth.** The Router's admission
   quality cannot be scored without labelled ground truth. Task 1
   found no existing labelled query-to-claim corpus in the repo;
   building one is out of scope for the spec work. The test plan
   therefore distinguishes **structural tests** (pass/fail against
   fixed properties; can ship with Task 8 implementation) from
   **quality benchmarks** (precision/recall against a future
   ground-truth set; the set itself is a follow-up deliverable).
   Only structural tests gate CI at first.

---

## Test Taxonomy

Four tiers, mirroring the architecture:

- **Unit tests** — per-module pure-function correctness. Fast, no
  network, no filesystem beyond tmp dirs. Target coverage: every
  public method in the Task 8 scaffold.
- **Integration tests** — cross-module flows. Use real filesystem
  under a pytest `tmp_path` fixture; no external network. Replace
  HTTP with a loopback FastAPI fixture when testing federation.
- **Adversarial stress tests** — one test per threat in the
  register
  ([`vortex-threat-model.md`](./vortex-threat-model.md) §Threat
  Register Summary). Each test constructs the attack, runs it
  through the relevant guard layer, and asserts the expected
  detection signal fires and the expected block / log occurs.
- **Benchmarks** — end-to-end quality and performance measurements.
  Non-gating in CI; reported as metrics and stored under
  `tests/benchmarks/results/` for trend analysis.

---

## Unit Tests

### Librarian

`tests/test_librarian_types.py`
- Every dataclass round-trips through `dataclasses.asdict` + JSON
  without loss.
- `Manifest.signatures` accepts zero or more `Signature`s.
- `CartridgeKind`, `CanonicalForm` enum values match the strings
  in [`librarian.md`](./librarian.md) §Cartridge Taxonomy.

`tests/test_librarian_addressing.py`
- `canonicalize_body(body, JSON_RFC8785)`: two semantically
  identical JSONs (different whitespace, key order) produce
  identical bytes.
- `canonicalize_body(body, TEXT_UTF8_NFC)`: NFD-input and
  BOM-prefixed input produce identical bytes.
- `compute_manifest_hash` is stable across key-ordering and
  whitespace differences in the input manifest.
- `verify_content_hash` rejects tampered bodies.
- `verify_manifest_hash` rejects a manifest whose stored
  `manifest_hash` does not match its canonical form.
- Unknown `CanonicalForm` raises `ValueError`.

`tests/test_librarian_scribe.py`
- `ScribeKeyStore` refuses to load a private-key file whose mode
  is not 0600 (use `os.chmod` in the test).
- `ScribeKeyStore.sign` produces a `Signature` whose
  Ed25519 verification against the paired public key succeeds.
- `Scribe.anchor` refuses to anchor when
  `len(signing_key_ids) < policy.min_signatures_by_kind[kind]`.
- `Scribe.anchor` assigns `content_hash` and `manifest_hash` and
  the signatures verify.
- `Scribe.anchor_revocation` produces a manifest with empty body,
  `kind = REVOCATION`, and non-empty `revokes`.

`tests/test_librarian_store.py`
- `Librarian.commit` refuses a manifest whose
  `signatures[].key_id` is not in `trusted.json`.
- `Librarian.commit` refuses a manifest whose `content_hash` does
  not match the committed body.
- After commit, `load(manifest_hash)` returns the manifest and
  `head(cartridge_id)` returns the same.
- `load` of a revoked hash returns `LoadResult(revoked=True)`.
- `load` of a superseded hash returns
  `LoadResult(superseded_by=successor_hash)`.
- `candidates(query_domains=["law.us.federal"], ...)` matches a
  Cartridge tagged `["law.us.federal.statute"]` by dotted-prefix
  rule, and does NOT match one tagged `["medical"]`.
- `preload(host_id, manifest_hash)` updates `WeightHost.loaded_cartridges`.

`tests/test_librarian_federation.py`
- `add_peer` / `remove_peer` round-trip via `peers.json`.
- `build_advertisement` includes every revocation even if it is
  older than `max_recent`.
- `fetch_manifest` with a tampered body returns `None` and logs
  `federation_body_mismatch`.
- A Manifest fetched from a peer whose `Signature.key_id` is not
  in local `trusted.json` is rejected (even if the peer URL is
  configured).
- Monotonic sequence enforcement: a peer advertisement with a
  lower sequence than previously observed is ignored.

### Whirlpool

`tests/test_whirlpool_types.py`
- `RingId` integer values match [`whirlpool.md`](./whirlpool.md)
  §Vortex Data Model.
- `DecayProfile.decay_seconds_by_ring` keys are `RingId` members.

`tests/test_whirlpool_ingest.py`
- `FeedFetcher.fetch_feed("http://…")` refuses plain HTTP.
- `TagFilter.filter` strips tags outside
  `policy.domain_tags` and retains tags inside.
- `Dedup.observe`: same publisher observing the same item twice
  returns `None` (no double-count); second distinct publisher
  returns the item with `corroborators = 2`.

`tests/test_whirlpool_vortex.py`
- `Vortex.insert` sets `ring = PERIPHERY`, populates `entered_at`
  and `expires_at` per the decay profile.
- `Vortex.corroborate`: an item with enough corroborators advances
  one ring; an attempt to advance more than one ring per quartile
  pins the item and returns a threat flag. (This is W-1.)
- `Vortex.tick` expires items past `expires_at` and returns them.
- Two items sharing `domain_tags` count toward the same
  `density_hotspot` in `VortexStats`.

`tests/test_whirlpool_pipeline.py`
- `Whirlpool.emit_promotion_nominations` emits an item only after
  it has dwelled in `CORE` for ≥ `core_dwell_seconds` and
  accumulated ≥ `promotion_corroborator_min` corroborators.
- Items that enter `CORE` but are decayed before meeting dwell
  threshold do NOT emit nominations.

### Router

`tests/test_router_distance.py`
- `DistanceWeights` rejected at load when `sum ≠ 1.0 ± 0.01`.
- `DistanceMetric.d_embed` returns `0.0` for identical vectors and
  `1.0` for antipodal vectors (modulo floating tolerance).
- `d_graph`, `d_causal`, `d_counter` return their configured
  constant (the stubs).
- `DistanceComponents.composite` is a correct dot product.

`tests/test_router_admission.py`
- `resolve_tau` returns per-agent override when present on
  `WeightHost.admission_policy`; falls back to global default
  otherwise.
- `resolve_tau(is_dissenter=True)` returns the dissenter's
  lowered triple (0.5 / 0.2 / 0.2).
- `apply_admission` respects per-tier `k_max` (8 Whirlpool, 3
  Weight-prior).
- `apply_admission(dissenter_moderate_boost=True)` adds 0.1 to
  candidates in the 50–80th distance percentile of the candidate
  pool.
- `draw_long_shot_tail` samples from
  `{trust·relevance ≥ 0.3, distance > median(admitted)}` without
  replacement and proportional to `trust·relevance`. Statistical
  property: over 1,000 trials, observed frequencies match the
  probability vector within a chi-square bound.

`tests/test_router_preamble.py`
- `sanitize_user_prompt` replaces every fence marker with an
  entity escape and is idempotent on already-sanitized input.
- `render_preamble` produces a string whose byte length is below
  `DEFAULT_PREAMBLE_BYTE_CAP`.
- When forced-rotation metadata is provided, the rendered
  `<admission>` block contains the `forced_rotation` key.
- Dropping under the preamble cap removes claims in
  increasing-distance order, not admission order.
- Parsing the rendered preamble's `<admission>` block and
  `<claims>` block as JSON succeeds.

---

## Integration Tests

`tests/test_librarian_integration.py`
- **End-to-end canonization.** Given a pending manifest + body
  and a Scribe with a key in `trusted.json`:
  1. `Scribe.anchor` produces a signed manifest.
  2. `Librarian.commit` persists it.
  3. `Librarian.load(manifest_hash)` returns the same manifest.
  4. `Librarian.head(cartridge_id)` points at the new manifest.
  5. A second Scribe anchor of the same cartridge_id at a higher
     version, with `supersedes=[old_hash]`, updates `head`; the
     old hash is now loadable but marked superseded.
- **Federation round-trip.** Two local Librarian instances with
  matching `trusted.json`. Instance A commits a Cartridge;
  instance B runs a gossip cycle and admits it. A subsequent
  revocation from A propagates to B and is marked refused on B
  within one gossip cycle.
- **Trust-list discrepancy.** Instance A's `trusted.json` contains
  a key absent from B's `trusted.json`. B gossips from A and
  refuses to admit any Cartridge signed by the unknown key; the
  rejection is logged; B's state otherwise unchanged.

`tests/test_whirlpool_integration.py`
- **Ingest → vortex → nomination.** A stub feed server returns a
  known set of items across three publishers. After N cycles,
  the Whirlpool has items at the expected rings with expected
  corroborator counts, and items meeting policy thresholds emit
  nominations. Expired items are not nominated.

`tests/test_router_integration.py`
- **Full bundle assembly.** Given a Librarian with three canned
  Cartridges, a Whirlpool with a small fixed vortex, and a
  stubbed embedder returning deterministic vectors:
  - `ContextRouter.assemble` produces a bundle whose admitted
    claims match the admission math hand-computed from the
    fixture.
  - The pre-admit entry at `data/r2/preadmit/{id}.json` contains
    `session_id`, `agent_name`, `tau`, `distance_weights`, and
    the full admitted/tail/rejected summary.
  - The rendered preamble byte-length respects the cap.
- **Forced rotation selection.** With a synthetic R2 ledger of 30
  sessions (one agent always in-majority, others varied),
  `ContextRouter.assemble` selects that agent as the dissenter
  and renders the widened bundle.
- **No-dissenter case.** With a synthetic R2 ledger where every
  agent's conformity is below the `conformity_floor`, no
  dissenter is selected and no agent receives the widened bundle.
- **Sanitization boundary.** User prompt contains literal
  `<context-bundle>`; the rendered preamble (post-sanitization)
  has exactly one authoritative bundle, and the NCG headless
  baseline path receives the unmodified original prompt.

`tests/test_admission_guard_integration.py`
- **Guard opt-in gate.** With `MAESTRO_CONTEXT_TIERS` unset and
  `GuardConfig.context_tiers_enabled = False`, the `ContextRouter`
  returns an empty bundle and the rendered preamble explicitly
  states "no context admitted."
- **Rate-limit.** After N admissions in the same window, the next
  admission is held and logged.
- **Preamble size cap.** A bundle whose admitted claims would
  exceed the cap has claims dropped in increasing-distance order,
  and the drop is summarized in the admission block.
- **Phantom provenance.** A fixture Weight response cites an
  `id` absent from the pre-admit ledger; the post-hoc check raises
  `phantom_provenance` (severity critical).

---

## Adversarial Stress Matrix

One test per threat in
[`vortex-threat-model.md`](./vortex-threat-model.md) §Threat
Register Summary. Each test is an adversarial scenario that must
produce (a) the expected `ImprovementSignal`, (b) the expected
block or log, and (c) no unintended side effects on unrelated
state. Tests under `tests/test_tier_threats/`.

| Threat | Test file |
|---|---|
| W-1 corroboration flooding | `test_w1_flood.py` |
| W-2 decay poisoning | `test_w2_decay_poison.py` |
| W-3 source-identity spoofing | `test_w3_source_spoof.py` |
| W-4 domain-tag squatting | `test_w4_tag_squat.py` |
| W-5 adversarial decay collapse | `test_w5_monoculture.py` |
| C-1 nomination flooding | `test_c1_nomination_flood.py` |
| C-2 Scribe compromise | `test_c2_scribe_compromise.py` |
| C-3 trust-list tampering | `test_c3_trust_list_tamper.py` |
| C-4 content-hash collision (synthetic) | `test_c4_body_mismatch.py` |
| C-5 supersession misdirection | `test_c5_supersession_delta.py` |
| C-6 revocation abuse | `test_c6_revocation_abuse.py` |
| C-7 federation replay | `test_c7_federation_replay.py` |
| C-8 external pre-signed import | `test_c8_external_import.py` |
| T-1 preamble injection | `test_t1_preamble_inject.py` |
| T-2 preamble tampering | `test_t2_preamble_tamper.py` |
| T-3 trust-field forgery | `test_t3_trust_forgery.py` |
| T-4 provenance spoofing | `test_t4_provenance_spoof.py` |
| T-5 distance-metric manipulation | `test_t5_weight_manip.py` |
| T-6 long-shot tail shaping | `test_t6_tail_shape.py` |
| T-7 preamble size inflation | `test_t7_size_dos.py` |
| T-8 dissenter fingerprinting | `test_t8_dissenter_fp.py` |

Each test carries the threat id in its docstring and links to the
corresponding section in `vortex-threat-model.md`. CI runs the
full matrix on every pull request.

---

## Benchmarks

Benchmarks are non-gating: they report metrics that MAGI consumes
for tuning. Results land in `tests/benchmarks/results/{date}.json`
and are trended over time.

### Admission Quality

Requires a labelled **Query / Admitted-Claim Ground-Truth Set**
(GT set) — a fixture of queries paired with the ideal admitted
claim subset per tier. The GT set is a separate deliverable
(Conflicts §2) and is maintained under
`tests/benchmarks/admission_gt/`.

Metrics per Query:
- **Precision@k**: fraction of admitted claims that are in the
  GT set, at the per-tier `k_max`.
- **Recall@k**: fraction of GT claims that the Router admitted.
- **MAP** (mean average precision) across the GT set.
- **Long-shot tail hit rate**: fraction of sampled tail items
  that are in the GT set. The expected value under random
  distant-sampling is close to zero; consistent non-zero hit
  rate is positive evidence.

### Performance

- **Assembly latency p50/p95/p99** per agent per session, measured
  end-to-end from `BundleRequest` to `ContextBundle`. Target p95
  under 200 ms for a bundle with 3 Cartridges + 8 Whirlpool items.
- **Preamble size distribution**: histogram of rendered preamble
  bytes. Watch for drift toward the cap over time.
- **Librarian `candidates` latency** as a function of Cartridge
  store size (1k / 10k / 100k cartridges).
- **Whirlpool `query` latency** as a function of vortex size
  (100 / 1k / 10k items).

### Decay Correctness

A decay correctness benchmark runs the Whirlpool under a
deterministic synthetic ingest schedule and measures:
- **Ring residence time distribution** per ring matches the
  profile within tolerance.
- **Expected expiry count** per tick matches the decay schedule.
- **Rate-limit efficacy**: items under an induced flood do not
  advance rings faster than policy allows.

---

## Evaluation Cadence

- **Unit + integration + threat matrix**: run on every pull
  request. Block merge on failure. Target: fast (< 60 s total).
- **Benchmarks**: run nightly on `main`. Write results to the
  benchmark store. MAGI's cross-session analysis can consume the
  benchmark history the same way it consumes the R2 ledger.
- **Adversarial stress**: full matrix on PR; property-based fuzz
  of admission and sanitization (hypothesis) in the nightly.
- **Federation integration**: PR on changes to `librarian/` or
  `router/`; nightly for regression.

---

## CI Integration

New test modules register into the existing pytest discovery
(`tests/test_*.py`). The `Makefile` gains one entry:

```
test-tiers:
	pytest tests/test_librarian_*.py tests/test_whirlpool_*.py \
	       tests/test_router_*.py tests/test_tier_threats/ \
	       tests/test_admission_guard_integration.py
```

Existing `Makefile` targets are unchanged. CI invocation: the
existing `tests/` discovery catches everything above without
extra configuration; the `test-tiers` target exists for developer
convenience.

Benchmarks run under a separate `make bench-tiers` target and are
not part of the default `make test` path.

---

## Coverage Targets

- **Unit tests**: ≥ 90% line coverage for `maestro/librarian/*`,
  `maestro/whirlpool/*`, `maestro/router/*`. Coverage reported via
  `pytest --cov`. Gates CI at 85%.
- **Adversarial matrix**: 100% of threats in the register have
  at least one test. Absence is a CI failure.
- **Benchmark stability**: p95 latency regression > 25% vs. the
  prior nightly triggers a `performance_regression` flag in the
  benchmark output. Non-gating; surfaces in operator dashboards.

---

## Open Questions (deferred)

- **Ground-truth set construction.** A small hand-curated GT set
  is a reasonable start; scaling to a useful benchmark requires
  annotated corpora that do not yet exist in this repo.
  Deliverable deferred.
- **Differential testing against a baseline without tiers.**
  Comparing per-session R2 grades on the same prompts with
  context tiers enabled vs. disabled would quantify the system's
  value end-to-end; the harness requires the tiers to be wired
  into the orchestrator (beyond Task 8's scope).
- **Live fuzzing of the federation gossip.** Property-based
  testing of the gossip cycle is worthwhile but is a larger
  effort than this document should prescribe.
- **Chaos testing.** Injecting clock skew, partial-write failures,
  and peer disconnection into integration tests is the correct
  next step after the structural tests land, not before.

---

## See Also

- [`context-tiers.md`](./context-tiers.md) — Three-tier overview
- [`librarian.md`](./librarian.md) — Cartridge schema and
  canonicalization
- [`whirlpool.md`](./whirlpool.md) — Vortex data model and decay
- [`router-distance.md`](./router-distance.md) — Admission function
  and preamble format
- [`distance-dissent.md`](./distance-dissent.md) — Forced rotation
- [`vortex-threat-model.md`](./vortex-threat-model.md) — Threats
  driving the adversarial stress matrix
- [`../self-improvement-pipeline.md`](../self-improvement-pipeline.md)
  — Existing test conventions for the injection pipeline
