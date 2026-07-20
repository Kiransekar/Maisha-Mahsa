"""Payroll emits Prime-Directive recompute claims (§0.4) with the SAME inputs its figures were
computed on, so Mahsa recomputes the identical value. The live block behaviour against the real
Mahsa binary is proven in tests/integration/test_full_loop.py."""

from app.core.money import Paise
from app.domains.payroll.service import compute_components, payslip_recompute_claims


def test_claims_use_the_wage_base_and_carry_the_computed_figures():
    comp = compute_components(
        basic=Paise.from_rupees(8000),
        hra=Paise.from_rupees(6000),
        lta=0,
        special_allowance=Paise.from_rupees(6000),
        state="MH",
        month=6,
    )
    # under-weighted CTC: excluded ₹12k > 50% of ₹20k -> wage base added back to ₹10,000
    assert comp["wage_base"] == Paise.from_rupees(10000)
    claims = {c.target: c for c in payslip_recompute_claims(comp)}

    # wage-base claim reconstructs included/excluded so Mahsa recomputes the same base
    wb = claims["statutory_wage_base"]
    assert wb.claimed_paise == comp["wage_base"]
    assert wb.inputs == {
        "included": comp["basic"],
        "excluded": Paise.from_rupees(12000),
        "in_kind": 0,
    }

    # PF/ESI claims feed the wage base (not raw Basic/gross) and carry the payslip's figures
    assert claims["pf_employee"].inputs == {"basic_monthly": comp["wage_base"]}
    assert claims["pf_employee"].claimed_paise == comp["employee_pf"]
    assert claims["esi_employee"].inputs == {"gross_monthly": comp["wage_base"]}
    assert claims["esi_employee"].claimed_paise == comp["employee_esi"]
    assert claims["esi_employer"].claimed_paise == comp["employer_esi"]


def test_no_claims_for_unported_figures():
    comp = compute_components(
        basic=Paise.from_rupees(18000), hra=0, lta=0, special_allowance=0, state="MH", month=6
    )
    targets = {c.target for c in payslip_recompute_claims(comp)}
    # PT/TDS/loss-of-pay are not yet Mahsa-recomputable -> no claim (they stay honest-pending)
    assert "professional_tax" not in targets and "tds_monthly" not in targets
    assert targets == {
        "statutory_wage_base",
        "pf_employee",
        "pf_employer",
        "esi_employee",
        "esi_employer",
    }
