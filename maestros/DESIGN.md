# MaestrOS — Design Record v0.0.1

> **MaestrOS is the operating-system substrate of the Maestro Orchestration Model.**
> Intent is the kernel abstraction. The vector database is the canonical
> address space. Decentralized synthesis of intelligence is the thesis;
> everything else is negotiable.

This document captures the decisions locked in during the initial
scoping conversation. It is the authoritative record until superseded.

---

## 1. Name

**MaestrOS** (pronounced "mah-ES-tross"). Plural of Maestro + OS.
The name is self-documenting: it is Maestro, as an operating system.
All branding inherits from the existing Maestro project; the narrative
is continuous, not forked.

Prior Maestro documentation used the working name **telOS** for this
substrate. That name is deprecated as of this record. All references
in `ARCHITECTURE.md`, `ROADMAP.md`, `changelog.md`, whitepapers, and
source comments have been updated to MaestrOS.

---

## 2. Relationship to Maestro

MaestrOS is the **substrate**, not a replacement.

 * The Python Maestro orchestrator becomes a client of `maestrosd`
   over a local control socket during the transition.
 * Maestro's dashboard, TUI, agent adapters, and clustering tooling
   keep working throughout Phase 8 (Rust port) and into Phase 9
   (MaestrOS substrate integration).
 * No component of Maestro is deleted until behavioral parity with
   its Rust counterpart has been verified.

---

## 3. Path

Three possible interpretations of "operating system" were considered:

| Path | What it is | Status |
|------|-----------|--------|
| **A** | Userspace Rust runtime on Linux. `maestrosd` owns scheduling, addressing, persistence, dispatch. Linux is a driver shim. | **v0 target.** |
| **B** | Unikernel / custom init. Boot directly into a Rust binary; no systemd, no shell, no filesystem hierarchy exposed. | Reachable from A by swapping `maestros-host` for a `maestros-bare` sibling. |
| **C** | Native microkernel with intent-addressed ABI. No POSIX syscalls. Capabilities resolved by semantic proximity. | **Long-term terminus.** The core workspace crates are architected so this path remains viable without rewriting the substrate. |

**Architectural invariant enforced to keep C reachable:**
`maestros-core`, `maestros-proto`, and `maestros-proof` are
`no_std + alloc`. Anything that touches a Tokio runtime, a socket,
a filesystem, or a Candle tensor lives in higher crates.

---

## 4. Intent Shape

**Decision:** typed wire format (shape **B**) + natural-language
convenience layer (shape **C**) at the edge.

 * Intents travel on the wire as typed envelopes with an embedded
   vector attached. CBOR via `ciborium` for the v0 encoding.
 * Natural-language strings arrive at the runtime boundary, get
   embedded on arrival, and from that point forward travel as
   fully-typed intents.
 * Every envelope header carries `(model_id, model_version, dim)`
   from v0.0.1 so per-domain models can be added later without a
   wire break.

Rationale: pure vector-only (shape A) is a debugging nightmare.
Pure natural-language (shape C) ties every hop to the embedding
model. B+C is the pragmatic seam.

---

## 5. Embedding Model

**v0 fixed model:** `nomic-embed-text-v1.5`
 * 768-dim native, Matryoshka-truncatable to 512 / 256 / 128.
 * Candle is the primary backend; `ort` (ONNX Runtime) is the NPU
   fallback for Jetson / Hailo targets.
 * Sub-50 ms per short text on the Raspberry Pi 5's Cortex-A76.

**Long-term goal:** per-domain models. Versioning is baked into the
envelope header from day one; introducing a second model is a config
change, not a wire break.

---

## 6. Vector Store

**LanceDB.** Rust-native, columnar, on-disk, versioned tables.
The substrate maintains two tables:

 * `capabilities` — the address space. k-NN from intent vector to
   capability provider. Signed manifest rows with freshness metadata
   and proof columns. Resolving an intent is a vector search plus a
   policy filter.
 * `ledger` — the epistemic ledger. Append-only, time-decayed record
   of every intent, outcome, R2 score, and quorum decision. This is
   the audit trail **and** a query corpus: the system can learn from
   its own history by vector-searching its past.

The equation "epistemic ledger = vector index" is made literal here.

---

## 7. Proof / Trust Model

**Storage Proof + cryptographic backing.**

 * Direct port of `maestro/storage_proof.py` (PoRep, PoRes, PoI) to
   Rust as `maestros-proof`.
 * `ed25519-dalek` for capability-manifest signing.
 * Merkle-over-SHA256 for PoRep.
 * BLS aggregation is an explicit hole for a later revision where
   gossip volume makes per-message signing hot.

Every capability advertisement on the mesh is a signed attestation;
every intent carries proof of the capability it is exercising.

---

## 8. Mesh Transport

 * **QUIC via Quinn** — encrypted, multiplexed, low-latency streams.
 * **SWIM gossip via `foca`** — membership, failure detection, and
   capability-manifest propagation.
 * LAN broadcast for discovery in v0. Nothing on the public internet
   until the proof model and policy filter are battle-tested.

---

## 9. Deployment — v0

**Target:** 2-node heterogeneous mesh.

| Node | Hardware | Role |
|------|----------|------|
| 1 | Raspberry Pi 5 (8 GB) + NVMe SSD | Edge / router / light inference / address-space holder |
| 2 | Jetson Orin Nano Super (8 GB) | Heavy WeightHost (7B-class local inference via llama.cpp-CUDA) |

**OS layer:** `maestrosd` runs as a **systemd unit** on
Raspberry Pi OS Lite (Node 1) and Linux4Tegra (Node 2). Custom
Buildroot / Yocto images are deferred to v0.2.

**Approximate cost:** ~$461, including switch and cables. Hailo-8L
AI HAT on the Pi is deferred to ~month 3 once the core mesh works.

---

## 10. Semantic Consensus

The existing Maestro quorum stack (dissent analysis, NCG drift
detection, R2 session grading, MAGI supermajority gating) is ported
**faithfully first** as `maestros-quorum`. Behavioral parity with the
Python reference is the Phase 8 acceptance test.

Improvements are allowed after parity has been demonstrated. The
load-bearing thesis is "decentralized synthesis of intelligence";
the specific quorum mechanics may evolve.

---

## 11. Workspace Layout

```
maestros/
├── Cargo.toml                # workspace root
├── DESIGN.md                 # this file
├── README.md
├── rust-toolchain.toml       # stable, aarch64 target
└── crates/
    ├── maestros-core/        # no_std + alloc. Intent, Capability, traits.
    ├── maestros-proto/       # no_std. Wire format (CBOR).
    ├── maestros-proof/       # no_std where possible. PoRep/PoRes/PoI + ed25519.
    ├── maestros-embed/       # std. Candle-backed embedding. Swappable backend.
    ├── maestros-lance/       # std. LanceDB address space + ledger.
    ├── maestros-mesh/        # std. Quinn + foca.
    ├── maestros-quorum/      # std. Port of dissent/ncg/r2/magi.
    ├── maestros-host/        # std. Tokio runtime. Boots maestrosd. PID-1 capable.
    └── maestrosd/            # the binary. Thin main().
```

The seam between `no_std` and `std` crates is the load-bearing
architectural choice. It is the thing that keeps Path C reachable.
Do not blur it.

---

## 12. Known Open Items

 * **v0.2** — Custom Buildroot / Yocto image. Currently using stock
   distros to keep the core loop focused.
 * **Hailo-8L NPU HAT** — deferred to ~month 3. `ort` backend hook
   exists in `maestros-embed` from day one so the integration is a
   backend swap, not a refactor.
 * **BLS signature aggregation** — explicit hole in `maestros-proof`.
 * **Cross-model intent comparison** — the per-domain embedding goal
   requires a policy for comparing vectors produced by different
   models. Not solved in v0; the envelope header records the model
   so the comparison can be rejected safely until a policy exists.
 * **Public internet exposure** — not until v0.3 at the earliest.

---

## 13. Conversation Trail

The decisions above were reached in a scoping conversation with
the project author. Key forcing functions:

 * "A launch point, C terminus" — decided the no_std/std seam.
 * "MaestrOS is the OS layer of Maestro" — decided the substrate
   relationship and the non-destructive transition strategy.
 * "Intent = B + C" — decided the wire format shape.
 * "Fixed embedding, per-domain goal" — forced the versioned header.
 * "LanceDB" — resolved the vector-store choice.
 * "Storage Proof + crypto" — forced ed25519 + Merkle layering.
 * "Mesh v0" — forced the Pi 5 + Jetson Orin Nano Super rig.
 * "$500, 2 months" — bounded the scope to what one person can
   actually ship on real hardware in a quarter.
 * "MaestrOS" — replaced the working name telOS after a naming
   review. The name encodes the thesis (plural of Maestro + OS)
   and inherits existing branding.

This design record is the canonical source of truth for v0.0.1.
Updates supersede by date.
