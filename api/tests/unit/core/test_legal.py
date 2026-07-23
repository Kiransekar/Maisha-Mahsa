"""WS10.4 — legal kit tests.

What these have to prove, beyond "the happy path returns something":

1. **The doc_type filter in ``latest_acceptance`` is real.** Deleting it used to leave the whole
   suite green, so a user who accepted the Privacy Policy read as having accepted the ToS. The
   tests below accept ONE doc type and assert the OTHER is still unaccepted, so the filter's
   absence is a failure, not an unobserved detail. Same for the ``org_id`` filter.
2. **``effective_at`` is honoured.** A future-dated version is not in force and must not trigger
   re-acceptance; the latest past-dated one wins regardless of registry order.
3. **The table's tenant scoping is real.** ``org_id`` is never a parameter — it comes from
   :func:`app.core.principal.current_org`, the contextvar the auth middleware binds from a
   verified JWT — and with no org bound every entry point raises instead of reading globally.
4. **The migration matches the reviewed SQL.** The Alembic revision inlines a snapshot of
   ``infra/db/multitenant/004_legal.sql``; a test asserts they have not drifted, because the RLS
   coverage gate only reads the .sql and only the migration reaches a production database.

Self-contained DB setup (this ticket owns only this test file, not the shared
``tests/conftest.py`` fixture or ``app/db/models/__init__.py``).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import legal
from app.core.legal import DocType, PublishedVersion
from app.core.principal import reset_current_org, set_current_org
from app.db.base import Base
from app.db.models import legal as legal_models

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"

NOW = datetime(2026, 7, 21, 12, 0, 0)
LATER = datetime(2026, 8, 1, 9, 0, 0)
MUCH_LATER = datetime(2027, 1, 1, 0, 0, 0)

TOS_V1 = PublishedVersion(DocType.TOS, "v1", NOW, "docs/legal/TOS_DRAFT.md")
TOS_V2 = PublishedVersion(DocType.TOS, "v2", LATER, "docs/legal/TOS_DRAFT.md")
PRIVACY_V1 = PublishedVersion(DocType.PRIVACY, "v1", NOW, "docs/legal/PRIVACY_DRAFT.md")

REGISTRY = (TOS_V1, TOS_V2, PRIVACY_V1)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=[legal_models.LegalAcceptance.__table__])
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def org_a() -> Iterator[None]:
    """Bind ORG_A the way the auth middleware does — via the real contextvar, not a parameter."""
    token = set_current_org(ORG_A)
    try:
        yield
    finally:
        reset_current_org(token)


# ---------------------------------------------------------------------------------------
# The disclaimer string — byte-exact per §WS10.4
# ---------------------------------------------------------------------------------------


def test_disclaimer_text_is_byte_exact():
    assert legal.DISCLAIMER_TEXT == (
        "software tool, not the practice of chartered accountancy; "
        "outputs require professional verification"
    )


# ---------------------------------------------------------------------------------------
# §0.6 — nothing is published, because every document is still a draft for counsel
# ---------------------------------------------------------------------------------------


def test_nothing_is_published_while_the_documents_are_drafts():
    # Listing a TODO(counsel)-marked draft as a published, acceptable legal document would be
    # exactly the invented legal assertion §0.6 forbids.
    assert legal.PUBLISHED == ()
    assert legal.current_version(DocType.TOS, MUCH_LATER) is None


def test_every_legal_document_is_headed_draft_for_counsel_review():
    docs = sorted(Path(__file__).resolve().parents[4].joinpath("docs/legal").glob("*.md"))
    assert docs, "docs/legal/*.md not found"
    for doc in docs:
        assert "DRAFT FOR COUNSEL REVIEW" in doc.read_text(encoding="utf-8").split("\n#")[0], doc


# ---------------------------------------------------------------------------------------
# effective_at is authoritative (ticket item 3) — not write-only decoration
# ---------------------------------------------------------------------------------------


def test_current_version_is_none_before_anything_takes_effect():
    before = datetime(2026, 1, 1)
    assert legal.current_version(DocType.TOS, before, REGISTRY) is None


def test_current_version_ignores_a_version_not_yet_in_force():
    # v2 is dated LATER; at NOW the in-force version is still v1.
    assert legal.current_version(DocType.TOS, NOW, REGISTRY) == "v1"


def test_current_version_advances_once_the_later_version_takes_effect():
    assert legal.current_version(DocType.TOS, LATER, REGISTRY) == "v2"


def test_in_force_version_follows_effective_at_not_registry_order():
    # Registry order deliberately inverted: if resolution used insertion order it would say v1.
    inverted = (TOS_V2, TOS_V1)
    assert legal.current_version(DocType.TOS, MUCH_LATER, inverted) == "v2"


def test_doc_types_resolve_independently():
    assert legal.current_version(DocType.DPA, MUCH_LATER, REGISTRY) is None
    assert legal.current_version(DocType.PRIVACY, MUCH_LATER, REGISTRY) == "v1"


# ---------------------------------------------------------------------------------------
# CARDINAL: latest_acceptance must filter by doc_type (the mutation that stayed green)
# ---------------------------------------------------------------------------------------


def test_accepting_privacy_does_not_count_as_accepting_the_tos(db: Session, org_a: None):
    legal.record_acceptance(db, "user-1", DocType.PRIVACY, "v1", NOW, REGISTRY)

    # The kill: with the doc_type filter deleted, this returns the PRIVACY row.
    assert legal.latest_acceptance(db, "user-1", DocType.TOS) is None
    assert legal.needs_reacceptance(db, "user-1", DocType.TOS, NOW, REGISTRY) is True

    privacy = legal.latest_acceptance(db, "user-1", DocType.PRIVACY)
    assert privacy is not None and privacy.doc_type == "privacy"


def test_latest_acceptance_returns_this_doc_types_version_not_another(db: Session, org_a: None):
    # Same user, same day, two doc types at DIFFERENT versions: a filterless query would return
    # whichever row happens to sort last, so the returned version pins the filter.
    legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY)
    legal.record_acceptance(db, "user-1", DocType.PRIVACY, "v1", LATER, REGISTRY)
    legal.record_acceptance(db, "user-1", DocType.TOS, "v2", MUCH_LATER, REGISTRY)

    tos = legal.latest_acceptance(db, "user-1", DocType.TOS)
    privacy = legal.latest_acceptance(db, "user-1", DocType.PRIVACY)
    assert tos is not None and tos.doc_type == "tos" and tos.version == "v2"
    assert privacy is not None and privacy.doc_type == "privacy" and privacy.version == "v1"


# ---------------------------------------------------------------------------------------
# Tenant scoping (§0.8) — org_id comes from the verified session context, and it is filtered
# ---------------------------------------------------------------------------------------


def test_acceptance_by_another_org_is_invisible(db: Session):
    token = set_current_org(ORG_B)
    try:
        legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY)
    finally:
        reset_current_org(token)

    token = set_current_org(ORG_A)
    try:
        # Same user id, different org: ORG_A must not read ORG_B's evidence, and must not be
        # let through a re-acceptance gate on the strength of it.
        assert legal.latest_acceptance(db, "user-1", DocType.TOS) is None
        assert legal.needs_reacceptance(db, "user-1", DocType.TOS, NOW, REGISTRY) is True
    finally:
        reset_current_org(token)


def test_recorded_org_is_the_bound_org_not_a_parameter(db: Session, org_a: None):
    row = legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY)
    assert row.org_id == ORG_A  # there is no org argument to pass — §0.8


@pytest.mark.parametrize(
    "call",
    [
        lambda db: legal.latest_acceptance(db, "user-1", DocType.TOS),
        lambda db: legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY),
        lambda db: legal.needs_reacceptance(db, "user-1", DocType.TOS, NOW, REGISTRY),
    ],
)
def test_every_entry_point_fails_closed_with_no_org_bound(db: Session, call):
    # No set_current_org: an unauthenticated caller must never read or write across all orgs.
    with pytest.raises(legal.OrgUnboundError):
        call(db)


# ---------------------------------------------------------------------------------------
# Acceptance log + re-acceptance on version bump
# ---------------------------------------------------------------------------------------


def test_needs_reacceptance_false_when_nothing_is_in_force(db: Session, org_a: None):
    assert legal.needs_reacceptance(db, "user-1", DocType.DPA, MUCH_LATER, REGISTRY) is False


def test_needs_reacceptance_true_before_first_acceptance(db: Session, org_a: None):
    assert legal.needs_reacceptance(db, "user-1", DocType.TOS, NOW, REGISTRY) is True


def test_record_acceptance_then_no_longer_needs_reacceptance(db: Session, org_a: None):
    legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY)
    assert legal.needs_reacceptance(db, "user-1", DocType.TOS, NOW, REGISTRY) is False


def test_version_bump_forces_reacceptance(db: Session, org_a: None):
    legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY)
    assert legal.needs_reacceptance(db, "user-1", DocType.TOS, NOW, REGISTRY) is False

    # v2 takes effect at LATER — same registry, only the clock moved.
    assert legal.needs_reacceptance(db, "user-1", DocType.TOS, LATER, REGISTRY) is True

    legal.record_acceptance(db, "user-1", DocType.TOS, "v2", LATER, REGISTRY)
    assert legal.needs_reacceptance(db, "user-1", DocType.TOS, LATER, REGISTRY) is False


def test_acceptance_is_per_user(db: Session, org_a: None):
    legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY)
    assert legal.needs_reacceptance(db, "user-1", DocType.TOS, NOW, REGISTRY) is False
    assert legal.needs_reacceptance(db, "user-2", DocType.TOS, NOW, REGISTRY) is True


def test_log_is_append_only(db: Session, org_a: None):
    legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY)
    legal.record_acceptance(db, "user-1", DocType.TOS, "v2", LATER, REGISTRY)

    latest = legal.latest_acceptance(db, "user-1", DocType.TOS)
    assert latest is not None and latest.version == "v2"
    assert latest.accepted_at == LATER.isoformat()
    # the v1 acceptance is still on record, not overwritten
    assert db.query(legal_models.LegalAcceptance).count() == 2


def test_cannot_accept_a_version_that_was_never_published(db: Session, org_a: None):
    with pytest.raises(ValueError):
        legal.record_acceptance(db, "user-1", DocType.TOS, "v99", NOW, REGISTRY)
    with pytest.raises(ValueError):
        # v1 exists — but for privacy, not for dpa.
        legal.record_acceptance(db, "user-1", DocType.DPA, "v1", NOW, REGISTRY)


# ---------------------------------------------------------------------------------------
# §0.8 — the table ships its RLS policy in the same migration, and the migration matches the
# SQL the coverage gate reads
# ---------------------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_migration_sql_is_a_verbatim_snapshot_of_the_reviewed_file():
    # The revision id starts with a digit, so it is loaded by path rather than imported.
    path = _repo_root() / "api/alembic/versions/0004_legal_acceptance.py"
    spec = importlib.util.spec_from_file_location("rev_0004", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    on_disk = _repo_root().joinpath("infra/db/multitenant/004_legal.sql").read_text("utf-8")
    assert module._004_SQL.strip() == on_disk.strip()
    assert module.down_revision == "0003_vault_retention_8y"


def test_migration_ships_rls_and_a_policy_for_the_new_table():
    sql = _repo_root().joinpath("infra/db/multitenant/004_legal.sql").read_text("utf-8")
    assert "CREATE TABLE legal_acceptance" in sql
    assert "ALTER TABLE legal_acceptance ENABLE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY legal_acceptance_tenant ON legal_acceptance" in sql
    assert "org_id = app_current_org()" in sql
    # append-only enforced by grant: the app role can never rewrite the evidence
    assert "GRANT SELECT, INSERT ON legal_acceptance TO maisha_app;" in sql
    assert "UPDATE" not in sql.split("GRANT")[-1]
    assert "DELETE" not in sql.split("GRANT")[-1]


# ---------------------------------------------------------------------------------------
# WS10.4 — require_terms_acceptance: the ToS+Privacy sign-in/mutation gate
# ---------------------------------------------------------------------------------------


def test_terms_gate_is_dormant_while_nothing_is_published(db: Session, org_a: None):
    # The shipped registry is empty (drafts publish nothing) — the gate must be a no-op,
    # for a verified user AND for an unattributable caller.
    legal.require_terms_acceptance(db, "user-1", NOW)
    legal.require_terms_acceptance(db, None, NOW)


def test_terms_gate_blocks_until_BOTH_documents_are_accepted(db: Session, org_a: None):
    # Both ToS and Privacy are in force at NOW: accepting only one must still block —
    # a gate that checked only the ToS would pass here and prove nothing about privacy.
    with pytest.raises(legal.ReacceptanceRequiredError):
        legal.require_terms_acceptance(db, "user-1", NOW, REGISTRY)

    legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY)
    with pytest.raises(legal.ReacceptanceRequiredError, match="privacy"):
        legal.require_terms_acceptance(db, "user-1", NOW, REGISTRY)

    legal.record_acceptance(db, "user-1", DocType.PRIVACY, "v1", NOW, REGISTRY)
    legal.require_terms_acceptance(db, "user-1", NOW, REGISTRY)  # both accepted -> passes


def test_terms_gate_fails_closed_for_an_unattributable_caller(db: Session, org_a: None):
    # Something is published + no verified user: an unattributable caller cannot have
    # accepted anything (same stance as require_current_acceptance).
    with pytest.raises(legal.ReacceptanceRequiredError):
        legal.require_terms_acceptance(db, None, NOW, REGISTRY)


def test_terms_gate_reopens_on_a_version_bump(db: Session, org_a: None):
    legal.record_acceptance(db, "user-1", DocType.TOS, "v1", NOW, REGISTRY)
    legal.record_acceptance(db, "user-1", DocType.PRIVACY, "v1", NOW, REGISTRY)
    legal.require_terms_acceptance(db, "user-1", NOW, REGISTRY)

    # ToS v2 takes effect at LATER — the gate must close again until v2 is accepted.
    with pytest.raises(legal.ReacceptanceRequiredError, match="tos"):
        legal.require_terms_acceptance(db, "user-1", LATER, REGISTRY)
    legal.record_acceptance(db, "user-1", DocType.TOS, "v2", LATER, REGISTRY)
    legal.require_terms_acceptance(db, "user-1", LATER, REGISTRY)
