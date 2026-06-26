"""Payables: recurring-payable detection and the payment-run batch (features recurring /
payment_run)."""

from datetime import date

from app.core.money import Paise
from app.db.models.payables import Vendor
from app.domains.payables import payables_calc
from app.domains.payables.service import PayablesService


def test_detect_recurring_flags_monthly_saas():
    bills = [
        {"vendor_id": 1, "vendor_name": "CloudHost", "bill_date": "2026-03-05",
         "amount_paise": Paise.from_rupees(50000)},
        {"vendor_id": 1, "vendor_name": "CloudHost", "bill_date": "2026-04-05",
         "amount_paise": Paise.from_rupees(50000)},
        {"vendor_id": 1, "vendor_name": "CloudHost", "bill_date": "2026-05-05",
         "amount_paise": Paise.from_rupees(52000)},
        # a one-off vendor — should not be flagged
        {"vendor_id": 2, "vendor_name": "Lawyers LLP", "bill_date": "2026-04-01",
         "amount_paise": Paise.from_rupees(200000)},
    ]
    rec = payables_calc.detect_recurring(bills)
    assert len(rec) == 1
    r = rec[0]
    assert r["vendor_id"] == 1 and r["occurrences"] == 3
    assert r["category"] == "saas_recurring"
    assert r["predicted_next_date"].startswith("2026-06")


def _vendor(session, name="V", msme=False, bank="123", ifsc="HDFC0001"):
    v = Vendor(name=name, payee_type="company", msme_status=1 if msme else 0,
               payment_terms=30, bank_account=bank, ifsc=ifsc)
    session.add(v)
    session.flush()
    return v


def test_recurring_payables_service(session):
    svc = PayablesService()
    v = _vendor(session, name="CloudHost")
    for d in ("2026-03-05", "2026-04-05", "2026-05-05"):
        svc.create_bill(session, bill_number=f"B-{d}", vendor_id=v.id, bill_date=d,
                        subtotal=Paise.from_rupees(50000))
    rec = svc.recurring_payables(session)
    assert any(r["vendor_id"] == v.id for r in rec)


def test_payment_run_batches_and_executes(session):
    svc = PayablesService()
    msme = _vendor(session, name="Micro Co", msme=True)
    reg = _vendor(session, name="Big Co", msme=False)
    # both due before the run date
    svc.create_bill(session, bill_number="R1", vendor_id=reg.id, bill_date="2026-04-01",
                    subtotal=Paise.from_rupees(100000))
    svc.create_bill(session, bill_number="M1", vendor_id=msme.id, bill_date="2026-04-10",
                    subtotal=Paise.from_rupees(40000))

    batch = svc.payment_run(session, date(2026, 6, 1))
    assert batch["count"] == 2
    assert batch["total_paise"] == Paise.from_rupees(140000)
    assert batch["lines"][0]["is_msme"] is True  # MSME prioritised first
    assert batch["executed"] is False

    # executing marks the bills paid -> a second run is empty
    svc.payment_run(session, date(2026, 6, 1), execute=True)
    assert svc.payment_run(session, date(2026, 6, 1))["count"] == 0
