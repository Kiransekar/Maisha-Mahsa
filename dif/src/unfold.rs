//! Unfold: turn fold + validation into a `ResponseShape` — the instructions the renderer
//! (Python) uses to lay out the dashboard/email. Mahsa decides presentation so it is
//! provable and consistent; Maisha never decides how a number is shown.

use crate::fold::Fold;
use crate::validate::{Severity, Validation, ValidationStatus};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct Banner {
    pub severity: Severity,
    pub text: String,
    /// Human-readable citation, e.g. "Code on Social Security 2020 — s.16(1)(a) (ex EPF & MP Act 1952 s.6)".
    pub citation: String,
    pub action: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ResponseShape {
    pub status: ValidationStatus,
    /// CSS accent token the UI should use: "green" | "amber" | "red".
    pub color: String,
    /// Layout hint, e.g. "domain:treasury" or "global".
    pub layout: String,
    /// Whether the response requires explicit founder approval before any action proceeds.
    pub requires_approval: bool,
    pub banners: Vec<Banner>,
    /// Global domain score 0..100 for the health dashboard.
    pub global_score: f64,
    /// Domain score 0..100 when a domain sub-vector was computed.
    pub domain_score: Option<f64>,
}

fn color_for(status: ValidationStatus) -> &'static str {
    match status {
        ValidationStatus::Green => "green",
        ValidationStatus::Yellow => "amber",
        ValidationStatus::Red => "red",
    }
}

pub fn unfold(fold: &Fold, validation: &Validation) -> ResponseShape {
    let banners = validation
        .triggered
        .iter()
        .map(|t| Banner {
            severity: t.severity,
            text: t.description.clone(),
            citation: format!("{} — {}", t.statute, t.section),
            action: t.action.clone(),
        })
        .collect();

    let layout = match &fold.domain {
        Some((d, _)) => format!("domain:{}", d.as_str()),
        None => "global".to_string(),
    };

    ResponseShape {
        status: validation.status,
        color: color_for(validation.status).to_string(),
        layout,
        // Yellow and Red both gate on the founder; Green flows through.
        requires_approval: validation.status != ValidationStatus::Green,
        banners,
        global_score: fold.global.score(),
        domain_score: fold.domain.as_ref().map(|(_, iv)| iv.score()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fold::fold;
    use crate::money::Paise;
    use crate::snapshot::{Domain, Snapshot};
    use crate::validate::{validate, RuleSet};

    #[test]
    fn red_status_requires_approval_and_carries_citation() {
        let s = Snapshot {
            cash: Paise::from_rupees(100_000),
            monthly_burn: Paise::from_rupees(100_000),
            ..Default::default()
        };
        let rs = RuleSet::embedded();
        let f = fold(&s, Some(Domain::Treasury));
        let v = validate(&f.global, &s, Some(Domain::Treasury), &rs);
        let shape = unfold(&f, &v);
        assert_eq!(shape.status, ValidationStatus::Red);
        assert_eq!(shape.color, "red");
        assert!(shape.requires_approval);
        assert!(shape.domain_score.is_some());
        assert!(shape.banners.iter().all(|b| b.citation.contains('—')));
    }
}
