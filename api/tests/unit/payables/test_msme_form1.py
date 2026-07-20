"""MSME Form-1 half-yearly return data pack (WS1.D8) — fixture-driven snapshot.

Half-year windows + return due dates (Apr-Sep -> due 31 Oct; Oct-Mar -> due 30 Apr) and the
45-day payment clock (MSMED Act s.15 / ``MSME_PAYMENT_DAYS``) are cited in MASTER_PLAN.md
§WS1.D8. Nothing else is invented here.

Note on semantics: a payable still open beyond 45 days at one period-end is, by definition,
still open at the next period-end too (unless paid) — so it legitimately reappears in
consecutive half-yearly returns. The fixtures below use vendor-specific bills per test to
keep each snapshot legible, plus one explicit test of that carry-over behaviour.
"""

from __future__ import annotations

from datetime import date

from app.core.money import Paise
from app.domains.payables import payables_calc as p

# ---- fixture: open payables for the Apr-Sep 2026 window ----
_PAYABLES_H1 = [
    # MSME, unpaid 121 days by 30 Sep 2026 -> reportable
    {
        "vendor_id": 1,
        "vendor_name": "Alpha Steel",
        "vendor_msme": True,
        "bill_date": "2026-06-01",
        "outstanding_paise": Paise.from_rupees(150000),
    },
    # MSME, unpaid only 10 days by 30 Sep 2026 -> within the 45-day window, not reportable
    {
        "vendor_id": 2,
        "vendor_name": "Beta Traders",
        "vendor_msme": True,
        "bill_date": "2026-09-20",
        "outstanding_paise": Paise.from_rupees(50000),
    },
    # Not MSME-registered -> excluded regardless of age
    {
        "vendor_id": 3,
        "vendor_name": "Gamma Corp",
        "vendor_msme": False,
        "bill_date": "2026-05-01",
        "outstanding_paise": Paise.from_rupees(200000),
    },
    # MSME, fully paid (outstanding 0) -> excluded
    {
        "vendor_id": 4,
        "vendor_name": "Delta MSME",
        "vendor_msme": True,
        "bill_date": "2026-07-01",
        "outstanding_paise": 0,
    },
    # MSME, unpaid 60 days by 30 Sep 2026 -> reportable
    {
        "vendor_id": 5,
        "vendor_name": "Epsilon Micro",
        "vendor_msme": True,
        "bill_date": "2026-08-01",
        "outstanding_paise": Paise.from_rupees(75000),
    },
]

# ---- fixture: open payables for the Oct 2026-Mar 2027 window (fresh vendors, no carryover) ----
_PAYABLES_H2 = [
    {
        "vendor_id": 6,
        "vendor_name": "Zeta Micro",
        "vendor_msme": True,
        "bill_date": "2026-11-01",
        "outstanding_paise": Paise.from_rupees(300000),
    },
    {
        "vendor_id": 7,
        "vendor_name": "Eta Traders",
        "vendor_msme": True,
        "bill_date": "2027-03-20",
        "outstanding_paise": Paise.from_rupees(90000),
    },
]


def test_msme_form1_period_resolves_apr_sep_window():
    assert p.msme_form1_period(date(2026, 7, 15)) == {
        "start": "2026-04-01",
        "end": "2026-09-30",
        "due_date": "2026-10-31",
    }


def test_msme_form1_period_resolves_oct_mar_window_crossing_year():
    # a January date belongs to the Oct(prev year)-Mar(this year) window
    assert p.msme_form1_period(date(2027, 1, 15)) == {
        "start": "2026-10-01",
        "end": "2027-03-31",
        "due_date": "2027-04-30",
    }
    # an October date belongs to the same window
    assert p.msme_form1_period(date(2026, 10, 5)) == {
        "start": "2026-10-01",
        "end": "2027-03-31",
        "due_date": "2027-04-30",
    }


def test_msme_form1_pack_apr_sep_snapshot():
    pack = p.msme_form1_pack(_PAYABLES_H1, date(2026, 9, 30))
    assert pack == {
        "period_start": "2026-04-01",
        "period_end": "2026-09-30",
        "return_due_date": "2026-10-31",
        "total_outstanding_paise": Paise.from_rupees(150000) + Paise.from_rupees(75000),
        "vendor_count": 2,
        "lines": [
            {
                "vendor_id": 1,
                "vendor_name": "Alpha Steel",
                "bill_date": "2026-06-01",
                "outstanding_paise": Paise.from_rupees(150000),
                "days_outstanding": 121,
                "reason_for_delay": "",
            },
            {
                "vendor_id": 5,
                "vendor_name": "Epsilon Micro",
                "bill_date": "2026-08-01",
                "outstanding_paise": Paise.from_rupees(75000),
                "days_outstanding": 60,
                "reason_for_delay": "",
            },
        ],
    }


def test_msme_form1_pack_oct_mar_snapshot():
    pack = p.msme_form1_pack(_PAYABLES_H2, date(2027, 3, 31))
    assert pack == {
        "period_start": "2026-10-01",
        "period_end": "2027-03-31",
        "return_due_date": "2027-04-30",
        "total_outstanding_paise": Paise.from_rupees(300000),
        "vendor_count": 1,
        "lines": [
            {
                "vendor_id": 6,
                "vendor_name": "Zeta Micro",
                "bill_date": "2026-11-01",
                "outstanding_paise": Paise.from_rupees(300000),
                "days_outstanding": 150,
                "reason_for_delay": "",
            },
        ],
    }
    # vendor 7's bill (20 Mar 2027) is only 11 days old at period-end -> not yet reportable
    assert 7 not in {line["vendor_id"] for line in pack["lines"]}


def test_msme_form1_pack_excludes_non_msme_paid_and_within_window():
    pack = p.msme_form1_pack(_PAYABLES_H1, date(2026, 9, 30))
    vendor_ids = {line["vendor_id"] for line in pack["lines"]}
    assert 2 not in vendor_ids  # within 45 days
    assert 3 not in vendor_ids  # not MSME-registered
    assert 4 not in vendor_ids  # fully paid


def test_msme_form1_pack_carries_over_unpaid_dues_into_next_period():
    # A bill still open beyond 45 days at one period-end is, by definition, still open (and
    # still reportable) at the next period-end unless it was paid in the interim.
    still_open = {**_PAYABLES_H1[0], "bill_date": "2026-06-01"}  # Alpha Steel, unpaid
    pack = p.msme_form1_pack([still_open], date(2027, 3, 31))
    assert pack["period_start"] == "2026-10-01"
    assert pack["vendor_count"] == 1
    assert pack["lines"][0]["vendor_id"] == 1
    assert pack["lines"][0]["days_outstanding"] == (date(2027, 3, 31) - date(2026, 6, 1)).days
