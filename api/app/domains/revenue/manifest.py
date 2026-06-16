"""Revenue feature manifest — the unit of build progress for this module (PRD §1.2)."""

from __future__ import annotations

from app.core.domain import DomainManifest, Feature, FeatureState

D = FeatureState.DONE
P = FeatureState.IN_PROGRESS
N = FeatureState.NOT_STARTED

MANIFEST = DomainManifest(
    domain="revenue",
    features=[
        Feature("customer_master", "Customer master (PAN/GSTIN/TDS/terms)", D),
        Feature("invoice_gen", "GST-compliant invoice generation (intra/inter-state)", D),
        Feature("tds_on_receipts", "TDS applicability on receivables", D),
        Feature("ar_aging", "AR aging (0-30/31-60/61-90/90+)", D),
        Feature("dunning", "Dunning reminder schedule (T-7/T-3/T-1/T+1/T+7)", D),
        Feature("credit_notes", "Credit notes + s.34 timeliness", D),
        Feature("gstr1_bridge", "Outward-supply feed into GST GSTR-1", D),
        Feature("revenue_recognition", "Accrual revenue recognition / deferred revenue", N),
        Feature("irn", "e-Invoice IRN generation + QR", N),
        Feature("export_invoicing", "LUT / IGST refund / FEMA export invoicing", N),
        Feature("dunning_send", "Automated reminder email dispatch", N),
    ],
)
