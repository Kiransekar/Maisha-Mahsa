"""Expense feature manifest — the unit of build progress for this module (PRD §1.11)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="expense",
    features=[
        Feature("claim_workflow", "Claim → approval → reimbursement workflow", D),
        Feature("policy_check", "Per-category policy-limit check (EXPENSE-001)", D),
        Feature("petty_cash", "Petty-cash ₹10,000 threshold", D),
        Feature("analytics", "Category-wise spend analytics", D),
        Feature("receipt_parse", "Receipt parsing from OCR text (GSTIN/amount/date)", D),
        Feature("ocr_capture", "Photo → OCR (Tesseract) image pipeline", D),
        Feature("card_recon", "Corporate card reconciliation", N),
        Feature("mileage", "Mileage / per-diem travel", D),
    ],
)
