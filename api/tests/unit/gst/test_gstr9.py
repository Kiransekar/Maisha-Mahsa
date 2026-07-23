"""GSTR-9 annual return consolidated from GSTR-1 + GSTR-3B — deferred feature."""

from __future__ import annotations

from app.core.money import Paise
from app.domains.gst.gst_calc import gstr9_annual

# Two months: each ₹1,00,000 taxable @ 18% intra-state (9% CGST + 9% SGST).
_G1 = [
    {
        "taxable": Paise.from_rupees(100000),
        "igst": 0,
        "cgst": Paise.from_rupees(9000),
        "sgst": Paise.from_rupees(9000),
    },
    {
        "taxable": Paise.from_rupees(100000),
        "igst": 0,
        "cgst": Paise.from_rupees(9000),
        "sgst": Paise.from_rupees(9000),
    },
]


def _g3b(out_cgst: int) -> list[dict]:
    return [
        {
            "output": {"igst": 0, "cgst": out_cgst, "sgst": Paise.from_rupees(9000)},
            "itc": {"igst": 0, "cgst": Paise.from_rupees(5000), "sgst": Paise.from_rupees(5000)},
            "tax_paid_cash": Paise.from_rupees(8000),
        },
        {
            "output": {"igst": 0, "cgst": Paise.from_rupees(9000), "sgst": Paise.from_rupees(9000)},
            "itc": {"igst": 0, "cgst": Paise.from_rupees(5000), "sgst": Paise.from_rupees(5000)},
            "tax_paid_cash": Paise.from_rupees(8000),
        },
    ]


def test_reconciles_when_gstr1_matches_3b() -> None:
    r = gstr9_annual(_G1, _g3b(Paise.from_rupees(9000)))
    assert r["periods"] == 2
    assert r["outward_per_gstr1"]["taxable"] == Paise.from_rupees(200000)
    assert r["outward_per_gstr1"]["total_tax"] == Paise.from_rupees(36000)  # 2×(9k+9k)
    assert r["output_tax_per_gstr3b"]["total"] == Paise.from_rupees(36000)
    assert r["itc_availed"]["total"] == Paise.from_rupees(20000)  # 2×(5k+5k)
    assert r["tax_paid_cash"] == Paise.from_rupees(16000)
    assert r["differential_tax"] == 0 and r["reconciled"] is True


def test_under_declared_in_3b_flags_additional_liability() -> None:
    # one month declared only ₹8,000 CGST in 3B vs ₹9,000 in GSTR-1 -> ₹1,000 short
    r = gstr9_annual(_G1, _g3b(Paise.from_rupees(8000)))
    assert r["differential_tax"] == Paise.from_rupees(1000)
    assert r["reconciled"] is False
