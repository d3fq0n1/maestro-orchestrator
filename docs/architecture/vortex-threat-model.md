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

*(End of chunk 1 — adversary model and Whirlpool attacks. Next:
Cartridge poisoning via the canonicalization pipeline.)*
