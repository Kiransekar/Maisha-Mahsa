//! Critic: the prior-update step that lets Mahsa adapt scoring weights from outcomes over
//! time (PRD §4.1 `critic/`). Deterministic exponential-moving-average update — pure, no
//! clock/RNG/network, so the loop stays reproducible (CLAUDE.md §2).

use crate::intent::IntentVec;

/// How strongly a single observed outcome nudges the global intent prior, per update.
pub const LEARNING_RATE: f64 = 0.1;

/// Update the global intent given an observed outcome signal in `[0,1]`.
///
/// EMA nudge toward the outcome, per dimension: `new = old + LEARNING_RATE * (outcome - old)`,
/// implemented as a clamped convex blend toward a uniform outcome vector. Deterministic:
/// same `(intent, outcome)` always yields the same result. The outcome is clamped to `[0,1]`
/// so an out-of-range signal can never push a prior outside the valid band.
pub fn update_prior(intent: IntentVec, outcome: f64) -> IntentVec {
    let target = outcome.clamp(0.0, 1.0);
    intent.blend(IntentVec([target; 8]), LEARNING_RATE)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deterministic_same_input_same_output() {
        let v = IntentVec([0.2, 0.4, 0.6, 0.8, 0.1, 0.3, 0.5, 0.7]);
        assert_eq!(update_prior(v, 0.9), update_prior(v, 0.9));
    }

    #[test]
    fn nudges_toward_outcome_by_learning_rate() {
        let v = IntentVec([0.0; 8]);
        let out = update_prior(v, 1.0);
        // each dim moves 10% of the way from 0.0 to 1.0
        for x in out.0 {
            assert!((x - 0.1).abs() < 1e-9, "expected ~0.1, got {x}");
        }
    }

    #[test]
    fn fixed_point_when_prior_equals_outcome() {
        let v = IntentVec([0.5; 8]);
        assert_eq!(update_prior(v, 0.5), v);
    }

    #[test]
    fn out_of_range_outcome_is_clamped() {
        let v = IntentVec([0.5; 8]);
        // outcome 2.0 clamps to 1.0 -> moves up toward 1.0, stays normalized
        let out = update_prior(v, 2.0);
        assert!(out.is_normalized());
        assert!(out.0.iter().all(|&x| x > 0.5));
    }

    #[test]
    fn result_stays_normalized() {
        let v = IntentVec([0.99, 0.01, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]);
        assert!(update_prior(v, 0.0).is_normalized());
        assert!(update_prior(v, 1.0).is_normalized());
    }
}
