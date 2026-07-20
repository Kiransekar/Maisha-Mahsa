//! Independent statutory recomputation (MMX-1.0 §WS3.1) — Mahsa re-derives, in Rust, the
//! figures the Python service produces, so no number reaches a human unrecomputed (Prime
//! Directive §0.4). Pure, clock-free, integer paise; every fn mirrors one Python path exactly.
//!
//! Parity is proven by `tests/parity.rs`, which replays the SAME CA-oracle vectors
//! (`api/tests/statutory_oracle/vectors/*.yaml`) against these fns and asserts equality to the
//! paisa. Because the Python oracle asserts the same vectors, Rust == expected == Python.
//!
//! Port order (§WS3.1): slab tax → PF/ESI (+ s.2(y) wage base) → TDS (all sections) →
//! ITC set-off → GST late-fee/interest → gratuity/bonus.

pub mod slab_tax;
pub mod pf_esi;
pub mod tds;
pub mod itc;
pub mod gst_fees;
pub mod gratuity_bonus;

/// Round integer paise to the nearest whole rupee, half up (mirror of Python `_round_rupee`).
pub(crate) fn round_rupee(paise: i64) -> i64 {
    if paise >= 0 {
        ((paise + 50) / 100) * 100
    } else {
        -(((-paise) + 50) / 100) * 100
    }
}

/// Round non-negative integer paise UP to the next whole rupee (mirror of Python `_ceil_rupee`
/// applied to an already-integer paise amount).
pub(crate) fn ceil_rupee(paise: i64) -> i64 {
    debug_assert!(paise >= 0);
    ((paise + 99) / 100) * 100
}
