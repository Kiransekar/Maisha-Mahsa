"""WS1.D2 — QRMP filing profile, PMT-06 fixed-sum, per-profile penalties.

Spec-cited value: fixed-sum PMT-06 = 35 % of the previous quarter's cash (WS1.D2).
Statutory due-date calendar days are not in the spec — they are injected here.
"""

from datetime import date

from app.core.money import Paise
from app.domains.gst import qrmp
from app.domains.gst.gst_calc import interest_3b, late_fee_3b


# ---- PMT-06 fixed sum = 35 % of previous quarter's cash ----
def test_pmt06_fixed_sum_35pct():
    prev = Paise.from_rupees(1_00_000)  # ₹1,00,000 cash last quarter
    assert qrmp.pmt06_fixed_sum(prev) == Paise.from_rupees(35_000)


def test_pmt06_fixed_sum_exact_paise_half_up():
    # 35 % of ₹101.01 = 3535.35 paise -> 3535 (round half up on exact Decimal, no float)
    assert qrmp.pmt06_fixed_sum(10_101) == 3535


def test_pmt06_self_assessed_passthrough():
    assert qrmp.pmt06_self_assessed(777) == 777


# ---- QRMP quarter: quarterly 1/3B + monthly PMT-06 + IFF in months 1-2 ----
def test_qrmp_calendar_structure():
    cal = qrmp.filing_calendar("qrmp", ["2026-04", "2026-05", "2026-06"])
    obs = cal["obligations"]
    forms = [(o["form"], o["frequency"], o["period"]) for o in obs]

    # PMT-06 monthly in the first two months only
    assert ("PMT-06", "monthly", "2026-04") in forms
    assert ("PMT-06", "monthly", "2026-05") in forms
    assert ("PMT-06", "monthly", "2026-06") not in forms

    # IFF only in the first two months
    iff_periods = sorted(o["period"] for o in obs if o["form"] == "IFF")
    assert iff_periods == ["2026-04", "2026-05"]

    # GSTR-1 and GSTR-3B are quarterly (one each, over the whole quarter)
    quarterly = {(o["form"], o["period"]) for o in obs if o["frequency"] == "quarterly"}
    assert quarterly == {("GSTR-1", "2026-04/2026-06"), ("GSTR-3B", "2026-04/2026-06")}


def test_qrmp_due_dates_pending_until_injected():
    # No injected dates -> every obligation flagged pending (BLOCKED-CA), never guessed.
    cal = qrmp.filing_calendar("qrmp", ["2026-04", "2026-05", "2026-06"])
    assert all(o["pending_ca"] and o["due_date"] is None for o in cal["obligations"])

    injected = {("PMT-06", "2026-04"): date(2026, 5, 25)}
    cal2 = qrmp.filing_calendar("qrmp", ["2026-04", "2026-05", "2026-06"], due_dates=injected)
    pmt = next(o for o in cal2["obligations"] if o["form"] == "PMT-06" and o["period"] == "2026-04")
    assert pmt["due_date"] == date(2026, 5, 25) and pmt["pending_ca"] is False


# ---- monthly profile keeps monthly obligations ----
def test_monthly_calendar_keeps_monthly():
    cal = qrmp.filing_calendar("monthly", ["2026-04", "2026-05", "2026-06"])
    obs = cal["obligations"]
    assert all(o["frequency"] == "monthly" for o in obs)
    assert {o["form"] for o in obs} == {"GSTR-1", "GSTR-3B"}
    # one GSTR-1 and one GSTR-3B per month = 6 obligations, no PMT-06 / IFF
    assert len(obs) == 6
    assert not any(o["form"] in ("PMT-06", "IFF") for o in obs)


def test_composition_calendar_is_cmp08():
    cal = qrmp.filing_calendar("composition", ["2026-04", "2026-05", "2026-06"])
    assert [o["form"] for o in cal["obligations"]] == ["CMP-08"]


def test_unknown_profile_raises():
    try:
        qrmp.filing_calendar("weekly", ["2026-04", "2026-05", "2026-06"])
    except ValueError:
        pass
    else:
        raise AssertionError("unknown profile must raise")


# ---- per-profile penalty reuses ported late_fee_3b / interest_3b ----
def test_obligation_penalty_delegates_to_ported_funcs():
    cash = Paise.from_rupees(50_000)
    pen = qrmp.obligation_penalty(
        cash,
        due_date=date(2026, 7, 22),
        filed_date=date(2026, 7, 30),  # 8 days late
    )
    assert pen["days_late"] == 8
    assert pen["late_fee"] == late_fee_3b(8)
    assert pen["interest"] == interest_3b(cash, 8)


def test_obligation_penalty_on_time_is_zero():
    pen = qrmp.obligation_penalty(999_00, due_date=date(2026, 7, 22), filed_date=date(2026, 7, 20))
    assert pen == {"days_late": 0, "late_fee": 0, "interest": 0}
