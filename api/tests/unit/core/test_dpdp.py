"""WS10.1 — DPDP rights-workflow tests.

What these prove, mutation-first:

1. **SLA math is exact** — received + 90 calendar days, across month/year boundaries.
2. **The legal hold is load-bearing** — an erasure over retained statutory records is created
   ``held`` with the statutory basis, and ``close_request`` REFUSES to complete it (raises,
   row unchanged, no closed event sealed). Removing the ``erasure_hold`` check from either
   path fails a test here — that is the ticket's mutation lock.
3. **The calendar is reused, not forked** — creating a request writes a real
   ``ComplianceCalendar`` row via ``ComplianceService.add_deadline``; completing marks it
   filed via ``mark_filed``.
4. **The processing log is the audit chain** — lifecycle events land in ``audit_log`` as a
   verifiable hash chain.
5. **Consent re-acceptance on version bump** — the WS10.4 acceptance mechanics extended to the
   DPDP notice: a bump of the in-force version makes the gate raise until re-acceptance; with
   nothing published the gate is a no-op (drafts publish nothing, §0.6).
6. **Tenancy fails closed** — no bound org: every entry point raises; another org's requests
   are invisible.

Self-contained DB setup (test_legal.py precedent): only the tables this suite touches.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import dpdp, legal
from app.core.legal import DocType, OrgUnboundError, PublishedVersion
from app.core.principal import (
    reset_current_org,
    reset_current_user,
    set_current_org,
    set_current_user,
)
from app.db.base import Base
from app.db.models.legal import DpdpRightsRequest, LegalAcceptance
from app.db.models.shared import AuditLog, ComplianceCalendar
from app.db.models.vault import Document

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(
        engine,
        tables=[
            DpdpRightsRequest.__table__,
            LegalAcceptance.__table__,
            ComplianceCalendar.__table__,
            AuditLog.__table__,
            Document.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def as_org_a() -> Iterator[None]:
    org_token = set_current_org(ORG_A)
    user_token = set_current_user("user-owner-a")
    try:
        yield
    finally:
        reset_current_user(user_token)
        reset_current_org(org_token)


def _retained_invoice(db: Session, upload_date: str = "2026-01-10") -> Document:
    """A statutory-class document whose retention (8y from FY-end, vault machinery) is live
    for any as_of this suite uses. retention_until computed by the REAL vault calc."""
    from app.domains.vault import vault_calc

    doc = Document(
        id=f"sha-{upload_date}",
        file_name="invoice.pdf",
        file_path="/x/invoice.pdf",
        doc_type="invoice",
        upload_date=upload_date,
        retention_until=vault_calc.retention_until(upload_date, "invoice"),
        sha256=f"sha-{upload_date}",
    )
    db.add(doc)
    db.flush()
    return doc


# ---- 1. SLA math ---------------------------------------------------------------------


def test_sla_due_date_is_received_plus_90_calendar_days() -> None:
    assert dpdp.sla_due_date("2026-07-23") == "2026-10-21"
    assert dpdp.sla_due_date("2026-01-01") == "2026-04-01"
    # year boundary
    assert dpdp.sla_due_date("2026-11-15") == "2027-02-13"
    # leap-adjacent: 2028 is a leap year
    assert dpdp.sla_due_date("2027-12-15") == "2028-03-14"


def test_create_rejects_garbage(db: Session, as_org_a: None) -> None:
    with pytest.raises(ValueError):
        dpdp.create_request(
            db, requester="A", request_type="obliterate", received_date="2026-07-23"
        )
    with pytest.raises(ValueError):
        dpdp.create_request(db, requester="A", request_type="access", received_date="not-a-date")
    assert db.scalars(select(DpdpRightsRequest)).all() == []


# ---- 2+3. workflow, calendar reuse ---------------------------------------------------


def test_access_request_is_open_and_lands_on_the_compliance_calendar(
    db: Session, as_org_a: None
) -> None:
    res = dpdp.create_request(
        db, requester="A. Kumar", request_type="access", received_date="2026-07-23"
    )
    assert res["status"] == "open"
    assert res["due_date"] == "2026-10-21"
    assert res["hold_basis"] is None

    # The EXISTING calendar machinery holds the SLA deadline — same table every statutory
    # deadline uses, domain "dpdp", pending, no requester PII in the shared calendar row.
    cal = db.scalars(select(ComplianceCalendar)).one()
    assert cal.domain == "dpdp"
    assert cal.due_date == "2026-10-21"
    assert cal.status == "pending"
    assert "A. Kumar" not in cal.form_name
    assert f"#{res['id']}" in cal.form_name


def test_completing_a_request_files_its_calendar_row(db: Session, as_org_a: None) -> None:
    res = dpdp.create_request(
        db, requester="A. Kumar", request_type="access", received_date="2026-07-23"
    )
    closed = dpdp.close_request(db, res["id"], closed_date="2026-08-01")
    assert closed["status"] == "completed"
    assert closed["closed_date"] == "2026-08-01"

    cal = db.scalars(select(ComplianceCalendar)).one()
    assert cal.status == "filed"
    assert cal.filed_date == "2026-08-01"

    with pytest.raises(ValueError, match="already completed"):
        dpdp.close_request(db, res["id"], closed_date="2026-08-02")


# ---- 2. THE legal hold (mutation lock) -----------------------------------------------


def test_erasure_touching_retained_records_is_held_with_the_statutory_basis(
    db: Session, as_org_a: None
) -> None:
    _retained_invoice(db)
    res = dpdp.create_request(
        db, requester="B. Rao", request_type="erasure", received_date="2026-07-23"
    )
    assert res["status"] == "held"
    assert res["hold_basis"] is not None
    assert "128(5)" in res["hold_basis"]  # Companies Act 2013 s.128(5), the sourced basis
    assert "eight financial years" in res["hold_basis"]


def test_held_erasure_cannot_be_completed_and_nothing_changes(db: Session, as_org_a: None) -> None:
    """THE mutation lock: remove the ``erasure_hold`` call from ``close_request`` and this
    fails — the erasure would complete over records still under the retention duty."""
    doc = _retained_invoice(db)
    res = dpdp.create_request(
        db, requester="B. Rao", request_type="erasure", received_date="2026-07-23"
    )
    events_before = len(db.scalars(select(AuditLog)).all())

    with pytest.raises(dpdp.LegalHoldError, match="128\\(5\\)"):
        dpdp.close_request(db, res["id"], closed_date="2026-08-01")

    row = db.get(DpdpRightsRequest, res["id"])
    assert row is not None and row.status == "held" and row.closed_date is None
    # No closed event was sealed, the calendar row is still pending, the document untouched.
    assert len(db.scalars(select(AuditLog)).all()) == events_before
    assert db.scalars(select(ComplianceCalendar)).one().status == "pending"
    assert db.get(Document, doc.id) is not None


def test_erasure_completes_once_retention_has_lapsed(db: Session, as_org_a: None) -> None:
    """Same org, same document — but closing AFTER the vault-computed retention_until: the
    hold is re-evaluated as of the close date (creation-time state is not trusted)."""
    doc = _retained_invoice(db, upload_date="2026-01-10")
    assert doc.retention_until == "2034-03-31"  # vault: 8y from FY-end (§WS1.C5)
    res = dpdp.create_request(
        db, requester="B. Rao", request_type="erasure", received_date="2026-07-23"
    )
    assert res["status"] == "held"

    closed = dpdp.close_request(db, res["id"], closed_date="2034-04-01")
    assert closed["status"] == "completed"


def test_erasure_with_no_retained_statutory_records_is_open(db: Session, as_org_a: None) -> None:
    # An operational-class doc (3y from upload) already lapsed by receipt — no hold.
    from app.domains.vault import vault_calc

    db.add(
        Document(
            id="sha-op",
            file_name="notes.txt",
            file_path="/x/notes.txt",
            doc_type="misc",
            upload_date="2020-01-01",
            retention_until=vault_calc.retention_until("2020-01-01", "misc"),
            sha256="sha-op",
        )
    )
    db.flush()
    res = dpdp.create_request(db, requester="C", request_type="erasure", received_date="2026-07-23")
    assert res["status"] == "open" and res["hold_basis"] is None


# ---- 4. processing log = the audit chain ---------------------------------------------


def test_lifecycle_events_are_sealed_on_a_verifiable_chain(db: Session, as_org_a: None) -> None:
    from app.core.audit import verify_chain
    from app.core.audit_store import load_chain

    res = dpdp.create_request(
        db, requester="A", request_type="correction", received_date="2026-07-23"
    )
    dpdp.close_request(db, res["id"], closed_date="2026-08-01")

    entries = load_chain(db)
    actions = [e.action for e in entries]
    assert "dpdp.request_created" in actions
    assert "dpdp.request_closed" in actions
    created = next(e for e in entries if e.action == "dpdp.request_created")
    assert created.user_id == "user-owner-a"  # attributed to the verified caller
    assert verify_chain(entries)


# ---- 5. consent — re-acceptance on version bump (WS10.4 mechanics, DPDP notice) ------

NOW = datetime(2026, 7, 23, 12, 0, 0)
LATER = datetime(2026, 8, 10, 9, 0, 0)

NOTICE_V1 = PublishedVersion(DocType.DPDP_NOTICE, "v1", NOW, "docs/legal/DPDP_NOTICE_DRAFT.md")
NOTICE_V2 = PublishedVersion(DocType.DPDP_NOTICE, "v2", LATER, "docs/legal/DPDP_NOTICE_DRAFT.md")


def test_nothing_published_means_the_gate_is_a_noop(db: Session, as_org_a: None) -> None:
    # The REAL registry is empty while every doc is a counsel-gated draft — the gate must not
    # invent an obligation (§0.6), so onboarding/ingestion proceed.
    legal.require_current_acceptance(db, "user-1", DocType.DPDP_NOTICE, NOW)


def test_version_bump_forces_reacceptance(db: Session, as_org_a: None) -> None:
    registry = (NOTICE_V1,)
    with pytest.raises(legal.ReacceptanceRequiredError, match="dpdp_notice"):
        legal.require_current_acceptance(db, "user-1", DocType.DPDP_NOTICE, NOW, registry)

    legal.record_acceptance(db, "user-1", DocType.DPDP_NOTICE, "v1", NOW, registry)
    legal.require_current_acceptance(db, "user-1", DocType.DPDP_NOTICE, NOW, registry)  # ok now

    # v2 comes into force -> the SAME user must re-accept; v1 acceptance no longer suffices.
    registry = (NOTICE_V1, NOTICE_V2)
    with pytest.raises(legal.ReacceptanceRequiredError, match="v2"):
        legal.require_current_acceptance(db, "user-1", DocType.DPDP_NOTICE, LATER, registry)
    legal.record_acceptance(db, "user-1", DocType.DPDP_NOTICE, "v2", LATER, registry)
    legal.require_current_acceptance(db, "user-1", DocType.DPDP_NOTICE, LATER, registry)


def test_published_notice_with_no_verified_user_fails_closed(db: Session, as_org_a: None) -> None:
    with pytest.raises(legal.ReacceptanceRequiredError):
        legal.require_current_acceptance(db, None, DocType.DPDP_NOTICE, NOW, (NOTICE_V1,))


# ---- 6. tenancy ----------------------------------------------------------------------


def test_no_bound_org_fails_closed(db: Session) -> None:
    with pytest.raises(OrgUnboundError):
        dpdp.create_request(db, requester="A", request_type="access", received_date="2026-07-23")
    with pytest.raises(OrgUnboundError):
        dpdp.list_requests(db)
    with pytest.raises(OrgUnboundError):
        dpdp.close_request(db, 1, closed_date="2026-07-23")


def test_requests_are_invisible_across_orgs(db: Session) -> None:
    token = set_current_org(ORG_A)
    try:
        res = dpdp.create_request(
            db, requester="A", request_type="access", received_date="2026-07-23"
        )
    finally:
        reset_current_org(token)

    token = set_current_org(ORG_B)
    try:
        assert dpdp.list_requests(db) == []
        with pytest.raises(ValueError, match="not found"):
            dpdp.close_request(db, res["id"], closed_date="2026-08-01")
    finally:
        reset_current_org(token)


# ---- §0.8 — migration matches the reviewed SQL (test_legal.py precedent) -------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_migration_sql_is_a_verbatim_snapshot_of_the_reviewed_file() -> None:
    path = _repo_root() / "api/alembic/versions/0010_dpdp_rights.py"
    spec = importlib.util.spec_from_file_location("rev_0010", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    on_disk = _repo_root().joinpath("infra/db/multitenant/008_dpdp.sql").read_text("utf-8")
    assert module._008_SQL.strip() == on_disk.strip()
    assert module.down_revision == "0009_itc_ims_action"


def test_migration_ships_rls_and_a_policy_for_the_new_table() -> None:
    sql = _repo_root().joinpath("infra/db/multitenant/008_dpdp.sql").read_text("utf-8")
    assert "CREATE TABLE dpdp_rights_request" in sql
    assert "ALTER TABLE dpdp_rights_request ENABLE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY dpdp_rights_request_tenant ON dpdp_rights_request" in sql
    assert "org_id = app_current_org()" in sql
    # lifecycle updates are allowed; deleting the evidence is not
    assert "GRANT SELECT, INSERT, UPDATE ON dpdp_rights_request TO maisha_app;" in sql
    assert "DELETE" not in sql.split("GRANT")[-1]
    # the acceptance log admits the dpdp notice
    assert "'dpdp_notice'" in sql
