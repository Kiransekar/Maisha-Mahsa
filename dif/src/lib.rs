//! Mahsa — the deterministic DIF core of Maisha-Mahsa.
//!
//! Mahsa is the gatekeeper (see `CLAUDE.md` §1). It takes a financial `Snapshot`
//! plus an optional domain hint, computes the global 8-dim Intent vector and an
//! optional domain sub-vector (**fold**), checks the hierarchical rule set
//! (**validate**), and emits a `ResponseShape` that tells the renderer how to
//! present the result (**unfold**).
//!
//! Invariants (enforced by tests, never to be relaxed):
//!   * Pure & deterministic — no clocks, no RNG, no IO inside fold/validate/unfold.
//!     The "as of" date is injected via the `Snapshot`.
//!   * Money is integer **paise**. Never a binary float in money math.
//!   * Every triggered rule carries a statute + section citation.

pub mod app;
pub mod critic;
pub mod fold;
pub mod intent;
pub mod money;
pub mod snapshot;
pub mod unfold;
pub mod validate;

pub use intent::{IntentVec, GLOBAL_DIMS};
pub use money::Paise;
pub use snapshot::{Domain, FoldRequest, Snapshot};
pub use validate::{RuleSet, Severity, ValidationStatus};

/// Semantic version of the engine. Returned by `/health`.
pub const ENGINE_VERSION: &str = env!("CARGO_PKG_VERSION");
