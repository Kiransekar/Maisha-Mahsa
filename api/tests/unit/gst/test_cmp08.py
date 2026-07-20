"""WS1.D3 — CMP-08 quarterly composition statement artifact.

Composition RATES are not spec-stated (§0.6): every test injects ``composition_rate``
explicitly; ``test_missing_rate_raises`` proves the no-default guard.
"""

from datetime import date

from app.domains.gst import cmp08
from app.domains.gst.gst_calc import interest_3b

REQUIRED_FIELDS = {
    "form",
    "period",
    "gstin",
    "legal_name",
    "composition_rate_pct",
    "outward_taxable_value",
    "outward_tax_payable",
    "rcm_taxable_value",
    "rcm_tax_payable",
    "tax_payable",
    "due_date",
    "filed_date",
    "days_late",
    "interest_payable",
    "total_payable",
}


def test_cmp08_artifact_shape_snapshot():
    # Injected composition_rate=1 (trader rate) — not invented, supplied by the caller.
    result = cmp08.build_cmp08(
        "2026-04/2026-06",
        {
            "gstin": "27AAAAA0000A1Z5",
            "legal_name": "Test Traders",
            "outward_taxable_value": 10_00_000,  # paise: Rs.10,000
        },
        composition_rate="1",
        due_date=date(2026, 7, 18),
        filed_date=date(2026, 7, 18),
    )
    assert result.keys() >= REQUIRED_FIELDS
    assert result["form"] == "CMP-08"
    assert result["period"] == "2026-04/2026-06"
    assert result["outward_tax_payable"] == 10_000  # 1% of 10,00,000 paise
    assert result["rcm_taxable_value"] == 0
    assert result["rcm_tax_payable"] == 0
    assert result["tax_payable"] == 10_000
    assert result["days_late"] == 0
    assert result["interest_payable"] == 0
    assert result["total_payable"] == 10_000


def test_cmp08_rounding_half_up_exact_paise():
    # 5% of 10,101 paise = 505.05 -> 505 (ROUND_HALF_UP on exact Decimal, no float)
    result = cmp08.build_cmp08(
        "2026-04/2026-06",
        {"outward_taxable_value": 10_101},
        composition_rate="5",
        due_date=date(2026, 7, 18),
        filed_date=date(2026, 7, 18),
    )
    assert result["outward_tax_payable"] == 505


def test_cmp08_rcm_inward_taxed_at_supply_rate_not_composition_rate():
    result = cmp08.build_cmp08(
        "2026-04/2026-06",
        {
            "outward_taxable_value": 10_00_000,
            "rcm_supplies": [{"taxable": 1_00_000, "rate": 18}],  # normal 18%, not the 1% comp rate
        },
        composition_rate="1",
        due_date=date(2026, 7, 18),
        filed_date=date(2026, 7, 18),
    )
    assert result["rcm_taxable_value"] == 1_00_000
    assert result["rcm_tax_payable"] == 18_000  # 18% of 1,00,000, not 1%
    assert result["tax_payable"] == 10_000 + 18_000


def test_cmp08_interest_delegates_to_ported_interest_3b():
    due = date(2026, 7, 18)
    filed = date(2026, 8, 2)  # 15 days late
    result = cmp08.build_cmp08(
        "2026-04/2026-06",
        {"outward_taxable_value": 10_00_000},
        composition_rate="1",
        due_date=due,
        filed_date=filed,
    )
    days_late = (filed - due).days
    assert result["days_late"] == days_late
    assert result["interest_payable"] == interest_3b(result["tax_payable"], days_late)
    assert result["interest_payable"] > 0
    assert result["total_payable"] == result["tax_payable"] + result["interest_payable"]


def test_cmp08_on_time_interest_zero():
    result = cmp08.build_cmp08(
        "2026-04/2026-06",
        {"outward_taxable_value": 10_00_000},
        composition_rate="1",
        due_date=date(2026, 7, 18),
        filed_date=date(2026, 7, 10),  # filed early
    )
    assert result["days_late"] == 0
    assert result["interest_payable"] == 0


def test_missing_composition_rate_raises():
    # §0.6: composition rate is not a spec-stated value -> no default, caller must inject.
    try:
        cmp08.build_cmp08(  # type: ignore[call-arg]
            "2026-04/2026-06",
            {"outward_taxable_value": 10_00_000},
            due_date=date(2026, 7, 18),
            filed_date=date(2026, 7, 18),
        )
        raise AssertionError("expected TypeError for missing composition_rate")
    except TypeError:
        pass


def test_missing_outward_taxable_value_raises():
    try:
        cmp08.build_cmp08(
            "2026-04/2026-06",
            {},
            composition_rate="1",
            due_date=date(2026, 7, 18),
            filed_date=date(2026, 7, 18),
        )
        raise AssertionError("expected KeyError for missing outward_taxable_value")
    except KeyError:
        pass
