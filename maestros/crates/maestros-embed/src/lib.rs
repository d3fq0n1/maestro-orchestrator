//! MaestrOS embedding layer.
//!
//! v0 ships with a single fixed model: `nomic-embed-text-v1.5` (768-dim,
//! Matryoshka-truncatable to 512/256/128). Candle is the primary backend;
//! `ort` (ONNX Runtime) is the fallback for NPU targets (Hailo, Jetson).
//!
//! Every intent envelope carries `(model_id, model_version, dim)` in its
//! header from day one, so per-domain models can be introduced in later
//! versions without a wire break.

pub mod model {}
pub mod backend {}
