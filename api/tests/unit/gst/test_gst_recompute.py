"""GstService.recompute_claims (§0.4): late GSTR-3B filings must emit interest/late-fee
claims that Mahsa's ported recompute (dif/src/recompute/gst_fees.rs) can reproduce exactly."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.gst import gst_calc
from app.domains.gst.service import GstService


def test_recompute_claims_round_trip_for_late_filed_3b(session):
    svc = GstService()
    svc.file_gstr3b(
        session,
        filing_period="2026-05",
        due_date="2026-06-20",
        output={"igst": 0, "cgst": Paise.from_rupees(5000), "sgst": Paise.from_rupees(5000)},
        itc_available={"igst": 0, "cgst": 0, "sgst": 0},
        filed_date="2026-06-25",  # 5 days late
    )

    claims = svc.recompute_claims(session)
    by_target = {c.target: c for c in claims}
    # Only interest_3b is claimed; late_fee_3b's is_nil is not persisted so it stays honest-pending.
    assert set(by_target) == {"interest_3b"}

    interest_claim = by_target["interest_3b"]
    # Same inputs the Python figure was computed on -> Mahsa's recompute reproduces it.
    assert gst_calc.interest_3b(**interest_claim.inputs) == interest_claim.claimed_paise
    assert interest_claim.inputs == {"cash_tax": Paise.from_rupees(10000), "days_late": 5}


def test_recompute_claims_skip_unfiled_and_on_time_returns(session):
    svc = GstService()
    # unfiled -> no filed_date -> skipped
    svc.file_gstr3b(
        session,
        filing_period="2026-04",
        due_date="2026-05-20",
        output={"igst": 0, "cgst": Paise.from_rupees(1000), "sgst": Paise.from_rupees(1000)},
        itc_available={"igst": 0, "cgst": 0, "sgst": 0},
    )
    # filed on time -> days_late == 0 -> no late fee/interest -> skipped
    svc.file_gstr3b(
        session,
        filing_period="2026-03",
        due_date="2026-04-20",
        output={"igst": 0, "cgst": Paise.from_rupees(1000), "sgst": Paise.from_rupees(1000)},
        itc_available={"igst": 0, "cgst": 0, "sgst": 0},
        filed_date="2026-04-18",
    )

    assert svc.recompute_claims(session) == []
