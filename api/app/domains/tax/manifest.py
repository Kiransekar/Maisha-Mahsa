"""Tax feature manifest — the unit of build progress for this module (PRD §1.6)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="tax",
    features=[
        Feature("advance_tax", "Advance-tax schedule + s.234C interest", D),
        Feature("tds_returns", "TDS returns (24Q/26Q/27Q) + s.234E late fee", D),
        Feature("tds_aggregation", "TDS aggregation from payroll + payables", D),
        Feature("audit_44ab", "s.44AB tax-audit trigger", D),
        Feature("mat", "MAT (s.115JB) computation", D),
        Feature("interest_234b", "s.234B interest (shortfall < 90%)", D),
        Feature("form_26as", "Form 26AS reconciliation", N),
        Feature("itr", "ITR-5/ITR-6 preparation", N),
        Feature("tax_holiday", "Section 80-IAC holiday tracking", N),
        Feature("transfer_pricing", "Transfer pricing documentation", N),
    ],
)
