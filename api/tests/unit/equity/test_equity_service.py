from datetime import date

from app.domains.equity.service import EquityService


def _cap_table(session, esop_shares=100000):
    svc = EquityService()
    svc.add_shareholder(session, name="Founder", category="founder", shares_held=700000)
    svc.add_shareholder(session, name="VC", category="investor", shares_held=200000)
    svc.add_shareholder(session, name="ESOP Pool", category="esop", shares_held=esop_shares)
    return svc


def test_cap_table_and_pool(session):
    svc = _cap_table(session)
    cap = svc.cap_table(session)
    assert cap["total_shares"] == 1000000
    assert svc.esop_pool_pct(session) == 0.1


def test_build_snapshot_pool_within_cap_is_healthy(session):
    svc = _cap_table(session, esop_shares=100000)  # exactly 10%
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["metrics"]["esop_pool_pct"] == 0.1
    assert snap["metrics"]["esop_board_approved"] == 1  # no snapshot -> assumed approved


def test_build_snapshot_unapproved_pool_flags_board(session):
    svc = _cap_table(session, esop_shares=150000)  # ~13%
    svc.snapshot_cap_table(session, snapshot_date="2026-06-01", esop_board_approved=False)
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["metrics"]["esop_pool_pct"] > 0.10
    assert snap["metrics"]["esop_board_approved"] == 0
    assert snap["metrics"]["board_compliance"] == 0.0


def test_convert_safe_via_service(session):
    from app.core.money import Paise

    svc = EquityService()
    res = svc.convert_safe(
        investment=Paise.from_rupees(5000000),
        valuation_cap=Paise.from_rupees(50000000),
        discount_rate=0.20,
        round_price_per_share=Paise.from_rupees(100),
        pre_round_shares=1000000,
    )
    assert res["shares_issued"] == 100000
