"""WS7.7 freshness assembler (UX research T4).

The invariant under test: absent signal is unknown, never healthy — a source with no rows must
report never-synced and must NOT be treated as fresh. Plus: ages come from real rows, and the
stale boundary is exact at the threshold.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.freshness import DEFAULT_THRESHOLD_DAYS, build_freshness
from app.db.models.gst import GstReturn
from app.db.models.payroll import PayrollRun
from app.db.models.treasury import BankAccount, BankTransaction
from app.db.models.vault import Document

AS_OF = date(2026, 7, 20)
ALL_KEYS = {"bank_feeds", "gst_filings", "payroll", "documents"}


def _by_key(report: dict) -> dict[str, dict]:
    return {s["key"]: s for s in report["sources"]}


def _seed_all_fresh(session: Session, day: str = "2026-07-20") -> None:
    session.add_all(
        [
            BankAccount(bank_name="HDFC", account_number="1", ifsc="HDFC0001", last_sync=day),
            GstReturn(
                return_type="GSTR-3B",
                filing_period="2026-06",
                due_date="2026-07-20",
                filed_date=day,
                status="filed",
            ),
            PayrollRun(month_year="2026-06", run_date=day),
            Document(
                id="a" * 64,
                file_name="x.pdf",
                file_path="/x.pdf",
                doc_type="invoice",
                upload_date=day,
                sha256="a" * 64,
            ),
        ]
    )
    session.flush()


def test_empty_db_every_source_never_synced_and_not_healthy(session: Session) -> None:
    report = build_freshness(session, AS_OF)
    sources = _by_key(report)
    assert set(sources) == ALL_KEYS
    for key, s in sources.items():
        assert s["synced"] is False, key
        assert s["last_updated"] is None, key  # never a fabricated date
        assert s["age_days"] is None, key  # never a fabricated 0
        assert s["stale"] is True, key  # unknown is never healthy

    overall = report["overall"]
    assert overall["status"] == "unknown"
    assert overall["healthy"] is False
    assert sorted(overall["never_synced"]) == sorted(ALL_KEYS)
    assert overall["worst_age_days"] is None  # not 0


def test_ages_computed_from_real_rows(session: Session) -> None:
    _seed_all_fresh(session, day="2026-07-18")
    sources = _by_key(build_freshness(session, AS_OF))
    for key, s in sources.items():
        assert s["synced"] is True, key
        assert s["last_updated"] == "2026-07-18", key
        assert s["age_days"] == 2, key
    assert build_freshness(session, AS_OF)["overall"]["worst_age_days"] == 2


def test_bank_feed_falls_back_to_transaction_date_when_account_never_synced(
    session: Session,
) -> None:
    session.add(BankAccount(bank_name="ICICI", account_number="2", ifsc="ICIC0002"))
    session.flush()
    assert _by_key(build_freshness(session, AS_OF))["bank_feeds"]["synced"] is False

    session.add(BankTransaction(account_id=1, txn_date="2026-07-19", credit=100))
    session.flush()
    bank = _by_key(build_freshness(session, AS_OF))["bank_feeds"]
    assert bank["synced"] is True
    assert bank["last_updated"] == "2026-07-19"
    assert bank["age_days"] == 1


def test_stale_boundary_is_exact_at_the_threshold(session: Session) -> None:
    threshold = DEFAULT_THRESHOLD_DAYS["bank_feeds"]
    for age, expected_stale in ((threshold - 1, False), (threshold, False), (threshold + 1, True)):
        session.query(BankAccount).delete()
        last = date.fromordinal(AS_OF.toordinal() - age)
        session.add(
            BankAccount(
                bank_name="HDFC",
                account_number="1",
                ifsc="HDFC0001",
                last_sync=last.isoformat(),
            )
        )
        session.flush()
        bank = _by_key(build_freshness(session, AS_OF))["bank_feeds"]
        assert bank["age_days"] == age
        assert bank["stale"] is expected_stale, f"age={age} threshold={threshold}"


def test_injected_threshold_overrides_the_default(session: Session) -> None:
    _seed_all_fresh(session, day="2026-07-15")  # 5 days old
    assert _by_key(build_freshness(session, AS_OF))["documents"]["stale"] is False
    tight = build_freshness(session, AS_OF, thresholds={"documents": 4})
    assert _by_key(tight)["documents"]["stale"] is True
    assert tight["overall"]["status"] == "stale"
    assert tight["overall"]["healthy"] is False


def test_all_fresh_reads_fresh(session: Session) -> None:
    _seed_all_fresh(session, day="2026-07-20")
    overall = build_freshness(session, AS_OF)["overall"]
    assert overall["status"] == "fresh"
    assert overall["healthy"] is True
    assert overall["never_synced"] == [] and overall["stale"] == []
    assert overall["worst_age_days"] == 0


def test_unparseable_date_is_treated_as_never_synced_not_healthy(session: Session) -> None:
    session.add(
        BankAccount(bank_name="X", account_number="9", ifsc="XXXX0009", last_sync="pending")
    )
    session.flush()
    bank = _by_key(build_freshness(session, AS_OF))["bank_feeds"]
    assert bank["synced"] is False and bank["stale"] is True
