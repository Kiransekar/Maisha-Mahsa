"""GST feature manifest — the unit of build progress for this module (PRD §1.5)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="gst",
    features=[
        Feature("gstin_validation", "GSTIN format + check-digit validation", D),
        Feature("gstr1", "GSTR-1 outward summary (B2B/B2C/HSN) + JSON", D),
        Feature("gstr3b", "GSTR-3B computation with statutory ITC set-off", D),
        Feature("late_fee_interest", "Late fee + s.50 interest", D),
        Feature("itc_recon", "GSTR-2B reconciliation + Rule 36(4) ratio", D),
        Feature("hsn_master", "HSN master + rate mapping", D),
        Feature("e_invoice", "e-Invoice IRN generation (> ₹5Cr)", N),
        Feature("rcm", "Reverse charge mechanism + self-invoice", D),
        Feature("gstr9", "GSTR-9 / 9C annual return", D),
        Feature("composition", "Composition scheme handling", N),
        Feature("lut", "LUT for exports", N),
    ],
)
