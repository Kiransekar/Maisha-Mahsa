"""Payables feature manifest — the unit of build progress for this module (PRD §1.3)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="payables",
    features=[
        Feature("vendor_master", "Vendor master (PAN/GSTIN/MSME/TDS section)", D),
        Feature("tds_engine", "TDS engine (194C/194J/194H/194I rates + thresholds)", D),
        Feature("three_way_match", "PO↔GRN↔invoice 3-way match (±5%)", D),
        Feature("ap_aging", "AP aging (0-30/31-60/61-90/90+)", D),
        Feature("msme_45day", "MSME 45-day compliance (s.43B(h))", D),
        Feature("itc_bridge", "Input-tax-credit feed into GST", D),
        Feature("recurring", "Recurring payables (SaaS) auto-categorisation", N),
        Feature("early_pay", "Early-payment discount capture", D),
        Feature("payment_run", "Payment batch / disbursement", N),
    ],
)
