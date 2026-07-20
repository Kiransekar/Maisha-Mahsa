"""TaxService.recompute_claims — §0.4 Prime-Directive claims for the tax domain.

Only late_fee_234e is ported to Rust (Mahsa); 234B/234C interest and the 115BAA ITR path
stay honest-pending and must never appear here."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.tax import tax_calc
from app.domains.tax.service import TaxService


def test_recompute_claims_round_trips_late_fee_234e_only(session):
    svc = TaxService()
    # filed 10 days late -> emits a late_fee_234e claim
    svc.file_tds_return(
        session,
        return_type="26Q",
        quarter="2026-Q1",
        due_date="2026-07-31",
        total_deducted=Paise.from_rupees(50000),
        filed_date="2026-08-10",
    )
    # filed on time -> no claim
    svc.file_tds_return(
        session,
        return_type="24Q",
        quarter="2026-Q1",
        due_date="2026-07-31",
        total_deducted=Paise.from_rupees(30000),
        filed_date="2026-07-31",
    )
    # not filed at all -> no claim
    svc.file_tds_return(
        session,
        return_type="27Q",
        quarter="2026-Q2",
        due_date="2026-10-31",
        total_deducted=Paise.from_rupees(20000),
    )

    claims = svc.recompute_claims(session)

    assert len(claims) == 1
    claim = claims[0]
    assert claim.target == "late_fee_234e"
    assert claim.inputs == {"days_late": 10, "tds_amount": Paise.from_rupees(50000)}
    assert claim.claimed_paise == Paise.from_rupees(2000)
    # round-trip: Mahsa's Rust recompute mirrors tax_calc.late_fee_234e exactly.
    assert tax_calc.late_fee_234e(**claim.inputs) == claim.claimed_paise
