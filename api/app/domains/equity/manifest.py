"""Equity feature manifest — the unit of build progress for this module (PRD §1.9)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="equity",
    features=[
        Feature("cap_table", "Cap table (founder/investor/ESOP/advisor, ownership %)", D),
        Feature("esop_pool", "ESOP pool % + board-approval gate (EQUITY-001)", D),
        Feature("safe_notes", "SAFE conversion (valuation cap vs discount)", D),
        Feature("dilution", "Round dilution modelling", D),
        Feature("cap_table_snapshot", "Cap table snapshot persistence", D),
        Feature("convertible_notes", "Convertible notes (interest accrual)", D),
        Feature("investor_reporting", "Quarterly investor update generator", N),
        Feature("dividend", "Dividend distribution (s.123)", D),
        Feature("share_certificates", "Share certificate / demat tracking", N),
        Feature("rights_buyback", "Rights issue / buyback compliance", N),
    ],
)
