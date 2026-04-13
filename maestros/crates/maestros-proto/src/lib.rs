//! MaestrOS wire format.
//!
//! Typed intent envelopes (CBOR on the wire, zero-copy friendly in memory),
//! capability manifest encoding, and mesh gossip message shapes.
//!
//! Header layout is versioned from day one so that the v0 fixed embedding
//! model (`nomic-embed-text-v1.5`, 768d) can coexist with per-domain models
//! introduced in later revisions without a wire break.
//!
//! `no_std` for the same reason as `maestros-core`: the wire format must
//! be parseable from any environment MaestrOS can run in.

#![no_std]

extern crate alloc;

pub mod envelope {}
pub mod manifest {}
pub mod gossip {}
