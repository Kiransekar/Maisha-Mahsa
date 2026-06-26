"""Vault feature manifest — the unit of build progress for this module (PRD §1.12)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="vault",
    features=[
        Feature("ingest", "Ingest + SHA-256 content hashing", D),
        Feature("dedup", "Duplicate detection (by content hash)", D),
        Feature("classify", "Document classification", D),
        Feature("retention", "Retention policy (7y/3y/permanent)", D),
        Feature("search", "Full-text search (OCR text + tags)", D),
        Feature("integrity", "SHA-256 integrity verification (VAULT-001)", D),
        Feature("ocr_pipeline", "Scan → OCR (Tesseract) image pipeline", D),
        Feature("auto_archive", "Auto-archive on retention expiry", D),
        Feature("access_control", "RBAC access control", D),
    ],
)
