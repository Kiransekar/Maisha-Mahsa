"""WS1.D3 — CMP-08 quarterly composition statement artifact.

CMP-08 is the composition taxpayer's quarterly self-assessed statement of tax payable:
outward supplies (incl. exempt), tax on them at the composition rate, any inward supplies
under reverse charge (taxed at the normal rate for that supply, not the composition rate —
composition dealers cannot use their concessional rate on RCM liability), and interest if
the statement is filed late.

Statutory truth (§0.6): the composition RATES (1 % traders/manufacturers, 5 % restaurant
non-alcohol, 6 % services u/s 10(2A)) are NOT stated in WS1.D2/D3 — ``composition_rate`` is
a mandatory keyword-only parameter with no default, so calling this without one raises
``TypeError`` rather than any rate being invented. Interest reuses the ported
``gst_calc.interest_3b`` (generic s.50, 18% p.a. — already reused for QRMP in
``qrmp.obligation_penalty``) unchanged. Money is integer paise; no clock is read — dates
are passed in.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .gst_calc import interest_3b, rcm_liability


def build_cmp08(
    period: str,
    composition_data: dict[str, Any],
    *,
    composition_rate: Decimal | str | int,
    due_date: date,
    filed_date: date,
) -> dict[str, Any]:
    """Build the CMP-08 quarterly statement dict for a composition-profile registration.

    ``composition_data`` keys:
      * ``outward_taxable_value`` (required, paise) — outward supplies incl. exempt.
      * ``rcm_supplies`` (optional, default []) — list of ``{"taxable": paise, "rate": pct}``
        fed to the ported ``rcm_calc.rcm_liability`` unchanged (RCM is taxed at the normal
        rate for that supply, never the composition rate).
      * ``gstin``, ``legal_name`` (optional, echoed through).

    ``composition_rate`` (percent, e.g. ``"1"``/``"5"``/``"6"``) has NO default — the rate
    is not a spec-stated value (§0.6); omitting it raises ``TypeError`` at the call site.
    """
    outward_taxable_value = int(composition_data["outward_taxable_value"])
    rcm_supplies = composition_data.get("rcm_supplies", [])
    rcm = rcm_liability(rcm_supplies)

    outward_tax = Decimal(outward_taxable_value) * Decimal(str(composition_rate)) / Decimal(100)
    outward_tax_payable = int(outward_tax.to_integral_value(ROUND_HALF_UP))
    tax_payable = outward_tax_payable + int(rcm["rcm_tax_payable"])

    days_late = max(0, (filed_date - due_date).days)
    interest_payable = interest_3b(tax_payable, days_late)

    return {
        "form": "CMP-08",
        "period": period,
        "gstin": composition_data.get("gstin"),
        "legal_name": composition_data.get("legal_name"),
        "composition_rate_pct": str(composition_rate),
        "outward_taxable_value": outward_taxable_value,
        "outward_tax_payable": outward_tax_payable,
        "rcm_taxable_value": int(rcm["taxable_value"]),
        "rcm_tax_payable": int(rcm["rcm_tax_payable"]),
        "tax_payable": tax_payable,
        "due_date": due_date,
        "filed_date": filed_date,
        "days_late": days_late,
        "interest_payable": interest_payable,
        "total_payable": tax_payable + interest_payable,
    }
