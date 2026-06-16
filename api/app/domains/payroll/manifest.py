"""Payroll feature manifest — the unit of build progress for this module (PRD §1.4)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="payroll",
    features=[
        Feature("salary_structure", "Salary structure / CTC breakdown", D),
        Feature("pf", "PF (EPF) employee + employer, ₹15k ceiling", D),
        Feature("esi", "ESI with ₹21k applicability ceiling", D),
        Feature("pt", "Professional Tax (MH, KA state slabs)", P),  # more states pending
        Feature("tds", "TDS s.192 new-regime slabs + rebate + marginal relief", D),
        Feature("payroll_run", "Monthly payroll run + entries + net pay", D),
        Feature("gratuity", "Gratuity provision (15/26 × basic × years)", D),
        Feature("bonus", "Statutory bonus provision (8.33%)", D),
        Feature("lwf", "Labour Welfare Fund (state calendars)", N),
        Feature("ecr", "EPFO ECR text-file generation", N),
        Feature("payslip", "Payslip PDF generation", N),
        Feature("form16", "Form 16 / 16A generation", N),
        Feature("leave", "Leave & attendance integration", N),
    ],
)
