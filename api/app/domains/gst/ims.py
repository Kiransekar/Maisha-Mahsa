"""IMS (Invoice Management System) workflow — pure state machine, no statutory rates.

Per WS1.D4: an inward invoice starts ``pending``. The recipient may ``accept`` (ITC
eligible) or ``reject`` (ITC not eligible) it. If no action is taken by the invoice's
deadline, GSTN's IMS deems it accepted (the "deemed-accept default"), so it still
becomes ITC eligible. The deadline itself is a per-invoice value injected by the
caller — this module does not hardcode a statutory cut-off date/day-count, since none
is given in the spec (§0.6). BLOCKED-CA: the exact GSTR-3B-linked deemed-acceptance
deadline rule is not in docs/MASTER_PLAN.md and must come from a CA-cited vector before
any caller wires a real date-offset here.

No clock is read; ``as_of`` is passed in. All ITC amounts are integer paise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, TypedDict

Action = Literal["accept", "reject", "pending"] | None
State = Literal["accepted", "rejected", "pending", "deemed_accepted"]


class Disposition(TypedDict):
    id: str
    state: State
    itc_eligible: bool
    reason: str
    itc_paise: int


class DispositionResult(TypedDict):
    invoices: list[Disposition]
    eligible_itc_total_paise: int


@dataclass(frozen=True)
class InwardInvoice:
    """One inward invoice as seen by IMS. ``action`` is the recipient's action to date
    (``None``/``"pending"`` = no action taken). ``deadline`` is the injected date by
    which action must be taken before the deemed-accept default applies."""

    id: str
    itc_paise: int
    deadline: date
    action: Action = None


def _disposition(inv: InwardInvoice, as_of: date) -> Disposition:
    if inv.action == "accept":
        state: State = "accepted"
        eligible = True
        reason = "taxpayer accepted"
    elif inv.action == "reject":
        state = "rejected"
        eligible = False
        reason = "taxpayer rejected"
    elif as_of >= inv.deadline:
        state = "deemed_accepted"
        eligible = True
        reason = "no action by deadline — deemed accepted per IMS default"
    else:
        state = "pending"
        eligible = False
        reason = "awaiting action, deadline not yet reached"

    return {
        "id": inv.id,
        "state": state,
        "itc_eligible": eligible,
        "reason": reason,
        "itc_paise": inv.itc_paise,
    }


def ims_disposition(invoices: list[InwardInvoice], as_of: date) -> DispositionResult:
    """Per-invoice disposition + aggregate eligible ITC (paise summed over
    accepted/deemed_accepted rows only). Deterministic — ``as_of`` is injected."""
    rows = [_disposition(inv, as_of) for inv in invoices]
    eligible_itc_total_paise = sum(row["itc_paise"] for row in rows if row["itc_eligible"])
    return {"invoices": rows, "eligible_itc_total_paise": eligible_itc_total_paise}
