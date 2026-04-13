//! MaestrOS mesh transport.
//!
//! QUIC (via Quinn) for encrypted, multiplexed, low-latency inter-node
//! channels. SWIM gossip (via `foca`) for membership, failure detection,
//! and capability manifest propagation.
//!
//! Nodes discover each other via LAN broadcast (v0) and exchange signed
//! manifests on join. An intent arriving at any node can be resolved
//! locally (k-NN against the local address-space mirror) and hopped
//! to the chosen provider over a QUIC stream.

pub mod transport {}
pub mod gossip {}
pub mod discovery {}
