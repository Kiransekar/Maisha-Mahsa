"""Ledger feature manifest — the unit of build progress for this module (PRD §1.7)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="ledger",
    features=[
        Feature("chart_of_accounts", "Chart of accounts (Indian GAAP types)", D),
        Feature("journal", "Journal entries with double-entry validation", D),
        Feature("trial_balance", "Trial balance", D),
        Feature("pnl", "Profit & Loss statement", D),
        Feature("balance_sheet", "Balance sheet (accounting equation)", D),
        Feature("depreciation", "Depreciation (SLM / WDV, Schedule II)", D),
        Feature("general_ledger", "Account-wise general ledger view", D),
        Feature("cash_flow", "Cash flow statement (direct/indirect)", N),
        Feature("bank_recon", "Bank reconciliation", N),
        Feature("auto_posting", "Auto journal posting from payroll/GST/revenue", N),
    ],
)
