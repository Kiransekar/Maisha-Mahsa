"""WS5.1-wiring — the enforcement layer, not the pure ``can()`` predicate underneath.

The HTTP permission matrix lives in ``tests/integration/test_rbac_matrix.py`` and proves the two
capabilities that are actually gated on routes today, over real HTTP with real signed tokens.
This file covers what HTTP cannot reach cheaply:

  · the FULL role x capability grid (6 x 8 = 48), with the expected column written out BY HAND
    rather than derived from ``ROLE_CAPABILITIES`` — a table derived from the implementation
    would agree with any implementation, which is the definition of a vacuous test;
  · that :func:`resolve_principal` really hangs off ``betterauth.get_principal`` and nothing
    else — the previous version read an invented ``request.state.role`` that nothing populated;
  · that the denial path never receives, let alone commits, the caller's request-scoped session;
  · that the 403 the caller sees names the capability and never the resource, while the audit
    entry (server-side) does record the path.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from fastapi.params import Depends as DependsParam
from sqlalchemy.orm import Session, sessionmaker

from app.core import audit_store, rbac_deps
from app.core.betterauth import get_principal
from app.core.principal import Principal
from app.core.rbac import Capability, Role
from app.core.rbac_deps import (
    emit_role_change,
    enforce,
    require,
    require_filing,
    resolve_principal,
)


@pytest.fixture(autouse=True)
def denial_audit_db(session: Session, monkeypatch):
    """Point the denial audit at the test DB. ``_audit_denial`` deliberately opens its OWN
    session (never the caller's), so it must be redirected explicitly — which is itself evidence
    that the caller's session is not involved."""
    factory = sessionmaker(bind=session.get_bind(), future=True, expire_on_commit=False)
    monkeypatch.setattr(rbac_deps, "session_factory", lambda: factory)
    return session


def _principal(role: Role, user_id: str = "u1") -> Principal:
    return Principal(user_id=user_id, org_id="org-7", role=role, email="a@b.com")


def _denied_count(db: Session) -> int:
    return sum(1 for e in audit_store.load_chain(db) if e.action == "rbac.access_denied")


# --- identity comes from the verified token, not from an invented request contract ------------


def test_resolve_principal_is_bound_to_betterauth_get_principal():
    """The whole reason the previous version was hollow: it resolved the role from
    ``request.state.role``, which nothing in the app set. Assert the dependency chain by
    inspection, so swapping the source out fails here."""
    default = inspect.signature(resolve_principal).parameters["principal"].default
    assert isinstance(default, DependsParam)
    assert default.dependency is get_principal


def test_resolve_principal_takes_no_request_and_reads_no_client_input():
    params = inspect.signature(resolve_principal).parameters
    assert list(params) == ["principal"]
    assert params["principal"].annotation in (Principal, "Principal")


def test_resolve_principal_returns_the_verified_principal_unchanged():
    p = _principal(Role.ACCOUNTANT)
    assert resolve_principal(p) is p


# --- the full role x capability grid, expected column written out by hand ---------------------

#: Independently transcribed from the WS5.1 role definitions in ``app.core.rbac``'s docstring —
#: NOT computed from ``ROLE_CAPABILITIES``. If the policy data changes, this fails until a human
#: re-reads it. Investor is empty on purpose: ``invest_view`` additionally needs a share-link
#: ``InvestorContext``, which no verified request carries yet, so it is denied (fail closed).
EXPECTED: dict[Role, set[str]] = {
    Role.OWNER: {
        "read",
        "write",
        "approve_payment",
        "approve_filing",
        "manage_users",
        "view_audit",
        "export",
        "invest_view",
    },
    Role.ADMIN: {
        "read",
        "write",
        "approve_payment",
        "approve_filing",
        "manage_users",
        "view_audit",
        "export",
    },
    Role.ACCOUNTANT: {"read", "write", "view_audit", "export"},
    Role.APPROVER: {"read", "approve_payment", "approve_filing", "view_audit"},
    Role.CA: {"read", "view_audit", "export"},
    Role.INVESTOR: set(),
}


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("capability", list(Capability))
def test_enforce_grid(role: Role, capability: Capability, denial_audit_db: Session):
    allowed = capability.value in EXPECTED[role]
    if allowed:
        enforce(_principal(role), capability, "/api/x")  # must not raise
        assert _denied_count(denial_audit_db) == 0
    else:
        with pytest.raises(HTTPException) as exc_info:
            enforce(_principal(role), capability, "/api/x")
        assert exc_info.value.status_code == 403
        assert _denied_count(denial_audit_db) == 1


def test_owner_holds_every_capability_except_none():
    """Guards the grid above against a silent shrink: Owner must cover the whole Capability
    enum, so adding a capability without deciding Owner's row fails."""
    assert EXPECTED[Role.OWNER] == {c.value for c in Capability}


def test_investor_is_denied_invest_view_without_a_share_link_context():
    """Honest fail-closed state, asserted so nobody reads the empty Investor row as an accident:
    ``enforce`` passes ``context=None`` because no verified request carries an InvestorContext
    yet. When share links land, this test is the one that must change."""
    with pytest.raises(HTTPException) as exc_info:
        enforce(_principal(Role.INVESTOR), Capability.INVEST_VIEW, "/api/reports/cap_table")
    assert exc_info.value.status_code == 403


# --- the 403 names the capability, never the resource ----------------------------------------


def test_denial_detail_names_the_capability_and_not_the_resource():
    with pytest.raises(HTTPException) as exc_info:
        enforce(_principal(Role.APPROVER), Capability.MANAGE_USERS, "/api/org/secret-thing")
    detail = exc_info.value.detail
    assert detail == "missing capability: manage_users"
    assert "secret-thing" not in detail
    assert "/api/" not in detail


def test_denial_is_audited_with_the_path_server_side(denial_audit_db: Session):
    """The path the caller must NOT see is exactly what the audit log must record."""
    with pytest.raises(HTTPException):
        enforce(_principal(Role.APPROVER, "u-42"), Capability.MANAGE_USERS, "/api/org/secret")
    chain = audit_store.load_chain(denial_audit_db)
    entries = [e for e in chain if e.action == "rbac.access_denied"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.domain == "rbac"
    assert entry.user_id == "u-42"
    assert "approver" in entry.query
    assert "manage_users" in entry.query
    assert "/api/org/secret" in entry.query
    assert audit_store.verify_chain(chain)


# --- a denial never touches the caller's session ----------------------------------------------


def test_denial_path_never_receives_the_callers_session():
    """The previous version called ``db.commit()`` on the request-scoped session inside the deny
    branch — a DENIAL committing whatever else the request had staged. The fix is structural:
    neither ``enforce`` nor the ``require`` dependency takes a Session at all, so there is no
    session for a future edit to commit. Asserted by signature so reintroducing one fails here.
    (The behavioural half — a denied call leaves the approval queue untouched — is asserted over
    real HTTP in tests/integration/test_rbac_matrix.py.)"""
    assert Session not in {p.annotation for p in inspect.signature(enforce).parameters.values()}

    dep_params = inspect.signature(require(Capability.READ)).parameters
    assert set(dep_params) == {"request", "principal"}
    for param in dep_params.values():
        assert param.annotation is not Session


def test_require_returns_the_principal_for_a_permitted_caller():
    from types import SimpleNamespace

    dep = require(Capability.APPROVE_PAYMENT)
    principal = _principal(Role.APPROVER)
    request = SimpleNamespace(url=SimpleNamespace(path="/api/approvals/treasury/decide"))
    assert dep(request, principal) is principal


# --- the statutory-filing hard gate (fix:rbac-api) --------------------------------------------


def test_require_filing_rejects_a_non_filing_action_at_definition_time():
    """A typo'd or invented action must never silently take the softer amount-matrix path."""
    with pytest.raises(ValueError, match="not a statutory filing action"):
        require_filing("create_invoice")


#: PAIRED both directions, by hand. The load-bearing row is APPROVER: it HOLDS the
#: approve_filing capability (see EXPECTED above) and is still refused — the WS5.2 hard gate
#: (Owner/Admin only, via approval_matrix.decide_approval) is stricter than rbac.can().
@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        (Role.OWNER, True),
        (Role.ADMIN, True),
        (Role.APPROVER, False),
        (Role.ACCOUNTANT, False),
        (Role.CA, False),
        (Role.INVESTOR, False),
    ],
)
def test_require_filing_is_a_hard_owner_admin_gate(
    role: Role, allowed: bool, denial_audit_db: Session
):
    from types import SimpleNamespace

    dep = require_filing("gstr3b")
    request = SimpleNamespace(url=SimpleNamespace(path="/api/gst/gstr3b"))
    principal = _principal(role)
    if allowed:
        assert dep(request, principal) is principal
        assert _denied_count(denial_audit_db) == 0
    else:
        with pytest.raises(HTTPException) as exc_info:
            dep(request, principal)
        assert exc_info.value.status_code == 403
        assert "Owner or Admin" in str(exc_info.value.detail)
        assert "/api/" not in str(exc_info.value.detail)  # capability-level, never the resource
        assert _denied_count(denial_audit_db) == 1  # the denial is audited server-side


def test_require_filing_declares_its_marker_for_the_coverage_guard():
    dep = require_filing("mark_filed")
    assert dep.required_capability is Capability.APPROVE_FILING
    assert dep.filing_action == "mark_filed"
    assert require(Capability.WRITE).required_capability is Capability.WRITE


# --- role_change_event wiring ------------------------------------------------------------------


def test_emit_role_change_chains_via_rbac_role_change_event(session: Session):
    emit_role_change(
        session,
        actor_user_id="u_owner",
        target_user_id="u_42",
        old_role=Role.ACCOUNTANT,
        new_role=Role.APPROVER,
    )
    chain = audit_store.load_chain(session)
    assert chain[-1].action == "rbac.role_change"
    assert chain[-1].domain == "rbac"
    assert chain[-1].query == "u_42: accountant -> approver"
    assert audit_store.verify_chain(chain)
