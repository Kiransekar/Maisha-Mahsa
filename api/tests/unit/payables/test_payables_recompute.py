"""Payables emits Prime-Directive recompute claims (§0.4) with the SAME inputs create_bill
computed tds_amount on, so Mahsa recomputes the identical figure. tds_category is a transient
create_bill argument (not persisted on Bill) — recompute_claims recovers it by replaying the
section's rate candidates against the stored tds_amount; these round-trip assertions prove that
recovery is exact, not guessed. The live block behaviour against the real Mahsa binary is proven
in tests/integration/test_full_loop.py."""

from app.core.money import Paise
from app.db.models.payables import Vendor
from app.domains.payables import payables_calc
from app.domains.payables.service import PayablesService


def _vendor(session, *, tds_section=None, payee_type="company"):
    v = Vendor(name="Vend", tds_section=tds_section, payee_type=payee_type, payment_terms=30)
    session.add(v)
    session.flush()
    return v


def _round_trip(claims):
    for c in claims:
        assert c.target == "tds_on_payment"
        assert payables_calc.tds_on_payment(**c.inputs)["tds_paise"] == c.claimed_paise


def test_claims_round_trip_for_plain_194c_and_194h(session):
    svc = PayablesService()
    vc = _vendor(session, tds_section="194C")
    svc.create_bill(
        session,
        bill_number="B1",
        vendor_id=vc.id,
        bill_date="2026-05-10",
        subtotal=Paise.from_rupees(40000),
    )
    vh = _vendor(session, tds_section="194H")
    svc.create_bill(
        session,
        bill_number="B2",
        vendor_id=vh.id,
        bill_date="2026-05-11",
        subtotal=Paise.from_rupees(25000),
    )
    claims = svc.recompute_claims(session)
    assert len(claims) == 2
    _round_trip(claims)
    assert claims[0].claimed_paise == Paise.from_rupees(800)  # 194C company 2% of 40k
    assert claims[1].claimed_paise == Paise.from_rupees(500)  # 194H 2% of 25k


def test_claims_recover_194j_technical_category(session):
    svc = PayablesService()
    v = _vendor(session, tds_section="194J")
    res = svc.create_bill(
        session,
        bill_number="B3",
        vendor_id=v.id,
        bill_date="2026-05-12",
        subtotal=Paise.from_rupees(100000),
        tds_category="technical",
    )
    assert res["tds_amount"] == Paise.from_rupees(2000)  # technical sub-rate 2%, not 10%
    claims = svc.recompute_claims(session)
    assert len(claims) == 1
    assert claims[0].inputs["category"] == "technical"
    _round_trip(claims)


def test_claims_recover_194i_plant_category(session):
    svc = PayablesService()
    v = _vendor(session, tds_section="194I")
    res = svc.create_bill(
        session,
        bill_number="B4",
        vendor_id=v.id,
        bill_date="2026-05-13",
        subtotal=Paise.from_rupees(60000),
        tds_category="plant",
    )
    assert res["tds_amount"] == Paise.from_rupees(1200)  # plant sub-rate 2%, not building 10%
    claims = svc.recompute_claims(session)
    assert len(claims) == 1
    assert claims[0].inputs["category"] == "plant"
    _round_trip(claims)


def test_no_claim_below_threshold_or_without_tds_section(session):
    svc = PayablesService()
    below = _vendor(session, tds_section="194J")
    svc.create_bill(
        session,
        bill_number="B5",
        vendor_id=below.id,
        bill_date="2026-05-14",
        subtotal=Paise.from_rupees(1000),  # below ₹50k threshold -> tds_amount 0
    )
    no_section = _vendor(session, tds_section=None)
    svc.create_bill(
        session,
        bill_number="B6",
        vendor_id=no_section.id,
        bill_date="2026-05-15",
        subtotal=Paise.from_rupees(100000),
    )
    claims = svc.recompute_claims(session)
    assert claims == []


def test_only_tds_on_payment_targets_emitted(session):
    svc = PayablesService()
    v = _vendor(session, tds_section="194C", payee_type="individual")
    svc.create_bill(
        session,
        bill_number="B7",
        vendor_id=v.id,
        bill_date="2026-05-16",
        subtotal=Paise.from_rupees(40000),
    )
    claims = svc.recompute_claims(session)
    targets = {c.target for c in claims}
    assert targets == {"tds_on_payment"}
    _round_trip(claims)
    assert claims[0].claimed_paise == Paise.from_rupees(400)  # individual 194C rate 1%
