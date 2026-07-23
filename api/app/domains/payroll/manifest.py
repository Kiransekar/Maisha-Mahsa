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
        Feature("pt", "Professional Tax (MH/KA/WB/GJ/AP/TS state slabs)", D),
        Feature("tds", "TDS s.192 new-regime slabs + rebate + marginal relief", D),
        Feature("payroll_run", "Monthly payroll run + entries + net pay", D),
        Feature("gratuity", "Gratuity provision (15/26 × basic × years)", D),
        Feature("bonus", "Statutory bonus provision (8-1/3% or Rs.100/year floor)", D),
        Feature("lwf", "Labour Welfare Fund (state calendars)", D),
        Feature("ecr", "EPFO ECR text-file generation", D),
        Feature("payslip", "Payslip PDF generation", D),
        Feature("form16", "Form 16 / 16A generation", D),
        Feature("leave", "Leave & attendance integration (loss-of-pay)", D),
    ],
)
