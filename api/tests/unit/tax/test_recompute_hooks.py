"""Compute-time recompute claims (§0.4) for on-demand tax figures: advance_tax_interest (234C)
and itr_computation (115BAA) attach a RecomputeClaim whose inputs reconstruct the figure, so a
verifying caller can hand it to Mahsa. Rust↔Python parity for these targets is proven in
dif/tests/parity.rs; here we pin that the hook attaches a correct, round-tripping claim."""

from app.core.money import Paise
from app.domains.tax import tax_calc
from app.domains.tax.service import TaxService, interest_234b_claim


def test_advance_tax_interest_attaches_round_tripping_234c_claim(session):
    svc = TaxService()
    # no AdvanceTax rows -> cumulative [0,0,0,0]; on ₹4,00,000 liability total_234c = ₹20,200.
    res = svc.advance_tax_interest(session, fy="2026-27", total_liability=Paise.from_rupees(400000))
    claim = res["recompute_claim"]
    assert claim.target == "interest_234c"
    assert claim.claimed_paise == res["total_234c"] == Paise.from_rupees(20200)
    # inputs reconstruct the figure exactly (what Mahsa will recompute).
    assert tax_calc.interest_234c(**claim.inputs)["total_234c"] == claim.claimed_paise


def test_itr_company_115baa_attaches_round_tripping_claim():
    svc = TaxService()
    res = svc.itr_computation(
        entity_type="company",
        gross_total_income=Paise.from_rupees(10_000_000),
        regime_115baa=True,
    )
    claim = res["recompute_claim"]
    assert claim.target == "company_tax_115baa"
    assert claim.claimed_paise == res["normal_tax"] == Paise.from_rupees(2_516_800)
    assert claim.inputs == {"total_income": Paise.from_rupees(10_000_000)}
    # round-trip against the Python engine.
    rt = svc.itr_computation(
        entity_type="company",
        gross_total_income=claim.inputs["total_income"],
        regime_115baa=True,
    )
    assert rt["normal_tax"] == claim.claimed_paise


def test_itr_non_company_attaches_no_claim():
    svc = TaxService()
    res = svc.itr_computation(entity_type="llp", gross_total_income=Paise.from_rupees(1_000_000))
    assert "recompute_claim" not in res  # 115BAA is company-only; nothing ported for a firm


def test_interest_234b_claim_round_trips():
    # assessed ₹5L, advance ₹1L (<90%), 5 months -> ₹20,000 interest.
    interest = tax_calc.interest_234b(
        Paise.from_rupees(500000), Paise.from_rupees(100000), months=5
    )["interest"]
    claim = interest_234b_claim(
        Paise.from_rupees(500000), Paise.from_rupees(100000), 5, interest
    )
    assert claim.target == "interest_234b"
    assert claim.claimed_paise == Paise.from_rupees(20000)
    assert tax_calc.interest_234b(
        claim.inputs["assessed_tax"],
        claim.inputs["advance_paid"],
        months=claim.inputs["months"],
    )["interest"] == claim.claimed_paise
