//! Exact money. 1 INR = 100 paise. All money math in the core is integer paise;
//! rupees (`f64`) exist only for display and for unitless ratio inputs to fold.

use serde::{Deserialize, Serialize};

/// An amount in integer paise. `Paise(150_00)` == ₹150.00.
#[derive(
    Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize, Default,
)]
#[serde(transparent)]
pub struct Paise(pub i64);

impl Paise {
    pub const ZERO: Paise = Paise(0);

    /// Construct from whole rupees.
    pub const fn from_rupees(rupees: i64) -> Self {
        Paise(rupees * 100)
    }

    /// Value in rupees as `f64` — for display / ratio math only, never for money math.
    pub fn rupees(self) -> f64 {
        self.0 as f64 / 100.0
    }

    pub fn checked_add(self, other: Paise) -> Option<Paise> {
        self.0.checked_add(other.0).map(Paise)
    }

    pub fn checked_sub(self, other: Paise) -> Option<Paise> {
        self.0.checked_sub(other.0).map(Paise)
    }

    pub fn is_negative(self) -> bool {
        self.0 < 0
    }

    pub fn is_zero(self) -> bool {
        self.0 == 0
    }
}

impl std::ops::Add for Paise {
    type Output = Paise;
    fn add(self, o: Paise) -> Paise {
        // saturating: never wrap silently in release (no overflow-checks) on /fold input.
        Paise(self.0.saturating_add(o.0))
    }
}

impl std::ops::Sub for Paise {
    type Output = Paise;
    fn sub(self, o: Paise) -> Paise {
        Paise(self.0.saturating_sub(o.0))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rupee_conversion_is_exact() {
        assert_eq!(Paise::from_rupees(150), Paise(15_000));
        assert_eq!(Paise(15_000).rupees(), 150.0);
    }

    #[test]
    fn checked_arithmetic_guards_overflow() {
        assert_eq!(Paise(i64::MAX).checked_add(Paise(1)), None);
        assert_eq!(Paise(5).checked_sub(Paise(3)), Some(Paise(2)));
    }
}
