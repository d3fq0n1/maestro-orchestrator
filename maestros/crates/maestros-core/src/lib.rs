//! MaestrOS core primitives.
//!
//! This crate is `no_std + alloc` by design. It defines the shape of
//! the intent-addressed substrate without committing to any runtime,
//! transport, storage, or I/O. Everything that touches the outside
//! world lives in a higher crate that depends on this one.
//!
//! The seam enforced here is what keeps Path C (native kernel) reachable
//! later: anything in `maestros-core` must be implementable on bare metal.

#![no_std]

extern crate alloc;

// Module stubs. Types and traits go in here once we start writing logic.
// Intentionally empty for v0.0.1 — this file exists to establish the
// workspace seam, not to carry behavior.

pub mod intent {}
pub mod capability {}
pub mod address_space {}
pub mod scheduler {}
pub mod ledger {}
