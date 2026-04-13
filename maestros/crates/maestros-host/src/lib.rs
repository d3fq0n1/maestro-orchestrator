//! MaestrOS userspace host runtime (Path A).
//!
//! Owns the Tokio runtime, wires the core/proto/proof/embed/lance/mesh/
//! quorum crates together, and exposes a local control socket. Boots as
//! a systemd unit on Raspberry Pi OS Lite for v0; the Buildroot/Yocto
//! custom-image flex lands in v0.2.
//!
//! Architectural invariant: every std-only concern (async runtime, I/O,
//! filesystem, network stack) lives in this crate or its dependencies.
//! `maestros-core`, `maestros-proto`, and `maestros-proof` remain
//! `no_std` so Path B/C (unikernel, bare-metal kernel) stays reachable
//! by swapping `maestros-host` for a bare-metal sibling crate without
//! touching the core.

pub mod runtime {}
pub mod control_socket {}
pub mod maestro_shim {}
