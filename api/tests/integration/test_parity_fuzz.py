"""Randomized cross-language parity fuzz (MMX-1.0 §WS3.2). For each ported recompute path, generate
many random, PAISE-GRANULAR inputs, compute the Python figure, and send it to the REAL Mahsa binary
as a recompute claim: Mahsa recomputes independently and any divergence to the paisa BLOCKs (the
mismatch note carries both values). Paise-level randomness deliberately straddles rounding edges and
thresholds — where the round-number oracle vectors are blind (e.g. the caught tds double-rounding
defect). Seeded for reproducibility.
"""

from __future__ import annotations

import random

import pytest

from app.core.mahsa_client import MahsaClient, RecomputeClaim
from app.core.statutory_wage import statutory_wage_base
from app.core.verify import verify_claims
from app.domains.gst import gst_calc
from app.domains.payables import payables_calc
from app.domains.payroll import statutory as pay
from app.domains.tax import tax_calc

pytestmark = pytest.mark.integration

CASES = 300
SEED = 20260720


def _m(rng: random.Random, hi_rupees: int) -> int:
    """Random amount in PAISE up to ``hi_rupees`` — paise-granular, so fractional rupees occur."""
    return rng.randint(0, hi_rupees * 100)


# ---- single-value generators: rng -> (inputs, claimed_paise) ---------------------------


def g_esi_employee(rng):
    g = _m(rng, 30000)
    return {"gross_monthly": g}, int(pay.esi(g)[0])


def g_esi_employer(rng):
    g = _m(rng, 30000)
    return {"gross_monthly": g}, int(pay.esi(g)[1])


def g_pf_employee(rng):
    b = _m(rng, 40000)
    return {"basic_monthly": b}, int(pay.pf_employee(b))


def g_eps_employer(rng):
    b = _m(rng, 40000)
    return {"basic_monthly": b}, int(pay.eps_employer(b))


def g_wage_base(rng):
    basic, hra, special, in_kind = (_m(rng, 50000) for _ in range(4))
    claimed = int(
        statutory_wage_base(
            {"basic": basic, "hra": hra, "special_allowance": special}, in_kind=in_kind
        )
    )
    return {"included": basic, "excluded": hra + special, "in_kind": in_kind}, claimed


def g_tds(rng):
    section = rng.choice(["194C", "194J", "194H", "194I"])
    amount = _m(rng, 200000)
    payee_type = rng.choice(["company", "individual", "huf"])
    category = None
    if section == "194J":
        category = rng.choice([None, "technical"])
    elif section == "194I":
        category = rng.choice([None, "plant"])
    ytd = _m(rng, 200000)
    claimed = int(
        payables_calc.tds_on_payment(
            section, amount, payee_type=payee_type, category=category, aggregate_ytd=ytd
        )["tds_paise"]
    )
    inputs = {"section": section, "amount": amount, "payee_type": payee_type, "aggregate_ytd": ytd}
    if category is not None:
        inputs["category"] = category
    return inputs, claimed


def g_annual_income_tax(rng):
    t = _m(rng, 3_000_000)
    return {"annual_taxable": t}, int(pay.annual_income_tax(t))


def g_bonus(rng):
    b = _m(rng, 25000)
    return {"basic_monthly": b}, int(pay.bonus_provision_monthly(b))


def g_gratuity_required(rng):
    lb = _m(rng, 100000)
    yrs = rng.randint(0, 30)
    return {"last_basic_monthly": lb, "completed_years": yrs}, int(pay.gratuity_required(lb, yrs))


def g_gratuity_hybrid(rng):
    y = rng.randint(2005, 2024)
    doj = f"{y}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    exit_y = y + rng.randint(1, 20)
    exit_date = f"{exit_y}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    old_base, new_base = _m(rng, 100000), _m(rng, 100000)
    import datetime

    claimed = int(
        pay.gratuity_hybrid(
            doj=datetime.date.fromisoformat(doj),
            exit_date=datetime.date.fromisoformat(exit_date),
            boundary=datetime.date(2025, 11, 21),
            old_base=old_base,
            new_base=new_base,
        )
    )
    return {
        "doj": doj,
        "exit_date": exit_date,
        "boundary": "2025-11-21",
        "old_base": old_base,
        "new_base": new_base,
    }, claimed


def g_late_fee_234e(rng):
    days, tds = rng.randint(0, 400), _m(rng, 500000)
    return {"days_late": days, "tds_amount": tds}, int(tax_calc.late_fee_234e(days, tds))


def g_interest_234b(rng):
    assessed, advance, months = _m(rng, 5_000_000), _m(rng, 5_000_000), rng.randint(0, 24)
    claimed = int(tax_calc.interest_234b(assessed, advance, months=months)["interest"])
    return {"assessed_tax": assessed, "advance_paid": advance, "months": months}, claimed


def g_interest_234c(rng):
    total = _m(rng, 5_000_000)
    paid, run = [], 0
    for _ in range(4):
        run += _m(rng, 1_500_000)
        paid.append(run)
    claimed = int(tax_calc.interest_234c(total, paid)["total_234c"])
    return {"total_liability": total, "cumulative_paid": paid}, claimed


def g_company_tax_115baa(rng):
    ti = _m(rng, 50_000_000)
    claimed = int(
        tax_calc.itr_computation(entity_type="company", gross_total_income=ti, regime_115baa=True)[
            "normal_tax"
        ]
    )
    return {"total_income": ti}, claimed


def g_late_fee_3b(rng):
    days, is_nil = rng.randint(0, 400), rng.choice([True, False])
    return {"days_late": days, "is_nil": is_nil}, int(gst_calc.late_fee_3b(days, is_nil=is_nil))


def g_interest_3b(rng):
    cash, days = _m(rng, 5_000_000), rng.randint(0, 400)
    return {"cash_tax": cash, "days_late": days}, int(gst_calc.interest_3b(cash, days))


SINGLE = {
    "esi_employee": g_esi_employee,
    "esi_employer": g_esi_employer,
    "pf_employee": g_pf_employee,
    "eps_employer": g_eps_employer,
    "statutory_wage_base": g_wage_base,
    "tds_on_payment": g_tds,
    "annual_income_tax": g_annual_income_tax,
    "bonus_provision_monthly": g_bonus,
    "gratuity_required": g_gratuity_required,
    "gratuity_hybrid": g_gratuity_hybrid,
    "late_fee_234e": g_late_fee_234e,
    "interest_234b": g_interest_234b,
    "interest_234c": g_interest_234c,
    "company_tax_115baa": g_company_tax_115baa,
    "late_fee_3b": g_late_fee_3b,
    "interest_3b": g_interest_3b,
}


@pytest.mark.parametrize("target", list(SINGLE))
async def test_fuzz_single_value_parity(target, mahsa_server):
    rng = random.Random(SEED)
    mahsa = MahsaClient(mahsa_server)
    gen = SINGLE[target]
    claims = []
    for _ in range(CASES):
        inputs, claimed = gen(rng)
        claims.append(
            RecomputeClaim(
                target=target, inputs=inputs, claimed_paise=claimed, label=str(inputs)[:120]
            )
        )
    fold = await verify_claims(mahsa, claims)
    assert len(fold.recompute) == CASES  # every claim was checked (none silently dropped)
    # Non-vacuous: Mahsa actually recomputed non-trivial figures for this path (§0.5).
    assert any(c.recomputed_paise for c in fold.recompute), (
        f"{target}: fuzz never exercised a non-zero recompute"
    )
    bad = [c for c in fold.recompute if not c.matches]
    assert not bad, (
        f"{target}: {len(bad)}/{CASES} parity mismatches. First: {bad[0].note} @ {bad[0].label}"
    )


async def test_fuzz_itc_setoff_multivalue_parity(mahsa_server):
    rng = random.Random(SEED)
    mahsa = MahsaClient(mahsa_server)
    claims = []
    for _ in range(CASES):
        output = {h: _m(rng, 100000) for h in ("igst", "cgst", "sgst")}
        credit = {h: _m(rng, 100000) for h in ("igst", "cgst", "sgst")}
        r = gst_calc.itc_setoff(output, credit)
        values = {}
        for h in ("igst", "cgst", "sgst"):
            values[f"cash_{h}"] = int(r["cash"][h])
            values[f"credit_{h}"] = int(r["remaining_credit"][h])
        claims.append(
            RecomputeClaim(
                target="itc_setoff",
                inputs={"output": output, "credit": credit},
                claimed_values=values,
                label=str(output)[:120],
            )
        )
    fold = await verify_claims(mahsa, claims)
    assert len(fold.recompute) == CASES
    assert any(c.recomputed_values for c in fold.recompute), "itc fuzz never exercised a recompute"
    bad = [c for c in fold.recompute if not c.matches]
    assert not bad, f"itc_setoff: {len(bad)}/{CASES} mismatches. First: {bad[0].note}"
