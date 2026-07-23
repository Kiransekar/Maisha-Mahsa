"""WS1.D2 — QRMP / filing-profile calendar, PMT-06 deposit, per-profile penalties.

A GST registration files on one of three profiles:

* ``monthly``      — GSTR-1 + GSTR-3B every month.
* ``qrmp``         — GSTR-1 + GSTR-3B **quarterly**, with a monthly PMT-06 tax deposit for
                     the first two months of the quarter and an optional IFF (Invoice
                     Furnishing Facility) in those same two months. The third month's
                     invoices and net tax are settled by the quarterly returns themselves.
* ``composition``  — quarterly CMP-08 statement (the CMP-08 artifact itself is WS1.D3).

Statutory truth (§0.6): the **fixed-sum** PMT-06 deposit is 35 % of the previous quarter's
cash tax paid — this 35 % is the only rate WS1.D2 states, so it lives here as a constant.
The **due-date calendar days** for each obligation (which day of the month a PMT-06, IFF,
GSTR-1 or GSTR-3B falls due) are NOT stated in WS1.D2; they are injected via ``due_dates``.
Absent an injected date an obligation is returned ``pending_ca=True`` (BLOCKED-CA / WS2)
rather than guessed. Money is integer paise; no clock is read — dates are passed in.

Late fee and interest are computed **per profile** by reusing the ported
``gst_calc.late_fee_3b`` / ``gst_calc.interest_3b`` unchanged — the profile only decides
which return's due date the lateness is measured against.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from .gst_calc import interest_3b, late_fee_3b

Profile = Literal["monthly", "qrmp", "composition"]

# WS1.D2 spec value: fixed-sum PMT-06 = 35 % of the previous quarter's cash tax paid.
QRMP_FIXED_SUM_RATE = Decimal("0.35")


def _norm(profile: str) -> Profile:
    p = profile.strip().lower()
    if p not in ("monthly", "qrmp", "composition"):
        raise ValueError(f"unknown filing profile: {profile!r}")
    return p  # type: ignore[return-value]


# ---- PMT-06 monthly deposit (QRMP) ----------------------------------------------------


def pmt06_fixed_sum(prev_quarter_cash: int) -> int:
    """Fixed-sum method: 35 % of the previous quarter's cash tax paid, exact paise."""
    return int(
        (Decimal(int(prev_quarter_cash)) * QRMP_FIXED_SUM_RATE).to_integral_value(ROUND_HALF_UP)
    )


def pmt06_self_assessed(liability: int) -> int:
    """Self-assessment method: deposit the month's actual self-assessed cash liability."""
    return int(liability)


# ---- filing calendar ------------------------------------------------------------------


def _obligation(
    form: str,
    kind: str,
    frequency: str,
    period: str,
    due_dates: dict[tuple[str, str], date] | None,
) -> dict[str, Any]:
    due = (due_dates or {}).get((form, period))
    return {
        "form": form,
        "kind": kind,
        "frequency": frequency,
        "period": period,
        "due_date": due,
        "pending_ca": due is None,  # statutory due day not in spec — inject or BLOCKED-CA
    }


def filing_calendar(
    profile: str,
    quarter: Sequence[str],
    *,
    due_dates: dict[tuple[str, str], date] | None = None,
) -> dict[str, Any]:
    """Obligations for one quarter under ``profile``.

    ``quarter`` is the three period labels of the quarter (e.g. ``["2026-04","2026-05",
    "2026-06"]``). ``due_dates`` maps ``(form, period)`` to the statutory due date; any
    obligation without one is returned ``pending_ca=True``. Returns a flat obligation list.
    """
    p = _norm(profile)
    months = list(quarter)
    if len(months) != 3:
        raise ValueError("a quarter must have exactly 3 month labels")
    qlabel = f"{months[0]}/{months[-1]}"
    obs: list[dict[str, Any]] = []

    if p == "monthly":
        for m in months:
            obs.append(_obligation("GSTR-1", "return", "monthly", m, due_dates))
            obs.append(_obligation("GSTR-3B", "return", "monthly", m, due_dates))
    elif p == "qrmp":
        for m in months[:2]:  # first two months: PMT-06 deposit + optional IFF
            obs.append(_obligation("PMT-06", "deposit", "monthly", m, due_dates))
            obs.append(_obligation("IFF", "iff", "monthly", m, due_dates))
        obs.append(_obligation("GSTR-1", "return", "quarterly", qlabel, due_dates))
        obs.append(_obligation("GSTR-3B", "return", "quarterly", qlabel, due_dates))
    else:  # composition
        obs.append(_obligation("CMP-08", "statement", "quarterly", qlabel, due_dates))

    return {"profile": p, "quarter": months, "obligations": obs}


# ---- per-profile late fee + interest (reuses the ported gst_calc functions) -----------


def obligation_penalty(
    cash_tax: int,
    *,
    due_date: date,
    filed_date: date,
    is_nil: bool = False,
    aato: int | None = None,
) -> dict[str, int]:
    """Late fee + interest for a return filed on ``filed_date`` against its ``due_date``.

    The due date is whichever the profile's calendar assigns (monthly vs quarterly 3B),
    so lateness is measured per profile. Delegates the money math to the ported
    ``late_fee_3b`` / ``interest_3b`` — those are NOT reimplemented here.
    """
    days_late = max(0, (filed_date - due_date).days)
    return {
        "days_late": days_late,
        "late_fee": late_fee_3b(days_late, is_nil=is_nil, aato=aato),
        "interest": interest_3b(int(cash_tax), days_late),
    }
