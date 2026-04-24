# Vortex Threat Model — Cartridge, Whirlpool, and Preamble Attacks

This document enumerates the attacks specific to the three-tier
context epistemology: manipulation of Whirlpools, poisoning of
Cartridges via the canonicalization pipeline, and tampering with the
trust-annotated preamble on the wire between the Router and the
Weights. It specifies which threats the implementation must address,
which are accepted residual risk, and what extensions the guard
layer (new `AdmissionGuard` module) and the existing
`InjectionGuard` need.

It does *not* repeat threats that apply equally to the pre-existing
Maestro pipeline (agent-key theft, RPC MITM between orchestrator and
Weight APIs, standard FastAPI vulnerabilities). Those are covered
under the existing hardening posture.

---

## Conflicts with existing design

One item to flag for the reader before the threat content.

1. **"InjectionGuard extensions needed" — naming.** The task brief
   asks for InjectionGuard extensions. Under the architecture
   decided in [`context-tiers.md`](./context-tiers.md) §Admission
   guard module (Q2 resolution), context admission is gated by a
   **new module** `maestro/admission.py` (`AdmissionGuard`), which
   composes with — but does not subclass or modify —
   `maestro/injection_guard.py`. Most of this document's "guard
   extensions" section therefore lands on `AdmissionGuard`; a small
   set lands on `InjectionGuard` because canonization, if ever
   automated, becomes a new category of code-adjacent write that
   the existing guard already has the right machinery to bound.
   Both are called out explicitly in §Guard Extensions.

---

## Adversary Model

Four adversary classes are in scope. Each has a different
capability set; mitigations are sized accordingly.

- **External content author (A1).** Publishes material on feeds
  Whirlpools ingest (HTTP/RSS). No Maestro credentials. Cannot
  read private state. Objective: get material admitted at Tier 2,
  or escalate it toward canonization.
- **External peer operator (A2).** Runs a federated Librarian
  instance in the peer list. Holds keys *not* in this instance's
  `trusted.json`. Can serve Cartridges but cannot sign Cartridges
  trusted by this instance.
- **Compromised operator host (A3).** Has filesystem read on
  `data/` but not write on `data/librarian/keys/` (private keys
  require explicit owner action to unlock). Can modify
  `data/runtime_config.json`, plugin configs, and the ingest peer
  list, subject to the existing guard machinery.
- **Compromised Scribe (A4).** Holds a signing key in
  `trusted.json`. Can sign any manifest. Cannot alter previously
  published Cartridge hashes (they are content-addressed), but can
  canonize new Cartridges and issue revocations. This is the
  highest-severity adversary class and most mitigations against it
  are detection-oriented, not prevention-oriented.

**Out of scope**: full supply-chain compromise (adversary controls
the `maestro` source repository itself), physical key extraction
from an offline Scribe device, and adversaries with write access to
`data/r2/preadmit/` or `data/r2/` log entries (those are treated as
authentic audit artifacts; tampering with them is detected by the
existing session-record hashing that is in the R2 post-hoc
invariants and is the subject of separate hardening work).

---

## Whirlpool Manipulation Attacks

These attacks target Tier 2: the vortex of fresh decaying context.
They are the most accessible to external adversaries (A1).

### W-1. Corroboration flooding

**Description.** Adversary publishes the same claim across many
apparently-independent sources so a Whirlpool observes elevated
corroboration and advances the claim toward the inner ring (and
thus toward promotion nominations under
[`whirlpool.md`](./whirlpool.md) §Promotion).

**Mitigations.**
- Whirlpool ingest normalizes source identity by registrable domain
  and by publisher-declared identity headers, de-duplicating
  syndicated feeds. Corroboration counts distinct publishers, not
  distinct URLs. Specified in
  [`whirlpool.md`](./whirlpool.md) §Ingest Policy.
- Fresh publishers (first-seen within the current decay window)
  contribute fractional corroboration weight (default 0.3) rather
  than 1.0. Weight rises with publisher age and with the number of
  that publisher's prior items that did *not* get flagged as
  corroboration-flood suspects.
- `AdmissionGuard` bounds the **rate** at which a Whirlpool item
  can climb rings (default: at most one ring per decay quartile).
  An item observed jumping three rings in one ingest tick is held
  at its current ring and logged as a `rapid_promotion_suspect`
  threat flag.

**Residual risk.** A determined adversary with aged, cooperating
publishers can still produce legitimate-looking corroboration.
Promotion to Cartridge still requires MAGI review + Scribe
signature, so flooding alone does not canonize. The risk is
admission into Tier-2 bundles, which is time-bounded by decay.

### W-2. Decay poisoning

**Description.** Adversary publishes time-sensitive material
intended to enter the vortex, influence admissions during a
critical window (e.g. a specific prompt the adversary expects
users to ask), then decay out of the vortex before detection.

**Mitigations.**
- R2 pre-admit entries (see
  [`router-distance.md`](./router-distance.md) §Storage) record
  every Whirlpool item admitted, with the full item id and source
  provenance, *independent of vortex decay*. Ledger retention is
  not coupled to Whirlpool decay. MAGI's cross-session analysis
  can therefore detect influence after the vortex has forgotten.
- High-rate, narrow-domain ingest bursts are flagged to MAGI for
  `ingest_burst` review. The reviewing threshold is per-domain
  and learned from historical ingest variance.

**Residual risk.** For single-session, narrow-target attacks, the
material may influence *one* orchestration result before detection.
This is the price of live context.

### W-3. Source-identity spoofing

**Description.** Adversary publishes claims under a trusted
publisher's identity (via compromised feed endpoints, DNS, or
similar) to borrow that publisher's corroboration weight.

**Mitigations.**
- HTTPS required for every feed URL. Whirlpool ingest refuses plain
  HTTP and logs the refusal. Exceptions require explicit operator
  allowlist, per-URL.
- Per-source content signatures, when the publisher offers them
  (RSS Atom signatures, HTTP Signatures, etc.), are verified and
  recorded. Absence of signature capability does not disqualify a
  publisher but caps their corroboration weight at 0.6 of a
  signed publisher's weight.
- Content hash consistency: if a publisher's historical hash
  velocity (items per day, mean item length) shifts sharply, MAGI
  receives a `publisher_drift` signal.

**Residual risk.** A publisher whose own infrastructure is
compromised in a way consistent with their history (e.g. slow
infiltration) is undetectable at the Whirlpool layer.

### W-4. Domain-tag squatting

**Description.** Adversary publishes into a Whirlpool's domain
with tags carefully chosen to match high-value queries (e.g. using
the exact dotted tags the Router expects for a legal-question
class), so the adversary's item is relevance-weighted high.

**Mitigations.**
- Per-Whirlpool `ingest_policy` declares the tag namespaces it is
  authoritative for. Tags outside the declared namespaces on an
  ingested item are stripped before the item enters the vortex.
- `AdmissionGuard` refuses to admit Whirlpool items carrying tags
  not declared by their Whirlpool's policy. This is a hard check
  at admission time, not a soft penalty.
- Tag declarations in `ingest_policy` are themselves reviewed by
  MAGI when a new Whirlpool is installed; a Whirlpool declaring
  broad, high-value namespaces (`law.*`, `medical.*`) requires
  `min_signatures_by_kind[whirlpool_policy]` ≥ 2 by default.

**Residual risk.** Within a legitimately declared namespace, a
squatter's items can reach the vortex. Downstream corroboration
requirements and relevance scoring bound their impact.

### W-5. Adversarial decay collapse

**Description.** Adversary correlates publications across
publishers so material for an adversary-chosen claim is always
fresh and material for an opposing claim decays out. The vortex
topology over time presents a biased picture.

**Mitigations.**
- Decay profiles are **symmetric by content class, not by
  adversary choice**: two items of the same `kind` and
  `domain_tags` decay on the same schedule regardless of source.
  Adversaries cannot make their items decay slower by ingestion
  pattern.
- MAGI monitors domain-level claim-diversity shifts in the pre-
  admit ledger (not the vortex). A domain whose pre-admit diversity
  drops below a baseline for N consecutive sessions is flagged
  `domain_monoculture`.
- The Router's forced rotation mechanism (see
  [`distance-dissent.md`](./distance-dissent.md)) is orthogonal
  protection: even if the vortex is biased, the dissenter receives
  widened admission including material the majority didn't see.

**Residual risk.** Over long horizons and coordinated sources, a
biased vortex still shapes baseline assumptions of the Weights'
responses. The Librarian tier is the intended defense: canonized
Cartridges do not decay.

---

## Cartridge Poisoning via the Canonicalization Pipeline

These attacks target Tier 1: the Librarian's canonized, signed,
content-addressed store. The attacks here are harder to mount than
Whirlpool attacks (canonization requires a Scribe signature) but the
impact is much larger (Cartridges do not decay and admit at near-
zero epistemic cost).

### C-1. Nomination flooding

**Description.** Adversary (A1 routed through a Whirlpool, or A3
via direct submission) floods the nomination queue at
`data/librarian/pending/` so MAGI review becomes either overwhelmed
or careless. The attack is denial-of-review before it is poisoning.

**Mitigations.**
- The `AdmissionGuard` rate-limit primitives (ported conceptually
  from `maestro/injection_guard.py:125–136`) apply to nominations
  per source: Whirlpool-source promotions are capped at N per
  decay window, operator submissions are capped at N per hour,
  and external pre-signed imports are unbounded by rate but
  bounded by trusted-key count.
- The review queue is ordered by MAGI-computed priority, not
  chronological order. Under flood, MAGI processes highest-
  priority first. Priority is computed from domain breadth
  (narrow-domain > broad-domain), corroboration count
  (Whirlpool-sourced), and operator-declared priority
  (operator-submitted).
- Flood-suspect nominations accumulate in `pending/` without being
  deleted. An operator running reviews manually can still reach
  them; MAGI is not the only possible reviewer.

**Residual risk.** A sustained flood can delay legitimate
canonization. The system degrades to existing Weight priors plus
Whirlpool material (both of which keep working) during the delay.

### C-2. Scribe compromise (A4)

**Description.** Adversary (A4) holds a key in `trusted.json` and
uses it to canonize an adversary-authored Cartridge.

**Prevention (partial).**
- The Scribe role is separate from MAGI's role by construction
  (see [`librarian.md`](./librarian.md) §Role). A compromised Scribe
  does not imply a compromised MAGI; MAGI still produces its
  Recommendation. An anchored Cartridge whose MAGI Recommendation
  was absent or negative is still Scribe-signed, so the Cartridge
  is admissible — but the absence or negativity is in
  `data/librarian/review/.../magi.json`, which is not written by
  the Scribe and whose absence is detectable.
- `policy.json` supports per-kind threshold signatures. Deployments
  that set `min_signatures_by_kind["statute_text"] = 2` require
  two Scribes to collude.

**Detection.**
- A post-anchor audit checks, for every new Cartridge, that the
  corresponding `data/librarian/review/{id}/{version}/magi.json`
  exists and has a positive verdict. Missing or negative
  verdicts produce a `scribe_anomaly` signal to MAGI (severity
  `critical`).
- Federation peers gossip the new Cartridge with its hash, and
  any peer that runs its own MAGI pass on the imported manifest
  can detect contradictions with their local review baseline;
  federated divergence in verdict is surfaced as
  `federation_verdict_disagreement` (severity `warning`).

**Response.**
- A legitimate Scribe issues a revocation
  ([`librarian.md`](./librarian.md) §Revocation) targeting the
  adversary-signed Cartridge(s).
- The compromised key is removed from `trusted.json` and a new key
  is distributed out of band. Cartridges signed by the removed
  key remain valid in the audit log but no longer admit; replay
  of an R2 entry whose `pre_admit_ref` references such a
  Cartridge is flagged with
  `replayed_after_key_revocation` (severity `warning`).

**Residual risk.** Between compromise and detection, adversary
Cartridges are admitted at Tier-1 trust. Detection latency is the
critical parameter; the post-anchor audit should run on every
anchor, not on a schedule.

### C-3. Trust-list tampering

**Description.** Adversary (A3) modifies `trusted.json` to add an
adversary-controlled key. Any subsequent Scribe signature from that
key is treated as trusted.

**Mitigations.**
- `trusted.json` is itself signed on write by an operator key held
  out-of-band (not in `data/librarian/keys/`). The Librarian
  refuses to load a `trusted.json` whose signature does not verify
  against the operator key fingerprint stored in
  `data/librarian/policy.json`.
- Changes to `trusted.json` are append-only within a session; the
  Librarian records every add/remove with timestamp and operator
  key id in `data/librarian/gossip.log`.
- An in-memory hash of the loaded `trusted.json` is checked against
  the on-disk file every N minutes; divergence produces a
  `trust_list_tampered` signal and the Librarian enters read-only
  mode (refuses new anchors, still serves existing Cartridges).

**Residual risk.** An adversary with simultaneous compromise of the
host filesystem and the out-of-band operator key can alter
`trusted.json` without detection. Collocating those two secrets is
explicitly against the deployment guidance.

### C-4. Content-hash collision abuse

**Description.** Adversary crafts two manifests with the same
`manifest_hash` — one legitimate, one adversary-controlled — and
swaps the body between instances.

**Mitigations.**
- `manifest_hash` is SHA-256 over RFC 8785 canonical JSON
  (`librarian.md` §Content Addressing). Finding a collision is
  infeasible under current cryptographic assumptions; preimage
  resistance is considered adequate for this class of document.
- Storage layout keys by full hash, so two inputs with the same
  hash resolve to the same file. Replacement of an existing
  hash's body content is detected at fetch time by re-hashing the
  body; mismatch is treated as `federation_body_mismatch`
  (severity `critical`), the fetched body is discarded, and the
  source peer is marked `probation`.

**Residual risk.** SHA-256 is believed sound; if a practical
collision or preimage attack emerges, the Librarian's
`canonical_form` registry allows a migration to a stronger hash
under a new `canonical_form` identifier without schema change.

### C-5. Supersession misdirection

**Description.** Adversary canonizes a Cartridge that declares
`supersedes: [legitimate_hash]` but whose body contradicts the
original. Routers that load the legitimate hash would then admit
the successor's inverted content.

**Mitigations.**
- MAGI review of a supersession compares the successor's body to
  the predecessor's in canonical form. Large delta relative to the
  kind's expected edit cadence (statutes rarely rewrite in full,
  for example) raises a `supersession_shape_anomaly` warning that
  the Scribe is instructed to resolve before signing.
- Supersession records carry both the predecessor's and the
  successor's `manifest_hash`. An R2 post-hoc session can detect
  that a consensus was shaped by a Cartridge that was superseded
  shortly afterward by a radically different version; the
  retrospective signal `supersession_altered_outcome` (severity
  `warning`) is fired.

**Residual risk.** A supersession that is legitimately a major
edit (e.g. a protocol RFC errata that reverses a normative
direction) looks identical at the Librarian layer to an adversarial
inversion. MAGI review by a human operator is the intended
safeguard; this is the same reason the task order requires MAGI
stay read-only and the Scribe be separate.

### C-6. Revocation abuse

**Description.** Adversary (A4 or collusion of A4s) issues
revocations for legitimate Cartridges to suppress truth that the
adversary finds inconvenient.

**Mitigations.**
- Revocations are signed and content-addressed like any other
  Cartridge; the same `min_signatures_by_kind["revocation"]`
  threshold applies. A single compromised Scribe cannot revoke
  under a threshold ≥ 2.
- Revocations are **not themselves revocable**
  ([`librarian.md`](./librarian.md) §Revocation): correction is via
  a new, re-signed successor. An adversarial revocation therefore
  leaves a permanent artifact in `data/librarian/revocations/` that
  MAGI's cross-session scan surfaces as
  `revocation_without_successor` when the revoked material has
  not been replaced after T days.
- R2 post-hoc entries whose sessions depended on a revoked
  Cartridge (via `pre_admit_ref`) are re-scored under
  `replayed_after_revocation` (severity `warning`), so MAGI can
  distinguish sessions merely caught by a revocation from those
  that an adversary revocation is intended to bury.

**Residual risk.** An adversary with sustained Scribe access meets
the threshold can permanently revoke at will. Detection depends on
MAGI running regularly and producing the `revocation_without_successor`
signal; detection latency is a parameter.

### C-7. Federation replay

**Description.** Peer operator (A2) re-advertises old Cartridges
whose trust-list entries have since been revoked, hoping to get
them admitted in the current context. Or, peer re-advertises
Cartridges to exhaust local bandwidth / fill gossip logs.

**Mitigations.**
- Trust is per-key per-load, not per-accept-once. A Cartridge that
  was trusted historically and is served again is re-verified
  against the current `trusted.json` at fetch time
  ([`librarian.md`](./librarian.md) §Federation). Revoked signing
  keys do not re-admit older Cartridges.
- Gossip advertisements carry a monotonic sequence per peer
  (stored in `federation/peers.json`). Advertisements with stale
  sequence numbers are ignored; flood advertisements with
  rapidly-repeating sequences are throttled.

**Residual risk.** A peer operator willing to sustain advertising
costs can waste some bandwidth. The impact does not reach the
admission path.

### C-8. External pre-signed import

**Description.** An external canonization authority whose key is in
`trusted.json` is compromised, and publishes Cartridges the local
MAGI would have rejected. Because the key is trusted, the import
flow ([`librarian.md`](./librarian.md) §Nomination) skips local
MAGI review.

**Mitigations.**
- Policy allows enabling MAGI review on external imports by
  setting `policy.json["review_external_imports"] = true`.
  Deployments in high-stakes domains are expected to enable this.
  The flag is off by default to avoid review-queue pressure for
  routine protocol/RFC imports.
- Per-key import caps: `policy.json["import_caps_by_key"]`
  specifies a max imports per key per day. An external authority
  that suddenly bursts is capped and the excess is held for
  review.
- Post-import audit: for every imported Cartridge, a deferred
  `external_import_review` MAGI pass runs. It does not block
  admission (the import was already trusted) but produces a
  retrospective `external_import_anomaly` signal that can feed
  into `trusted.json` key removal.

**Residual risk.** Deployments with `review_external_imports` off
and no post-import audit running are exposed to the full trust of
the compromised key until the deferred audit runs. The windows are
tunable.

---

*(End of chunk 2 — Cartridge poisoning. Next: trust-annotation and
preamble tampering.)*
