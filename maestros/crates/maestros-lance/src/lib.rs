//! MaestrOS address space + epistemic ledger, LanceDB-backed.
//!
//! Two tables define the substrate:
//!
//!   * `capabilities` — k-NN lookup from intent vector to capability
//!     provider. Signed manifests, freshness metadata, proof columns.
//!     Resolving an intent is a vector search plus a policy filter.
//!
//!   * `ledger` — append-only record of every intent, outcome, R2 score,
//!     and quorum decision. Time-decayed. This is both the audit trail
//!     AND a query corpus: the system can learn from its own history
//!     by vector-searching its past.
//!
//! The equation "epistemic ledger = vector index" is made literal here.

pub mod address_space {}
pub mod ledger {}
pub mod schema {}
