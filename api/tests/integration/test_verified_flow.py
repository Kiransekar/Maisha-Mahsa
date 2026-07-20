"""End-to-end verified flow for on-demand tax figures against the REAL Mahsa binary: compute →
attach claim → verify_figure. A correct figure verifies; a tampered one is BLOCKED (§0.4)."""

import pytest

from app.core.mahsa_client import MahsaClient
from app.core.money import Paise
from app.core.verify import verify_figure
from app.domains.gst.service import GstService
from app.domains.tax.service import TaxService, interest_234c_claim
from app.domains.tax.tax_calc import interest_234c

pytestmark = pytest.mark.integration


async def test_ondemand_234c_verifies_and_tamper_blocks(mahsa_server):
    mahsa = MahsaClient(mahsa_server)
    # ₹4,00,000 liability, nothing paid -> total_234c ₹20,200.
    result = interest_234c(Paise.from_rupees(400000), [0, 0, 0, 0])
    claim = interest_234c_claim(Paise.from_rupees(400000), [0, 0, 0, 0], result["total_234c"])

    ok = await verify_figure(mahsa, claim)
    assert ok.verified and not ok.blocked

    tampered = claim.model_copy(update={"claimed_paise": claim.claimed_paise + 100})
    bad = await verify_figure(mahsa, tampered)
    assert bad.blocked and not bad.verified


async def test_ondemand_115baa_hook_verifies_live(mahsa_server):
    mahsa = MahsaClient(mahsa_server)
    svc = TaxService()
    itr = svc.itr_computation(
        entity_type="company",
        gross_total_income=Paise.from_rupees(10_000_000),
        regime_115baa=True,
    )
    v = await verify_figure(mahsa, itr["recompute_claim"])
    assert v.verified and not v.blocked


async def test_ondemand_multivalue_itc_setoff_verifies_and_tamper_blocks(session, mahsa_server):
    # A multi-value figure (per-head cash + remaining credit) verifies field-wise; tampering one
    # head's cash BLOCKs (§0.4).
    mahsa = MahsaClient(mahsa_server)
    svc = GstService()
    res = svc.file_gstr3b(
        session,
        filing_period="2026-05",
        due_date="2026-06-20",
        output={"igst": 10000, "cgst": 5000, "sgst": 5000},
        itc_available={"igst": 8000, "cgst": 6000, "sgst": 3000},
        filed_date="2026-06-25",
    )
    claim = res["recompute_claim"]

    ok = await verify_figure(mahsa, claim)
    assert ok.verified and not ok.blocked

    tampered = claim.model_copy(
        update={"claimed_values": {**claim.claimed_values, "cash_igst": 999_999}}
    )
    bad = await verify_figure(mahsa, tampered)
    assert bad.blocked and not bad.verified
