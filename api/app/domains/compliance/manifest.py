"""Compliance feature manifest — the unit of build progress for this module (PRD §1.10)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="compliance",
    features=[
        Feature("calendar", "Compliance calendar (all statutes, all forms)", D),
        Feature("seed_statutory", "Seed standard monthly statutory deadlines", D),
        Feature("alerts", "T-7 / T-1 / T-0 + overdue alerts", D),
        Feature("filing_status", "Per-statute filing-status health", D),
        Feature("mark_filed", "Mark a return filed (with acknowledgement)", D),
        Feature("mca_filings", "MCA filings (AOC-4/MGT-7/DIR-3 KYC/DPT-3)", N),
        Feature("secretarial", "Secretarial compliance (minutes/AGM/resolutions)", N),
        Feature("audit_support", "Statutory/internal audit support package", N),
        Feature("dpiit", "DPIIT Startup India reporting", N),
    ],
)
