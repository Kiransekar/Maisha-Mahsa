//! Property tests: the fold/validate invariants must hold for *any* snapshot.

use mahsa::fold::fold;
use mahsa::money::Paise;
use mahsa::snapshot::{Domain, Snapshot};
use mahsa::validate::{validate, RuleSet, ValidationStatus};
use proptest::prelude::*;

fn arb_snapshot() -> impl Strategy<Value = Snapshot> {
    (
        0i64..2_000_000_000i64, // cash paise
        0i64..200_000_000i64,   // burn paise
        0i64..200_000_000i64,   // revenue paise
        0u32..10u32,            // accounts
        0.0f64..1.0f64,         // concentration
        0u32..6u32,             // overdue filings
    )
        .prop_map(|(cash, burn, rev, accts, conc, overdue)| Snapshot {
            cash: Paise(cash),
            monthly_burn: Paise(burn),
            monthly_revenue: Paise(rev),
            bank_account_count: accts,
            largest_account_share: conc,
            overdue_filings: overdue,
            ..Default::default()
        })
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(512))]

    /// Intent is always normalized to [0,1] across every dimension.
    #[test]
    fn global_intent_is_always_normalized(s in arb_snapshot()) {
        let f = fold(&s, Some(Domain::Treasury));
        prop_assert!(f.global.is_normalized());
        if let Some((_, dv)) = f.domain {
            prop_assert!(dv.is_normalized());
        }
    }

    /// Folding is deterministic: identical input → identical output.
    #[test]
    fn fold_is_deterministic(s in arb_snapshot()) {
        let a = fold(&s, Some(Domain::Treasury));
        let b = fold(&s, Some(Domain::Treasury));
        prop_assert_eq!(a.global, b.global);
    }

    /// Validation is total and deterministic; status is one of the three lights.
    #[test]
    fn validation_is_total(s in arb_snapshot()) {
        let rs = RuleSet::embedded();
        let f = fold(&s, Some(Domain::Treasury));
        let v1 = validate(&f.global, &s, Some(Domain::Treasury), &rs);
        let v2 = validate(&f.global, &s, Some(Domain::Treasury), &rs);
        prop_assert_eq!(v1.status, v2.status);
        prop_assert!(matches!(
            v1.status,
            ValidationStatus::Green | ValidationStatus::Yellow | ValidationStatus::Red
        ));
        // A Red status implies at least one block-severity rule fired.
        if v1.status == ValidationStatus::Red {
            prop_assert!(v1.triggered.iter().any(|t| matches!(t.severity, mahsa::validate::Severity::Block)));
        }
    }
}
