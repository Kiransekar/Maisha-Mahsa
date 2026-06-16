//! Critic: the prior-update step that lets Mahsa adapt scoring weights from outcomes
//! over time (PRD §4.1 `critic/`). L1 scaffold — currently a pure identity so the loop is
//! complete and deterministic. Implementing the Bayesian update is tracked in
//! BUILD_PROGRESS.md (L1 "critic"). It must remain pure and deterministic when built.

use crate::intent::IntentVec;

/// Update the global intent given an observed outcome signal in `[0,1]`.
/// Identity for now (no learning) — documented stub, never a silent fallback.
pub fn update_prior(intent: IntentVec, _outcome: f64) -> IntentVec {
    intent
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_for_now() {
        let v = IntentVec([0.5; 8]);
        assert_eq!(update_prior(v, 0.9), v);
    }
}
