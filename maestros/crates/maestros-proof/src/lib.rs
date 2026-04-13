//! MaestrOS capability proofs.
//!
//! Direct port of `maestro/storage_proof.py` (PoRep, PoRes, PoI) with
//! ed25519-signed capability manifests layered on top. Every capability
//! advertisement on the mesh is a signed attestation; every intent carries
//! proof of the capability it is exercising.
//!
//! Designed to be `no_std`-friendly so the same proof checks can run on
//! the eventual bare-metal kernel. BLS aggregation is an explicit hole
//! for later versions where gossip volume makes per-message signing hot.

#![no_std]

extern crate alloc;

pub mod porep {}
pub mod pores {}
pub mod poi {}
pub mod sign {}
pub mod manifest {}
