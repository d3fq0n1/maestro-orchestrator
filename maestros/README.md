# MaestrOS

> The operating-system substrate of the Maestro Orchestration Model.
> Intent is the kernel abstraction. The vector database is the
> canonical address space. Written in Rust. Targets Raspberry Pi 5
> and Jetson Orin Nano Super as the v0 reference mesh.

**Status:** v0.0.1 skeleton. Workspace seams are in place; crate
bodies are stubs. Phase 8 (Rust port of Maestro core) and Phase 9
(MaestrOS substrate) work lands here incrementally.

This directory is a Cargo workspace sitting alongside the Python
Maestro project. It does **not** replace Maestro; it is the substrate
Maestro will eventually run on top of. See
[`DESIGN.md`](./DESIGN.md) for the full decision record.

## Layout

| Crate | no_std? | Purpose |
|-------|---------|---------|
| `maestros-core`   | yes | Intent, Capability, AddressSpace, Scheduler traits |
| `maestros-proto`  | yes | Wire format (CBOR envelopes, manifests, gossip) |
| `maestros-proof`  | yes | PoRep / PoRes / PoI + ed25519-signed manifests |
| `maestros-embed`  | no  | Candle-backed `nomic-embed-text-v1.5` |
| `maestros-lance`  | no  | LanceDB address space + epistemic ledger |
| `maestros-mesh`   | no  | Quinn (QUIC) + foca (SWIM gossip) |
| `maestros-quorum` | no  | Faithful port of Maestro dissent / NCG / R2 / MAGI |
| `maestros-host`   | no  | Tokio runtime; boots `maestrosd` on Linux |
| `maestrosd`       | no  | Thin daemon binary |

The `no_std` crates are the load-bearing architectural seam. They
exist so that a future `maestros-bare` crate can replace
`maestros-host` for a unikernel or native-kernel target without
rewriting the substrate.

## Target Hardware (v0 mesh)

 * **Node 1:** Raspberry Pi 5, 8 GB, NVMe SSD — edge router / address-space holder
 * **Node 2:** Jetson Orin Nano Super, 8 GB — heavy WeightHost (7B-class local inference)

See [`DESIGN.md`](./DESIGN.md) §9 for the shopping list and rationale.

## Building

```
cd maestros
cargo check --workspace
```

v0.0.1 is stubs only; `cargo check` should succeed with zero warnings.
Real logic lands in subsequent commits as Phase 8 work progresses.

## Branch

All MaestrOS development currently lives on
`claude/telos-kernel-exploration-xSEfp`. The branch name predates the
MaestrOS rename and is retained for commit-history continuity.
