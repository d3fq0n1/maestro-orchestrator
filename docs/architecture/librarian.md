# Librarian — Tier 1 Cartridge System

The Librarian is the component that owns Tier 1 of the three-tier
context epistemology (see [`context-tiers.md`](./context-tiers.md)). It
holds, serves, and federates **Cartridges** — immutable, content-addressed,
signed context modules representing known-truths that have been canonized.

A Cartridge is not a retrieval result. It is a published artifact with
identity, provenance, and a supersession history. The Router loads
Cartridges by reference at near-zero epistemic cost: their trust is
already adjudicated.

This document specifies: the manifest schema, the content-addressing
scheme, the signature / attestation model, the canonicalization
pipeline (nomination → MAGI review → Scribe anchoring → canonization
→ supersession/revocation), the on-disk storage layout, and the
federation protocol. No code.

---

## Conflicts with existing design

Three decisions were resolved before drafting.

1. **Canonization authority.** MAGI today produces `Recommendation`
   objects read-only (`maestro/magi.py:35–41`); it does not hold
   signing keys. The Librarian introduces a **Scribe**: a separate
   authority that holds Cartridge signing keys. MAGI proposes
   canonization; the Scribe verifies the proposal and signs. This
   preserves MAGI's read-only character (the ethical principle at
   `maestro/magi.py:14–16`) while giving the Librarian an attestable
   authority. The Scribe is a role, not a new agent — it can be
   operated by one human, a quorum of humans, or a future automated
   layer with explicit sign-off semantics.

2. **Key storage.** `maestro/keyring.py` manages API keys for the
   council (GPT-4o, Claude, Gemini, Llama) and is not suited for
   signing keys. The Librarian uses a new dedicated key store at
   `data/librarian/keys/` with Ed25519 signatures. `keyring.py` is
   untouched.

3. **Federation transport.** Maestro already has LAN peer discovery
   (`maestro/lan_discovery.py`). The Librarian layers gossip on top
   of the existing discovery mesh plus HTTP fetch for content. No
   new network stack; no libp2p / DHT introduction. Cross-LAN
   federation is explicit peering (operator-configured URL list),
   not automatic discovery across the public internet.

---

## Cartridge Taxonomy

Cartridges have a `kind` that informs default Router weighting and
revocation semantics. The initial kinds:

| Kind | Example | Immutable on anchor? | Supersession cadence |
|---|---|---|---|
| `unit_definition` | SI prefixes, imperial conversions | Yes | Rare (decades) |
| `statute_text` | 42 U.S.C. §1983 at 2024-01-01 enactment | Yes, at version | On amendment |
| `protocol_spec` | RFC 9110 §3.4 | Yes, at RFC | On errata / bis |
| `schema` | Maestro R2LedgerEntry v7.4 | Yes, at version | On version bump |
| `definition` | Mathematical definition, term-of-art | Yes | Rare |
| `reference_dataset` | A fixed lookup table | Yes | On republication |

A Cartridge is *not* a free-text document. Every kind has a validator
and a canonical-form serializer (see §Manifest Schema). New kinds are
added by extending the Scribe's validator registry; this is a manifest-
and-validator change, not a schema migration.

---

## Manifest Schema

Every Cartridge is a pair: **manifest** (JSON, signed) + **body**
(opaque bytes addressed by hash). Both are needed to load a Cartridge.

Manifest fields:

- `cartridge_id: str` — stable human-readable slug (e.g.
  `si-prefixes`, `rfc9110-section-3-4`). Uniqueness is enforced per
  Librarian instance.
- `version: str` — monotonically increasing version tag
  (`2024.01.01`, `v1.2.0`). The Scribe rejects a version that is not
  strictly greater than the current head of this `cartridge_id`
  unless the manifest is a declared supersession of a different
  `cartridge_id` (see §Supersession).
- `kind: str` — one of the taxonomy entries above. The Scribe
  rejects if the validator for this kind fails on `body`.
- `content_hash: str` — `"sha256:<hex>"`. Computed over the
  canonical-form body. See §Content Addressing.
- `manifest_hash: str` — `"sha256:<hex>"`. Computed over the manifest
  with the `manifest_hash` and `signatures` fields removed (see
  §Content Addressing). This is the primary address of the Cartridge.
- `canonical_form: str` — identifier of the canonical-form
  serializer used for `body` (e.g. `json/rfc8785`, `text/utf8-nfc`,
  `bytes/raw`). The Scribe applies this serializer before hashing
  so two semantically identical bodies hash to the same value.
- `supersedes: list[str]` — zero or more `manifest_hash` values
  this Cartridge replaces. Routers that load a superseded hash
  issue a diagnostic and admit the successor instead (unless the
  successor is revoked).
- `revokes: list[str]` — `manifest_hash` values this Cartridge
  withdraws without replacement. Used for canonized errata retraction.
- `domain_tags: list[str]` — Whirlpool-compatible domain strings
  used by the Router for relevance scoring and by `WeightHost` for
  subscription matching.
- `issued_at: str` — ISO8601 UTC timestamp of Scribe signing.
- `not_before: str | null` — optional time at which the Cartridge
  becomes admissible. Used for embargoed canonization (e.g. a statute
  whose effective date lies in the future).
- `not_after: str | null` — optional expiry. Typically null for
  canonized material; used only when known-truths have a declared
  sunset (sunset clause in a statute, protocol RFC marked obsolete).
- `signatures: list[Signature]` — see §Attestation.
- `metadata: dict` — free-form, unsigned extras (origin URL, human
  title, description, contributor names). Untrusted; never used in
  Router scoring.

Two invariants are enforced at anchor time:

- `manifest_hash` is a function of every field except itself and
  `signatures`. This means the signatures certify the hash, and the
  hash identifies the manifest. Any tamper breaks both.
- `content_hash` is a function of the canonical-form `body`. The
  body bytes are not required to be stored inside the manifest — the
  manifest simply references them.

---

## Content Addressing

### Body addressing

`content_hash` is the SHA-256 of the canonical-form bytes of `body`.

- For `canonical_form = "json/rfc8785"`: RFC 8785 JSON Canonicalization
  Scheme. Sorted keys, no whitespace, normalized numbers. Deterministic.
- For `canonical_form = "text/utf8-nfc"`: Unicode NFC normalization,
  LF line endings, UTF-8 encoding, no BOM.
- For `canonical_form = "bytes/raw"`: the body is treated as opaque;
  the caller is responsible for determinism. Used only for
  `reference_dataset` kinds that ship a pre-hashed blob.

New canonical forms are added to the Scribe's registry alongside a
validator; a Librarian that does not recognize a `canonical_form`
refuses to admit the Cartridge.

### Manifest addressing

`manifest_hash` is the SHA-256 of the RFC 8785 canonicalization of
the manifest with the `manifest_hash` and `signatures` fields elided.
Signatures sign this value. The hash is the Cartridge's primary
identity across the federation.

### Supersession vs. mutation

Once a `manifest_hash` is published, it is immutable. A correction
is a *new* Cartridge with `supersedes: [<old_hash>]`. This is the
only mechanism. There is no "edit Cartridge" operation anywhere in
the Librarian.

---

## Attestation — The Scribe

### Role

The Scribe holds the Ed25519 signing keys that attest Cartridges as
canonized. The role is separate from MAGI and separate from the
orchestrator. In a minimal deployment the Scribe is the operator's
laptop running a signing tool. In a production deployment the Scribe
can be a quorum of key-holders whose signatures combine into a
threshold signature.

MAGI's `Recommendation` objects reach the Scribe as canonization
proposals; MAGI cannot sign, and a Cartridge without a Scribe
signature is not canonized (Routers reject unsigned Cartridges
outright).

### Keys

- Algorithm: Ed25519.
- Storage: `data/librarian/keys/`, one file per key, filename
  `{key_id}.ed25519.pem`. Public keys in `data/librarian/keys/public/`.
- The private-key files are mode `0600` and the directory is `0700`;
  if ownership or mode is wrong, the Scribe tool refuses to load.
- A `data/librarian/keys/trusted.json` file enumerates the public
  keys this Librarian instance trusts for signing. A Cartridge is
  admitted only if every `Signature.key_id` in its `signatures` list
  is present in `trusted.json`.

`maestro/keyring.py` (API keys for Weights) is untouched. It and
the Librarian key store share no code path.

### Signature record

```
Signature {
  key_id: str            // fingerprint of the signing public key
  algo: "ed25519"
  sig: str               // base64-encoded signature over manifest_hash
  signed_at: str         // ISO8601 UTC
  role: str              // "scribe" (reserved: "supersession-witness",
                         //           "revocation-witness")
}
```

### Threshold policy

`data/librarian/policy.json` specifies a minimum signature count per
`kind`. The default `min_signatures = 1`. Deployments that require
`statute_text` to be co-signed by two Scribes set
`min_signatures_by_kind["statute_text"] = 2`. The Scribe tool refuses
to anchor below the threshold; the Router refuses to admit below the
threshold at load time (defense in depth).

---

## Canonicalization Pipeline

```
Nomination  ─►  MAGI review  ─►  Scribe anchoring  ─►  Canonization
                                                              │
                                     Supersession  ◄──────────┤
                                                              │
                                     Revocation    ◄──────────┘
```

### 1. Nomination

A nomination proposes that a piece of material be canonized. Sources:

- A Whirlpool pushes an inner-ring claim that has accumulated
  sufficient corroboration (see [`whirlpool.md`](./whirlpool.md)
  §Promotion).
- An operator submits a manifest + body via the Librarian API.
- An external canonization authority (e.g. an institution publishing
  a reference dataset) submits a pre-signed Cartridge; in that case
  nomination and anchoring collapse into an import operation
  provided the external key is in `trusted.json`.

A nomination produces a pending manifest (unsigned) and a body at
`data/librarian/pending/{cartridge_id}/{version}/`.

### 2. MAGI review

MAGI reads the pending manifest and, for internally sourced
nominations (Whirlpool promotions, operator submissions), runs its
analysis pipeline (`maestro/magi.py`):

- Does this material conflict with an existing canonized Cartridge?
  If yes, is this a supersession or a contradiction?
- Is the `kind` validator satisfied?
- Are corroboration and provenance sufficient (Whirlpool-sourced
  nominations only)?
- Are the `domain_tags` coherent with existing tagged material?

MAGI emits a `Recommendation` (`maestro/magi.py:36–41`) with category
`cartridge_canonization` and a pass/fail verdict plus evidence. MAGI
cannot sign. The Recommendation is written to
`data/librarian/review/{cartridge_id}/{version}/magi.json`.

Externally sourced, pre-signed Cartridges skip this step provided the
signing key is trusted.

### 3. Scribe anchoring

The Scribe reads the pending manifest and MAGI's Recommendation (if
present). If the Scribe is satisfied, it:

- applies the canonical-form serializer to `body`,
- computes `content_hash` and `manifest_hash`,
- signs `manifest_hash`,
- atomically moves the manifest + body from `pending/` to the live
  store (see §Storage Layout).

The Scribe is offline-capable: it can read pending manifests from
disk, sign, and write back without touching the network.

### 4. Canonization

Once anchored, the Cartridge is loadable by any Router that trusts
the signing key. Canonization does not imply federation — a Cartridge
is canonized locally and propagates via gossip (see §Federation).

### 5. Supersession

A supersession is simply a new Cartridge whose `supersedes` list
names one or more prior `manifest_hash` values. The Scribe verifies
that:

- every referenced hash exists locally or in a trusted federation
  peer,
- the new `cartridge_id` + `version` either matches a predecessor's
  `cartridge_id` with a strictly greater `version`, or explicitly
  declares a rename in `metadata.previous_id`.

Routers that encounter a superseded hash issue a `superseded`
diagnostic through the admission ledger (see
[`context-tiers.md`](./context-tiers.md) §R2 pre-hoc role) and admit
the successor. Superseded Cartridges are not deleted — they remain
loadable for reproducibility of prior R2 entries.

### 6. Revocation

A revocation is a Cartridge of `kind: revocation` whose body is
empty and whose `revokes` list names the hashes being withdrawn. A
revocation is itself content-addressed and signed; it propagates
over federation the same way a regular Cartridge does.

A revoked hash is refused by the Router even if the bytes remain on
disk. Replay of an R2 entry whose `pre_admit_ref` names a revoked
Cartridge is marked with a `replayed_after_revocation` diagnostic.

Revocations are never themselves revoked. A mistaken revocation is
corrected by issuing a *new* Cartridge that the revoked one would
have named, not by undoing the revocation record.

---

## Storage Layout

All Librarian state lives under `data/librarian/`, siblings to the
existing `data/r2/`, `data/sessions/`, `data/storage_nodes/` trees.

```
data/librarian/
  keys/
    {key_id}.ed25519.pem            # private (mode 0600)
    public/
      {key_id}.ed25519.pub          # public
    trusted.json                    # federation-wide trust list
  policy.json                       # threshold + canonical-form registry
  pending/
    {cartridge_id}/
      {version}/
        manifest.json               # unsigned
        body                        # raw body (pre-canonicalization)
  store/
    by-hash/
      {aa}/{manifest_hash}.json     # signed manifest
      {aa}/{content_hash}.body      # canonical-form body
    by-id/
      {cartridge_id}/
        head -> ../../by-hash/{aa}/{manifest_hash}.json
        versions/
          {version} -> ../../by-hash/{aa}/{manifest_hash}.json
  review/
    {cartridge_id}/{version}/magi.json   # MAGI Recommendation
  revocations/
    {aa}/{manifest_hash}.json       # revocation manifests (also in by-hash/)
  federation/
    peers.json                      # operator-configured peer URLs
    gossip.log                      # append-only federation event log
```

The `by-hash` tree is the ground truth. `by-id/head` is a mutable
symlink updated atomically on anchor or supersession. The `{aa}`
shard prefix is the first two hex chars of the hash (256 top-level
directories) for filesystem sanity.

---

## Federation Protocol

### Peering model

Each Librarian instance has a `federation/peers.json` list of peer
URLs. Discovery is via:

- `maestro/lan_discovery.py` on the local LAN (automatic),
- operator-configured peer URLs for cross-LAN (explicit).

No DHT. No public cross-instance discovery. A Librarian federates
only with declared peers.

### Gossip cycle

On a tunable interval (default 60 s) each Librarian runs a gossip
cycle with each peer:

1. **Advertise**: POST `/librarian/federation/advertise` with a
   compact list of `(manifest_hash, kind, version)` tuples for the
   N most-recently-anchored Cartridges and for all revocations
   (revocations are always re-advertised until acknowledged).
2. **Diff**: the peer replies with the subset of hashes it has not
   yet seen.
3. **Fetch**: for each missing hash, GET
   `/librarian/federation/manifest/{manifest_hash}` and, if the
   manifest passes signature verification, GET
   `/librarian/federation/body/{content_hash}`.
4. **Verify and admit**: verify Scribe signatures against
   `trusted.json`; verify `content_hash` matches the fetched body.
   If anything fails, the fetch is discarded and logged at
   `federation/gossip.log`.

Revocations are priority-propagated: every gossip cycle re-advertises
every revocation the local instance holds, and a peer receiving a
revocation for a hash it holds writes it to the store and marks the
target refused immediately (before signature verification completes,
the target is held in quarantine).

### Trust is per-key, not per-peer

A peer can serve a Cartridge, but a Cartridge is admitted only if
its signatures verify against the local `trusted.json`. A
compromised peer cannot introduce a new trusted Cartridge; it can
only replay Cartridges already signed by keys this instance trusts,
which the hash-based dedupe handles idempotently.

### Keyring updates

`trusted.json` is updated out of band (operator action). A signed
"trust-bundle" format is explicitly out of scope for this
specification; operators exchange public keys via whatever channel
they trust (signed email, in-person, an existing PKI).

---

## Integration with Maestro

### Router

The Router calls a Librarian lookup function during bundle assembly:

```
Librarian.candidates(query_domains, kind_filter) -> list[CartridgeRef]
```

The returned `CartridgeRef` carries `manifest_hash`, `content_hash`,
`kind`, `domain_tags`, and the computed trust score (derived from
signature count, kind, and revocation status). The Router then
applies the admission function from
[`context-tiers.md`](./context-tiers.md) §Admission function.

### WeightHost

`WeightHost.loaded_cartridges` (see
[`context-tiers.md`](./context-tiers.md) §WeightHost capability
extensions) is a list of `manifest_hash` values. The Librarian
exposes `Librarian.preload(host_id, manifest_hash)` so a host can
declare which Cartridges it has pre-admitted into its working
memory. Routing prefers hosts that already hold the relevant
Cartridges.

### R2

The post-hoc `R2LedgerEntry` records which Cartridge hashes the
session used via its `pre_admit_ref` link (see
[`context-tiers.md`](./context-tiers.md) §R2 pre-hoc role). If any
of those hashes is subsequently revoked, MAGI's cross-session
analysis surfaces the affected sessions as a new signal type,
`cartridge_revoked_in_history` (severity `info` when the session
grade was unaffected, `warning` when a revoked `statute_text` or
`protocol_spec` shaped the consensus).

### MAGI

MAGI gains a new `Recommendation.category = "cartridge_canonization"`
for Whirlpool promotions and operator submissions. The recommendation
is written under `data/librarian/review/` and is the input to the
Scribe's anchoring tool. MAGI never signs.

### Existing modules untouched

- `maestro/keyring.py` (API keys) — no changes.
- `maestro/injection_guard.py` — no changes. Cartridge admission is
  gated by `AdmissionGuard` (see
  [`context-tiers.md`](./context-tiers.md)), not by `InjectionGuard`.
- `maestro/lan_discovery.py` — gains a new service advertisement
  type (`librarian`) but its discovery protocol is unchanged.

---

## Open Questions (deferred)

- Validator registry for each `kind` — exact schemas are kind-
  specific and out of scope for this document.
- Scribe quorum / threshold-signature implementation — the policy
  is specified here; the cryptographic mechanism (e.g. FROST
  Ed25519) is an implementation detail.
- Trust-bundle signed format for exchanging `trusted.json` updates
  out of band — explicitly out of scope.

---

## See Also

- [`context-tiers.md`](./context-tiers.md) — Three-tier overview
- [`whirlpool.md`](./whirlpool.md) — Tier 2 promotion source for
  internal Cartridge nominations
- [`router-distance.md`](./router-distance.md) — How the Router
  scores and admits Cartridge candidates
- [`vortex-threat-model.md`](./vortex-threat-model.md) — Cartridge
  poisoning attacks and mitigations
- [`../magi.md`](../magi.md) — MAGI's role as non-signing reviewer
- [`../architecture.md`](../architecture.md) — System overview
