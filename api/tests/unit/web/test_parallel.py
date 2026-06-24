"""Layer 6 parallel run: start, observe, reconcile against captured metrics, GO/HOLD gate."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core import history_store, parallel
from app.domains import build_registry

_DAY = date(2026, 6, 24)


def _capture(session: Session) -> None:
    history_store.capture(
        session, build_registry(), captured_at=_DAY.isoformat(), as_of=_DAY
    )


def test_start_and_active(session: Session) -> None:
    assert parallel.active_run(session) is None
    run = parallel.start_run(session, name="Run A", started_on=_DAY, days=30)
    assert run.started_on == "2026-06-24"
    assert run.ends_on == "2026-07-24"
    assert parallel.active_run(session).id == run.id  # type: ignore[union-attr]


def test_reconcile_match_and_mismatch(session: Session) -> None:
    _capture(session)
    run = parallel.start_run(session, name="R", started_on=_DAY)
    # gst gstr3b_days_late is 0 on a clean DB; matching external -> ✓, off-by-one -> ⚠
    maisha = parallel._maisha_value(session, "gst", "gstr3b_days_late", _DAY.isoformat())
    assert maisha == 0.0
    parallel.record_observation(session, run_id=run.id, observed_on=_DAY,
                                domain="gst", metric="gstr3b_days_late", external_value=0.0)
    parallel.record_observation(session, run_id=run.id, observed_on=_DAY,
                                domain="gst", metric="gstr3b_days_late", external_value=5.0)
    recs = parallel.reconcile(session, run)
    assert [r.ok for r in recs] == [True, False]
    assert recs[1].variance == 5.0


def test_reconcile_no_capture_is_not_ok(session: Session) -> None:
    run = parallel.start_run(session, name="R", started_on=_DAY)  # no capture taken
    parallel.record_observation(session, run_id=run.id, observed_on=_DAY,
                                domain="treasury", metric="cash", external_value=100.0)
    rec = parallel.reconcile(session, run)[0]
    assert rec.maisha is None and rec.variance is None and rec.ok is False


def test_readiness_go_requires_full_window_and_all_match(session: Session) -> None:
    _capture(session)
    run = parallel.start_run(session, name="R", started_on=_DAY)
    parallel.record_observation(session, run_id=run.id, observed_on=_DAY,
                                domain="gst", metric="gstr3b_days_late", external_value=0.0)
    # one matching comparison on one day -> HOLD (needs the full window)
    hold = parallel.readiness(session, run, min_days=30)
    assert hold.recommendation == "HOLD"
    assert hold.matches == 1 and hold.mismatches == 0
    # with min_days satisfied and all matching -> GO
    go = parallel.readiness(session, run, min_days=1)
    assert go.recommendation == "GO"
    assert go.agreement_pct == 100.0


def test_readiness_hold_lists_discrepancies(session: Session) -> None:
    _capture(session)
    run = parallel.start_run(session, name="R", started_on=_DAY)
    parallel.record_observation(session, run_id=run.id, observed_on=_DAY,
                                domain="gst", metric="gstr3b_days_late", external_value=9.0)
    rep = parallel.readiness(session, run, min_days=1)
    assert rep.recommendation == "HOLD"
    assert len(rep.discrepancies) == 1
