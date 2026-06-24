"""Forecast feature manifest — the unit of build progress for this module (PRD §1.8)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="forecast",
    features=[
        Feature("budget", "Annual budget + variance analysis", D),
        Feature("cash_forecast", "Rolling cash-flow projection + overdraft alert", D),
        Feature("scenario", "Scenario engine (base/optimistic/pessimistic/hire)", D),
        Feature("burn_multiple", "Burn multiple (net burn / net new ARR)", D),
        Feature("unit_economics", "Unit economics (CAC/LTV/payback)", D),
        Feature("headcount", "Headcount planning → payroll forecast", D),
        Feature("rolling_reforecast", "Quarterly re-forecast workflow", D),
        Feature("rev_recognition_forecast", "Contract-to-revenue timing", N),
    ],
)
