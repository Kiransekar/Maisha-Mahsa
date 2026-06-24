"""Treasury feature manifest — the unit of build progress for this module (PRD §1.1)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="treasury",
    features=[
        Feature("multi_bank_csv", "Multi-bank CSV import (HDFC/ICICI/Axis/canonical)", D),
        Feature("cash_position", "Consolidated cash position", D),
        Feature("burn", "Burn calculator", D),
        Feature("runway", "Runway calculator", D),
        Feature("burn_attribution", "Burn attribution by category", D),
        Feature("treasury_policy", "Auto-sweep / FD laddering suggestions", N),
        Feature("upi_recon", "UPI reconciliation", N),
        Feature("bg_tracking", "Bank guarantee tracking", N),
    ],
)
