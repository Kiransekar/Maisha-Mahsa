"""P3: forecast revenue-recognition timing, revenue export invoicing, expense card recon."""

from app.core.money import Paise
from app.domains.expense import expense_calc
from app.domains.forecast import forecast_calc
from app.domains.revenue import revenue_calc


def test_revenue_recognition_forecast_straight_line():
    contracts = [
        {"total_paise": Paise.from_rupees(120000), "start": "2026-01", "term_months": 12},
    ]
    out = forecast_calc.revenue_recognition_forecast(
        contracts, horizon_months=12, start="2026-01"
    )
    assert len(out["monthly"]) == 12
    assert out["monthly"][0] == Paise.from_rupees(10000)  # 120000 / 12
    assert out["total_recognized"] == Paise.from_rupees(120000)


def test_revenue_recognition_remainder_trued_up():
    contracts = [{"total_paise": 100, "start": "2026-01", "term_months": 3}]  # 100 paise / 3
    out = forecast_calc.revenue_recognition_forecast(contracts, horizon_months=3, start="2026-01")
    assert out["monthly"] == [33, 33, 34]  # remainder into the last month
    assert out["total_recognized"] == 100


def test_export_invoice_with_lut_zero_rated():
    res = revenue_calc.export_invoice(
        Paise.from_rupees(100000), with_lut=True, invoice_date="2026-04-15"
    )
    assert res["igst"] == 0 and res["total"] == Paise.from_rupees(100000)
    assert res["refund_eligible"] is False
    assert res["realization_due_date"] == "2027-01-15"  # +9 months (FEMA)


def test_export_invoice_without_lut_igst_refundable():
    res = revenue_calc.export_invoice(
        Paise.from_rupees(100000), with_lut=False, igst_rate=18.0, invoice_date="2026-04-15"
    )
    assert res["igst"] == Paise.from_rupees(18000)
    assert res["refund_eligible"] is True


def test_card_reconciliation_matches_by_amount_and_date():
    statement = [
        {"id": "s1", "date": "2026-05-10", "amount_paise": Paise.from_rupees(2000)},
        {"id": "s2", "date": "2026-05-15", "amount_paise": Paise.from_rupees(5000)},
    ]
    claims = [
        {"id": "c1", "date": "2026-05-11", "amount_paise": Paise.from_rupees(2000)},
        {"id": "c2", "date": "2026-05-30", "amount_paise": Paise.from_rupees(9999)},
    ]
    res = expense_calc.reconcile_card(statement, claims, date_tolerance_days=3)
    assert res["matched"] == [{"statement_id": "s1", "claim_id": "c1",
                               "amount_paise": Paise.from_rupees(2000)}]
    assert res["unmatched_statement"] == ["s2"]
    assert res["unmatched_claims"] == ["c2"]
    assert res["match_rate"] == 0.5
