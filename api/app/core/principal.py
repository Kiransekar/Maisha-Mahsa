"""Principal — the verified caller, as resolved from a Better Auth JWT (WS4.3-betterauth-api).

Better Auth (better-auth.com) owns credentials/2FA/sessions in the Node layer; this repo only
VERIFIES its tokens (see :mod:`app.core.betterauth`). This module holds the two things that
verification needs and nothing else: the resolved :class:`Principal` shape, and the explicit,
data-driven map from Better Auth's roles onto our own :class:`app.core.rbac.Role`.

Our roles (Owner/Admin/Accountant/Approver/CA/Investor) are RICHER than Better Auth's built-in
organization-plugin roles (owner/admin/member). The mapping below is therefore explicit data, not
a clever inference: an unmapped or unrecognised role string maps to ``None`` and the caller MUST
deny access (fail closed) rather than guess or downgrade to some default role.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

from app.core.rbac import Role

# PRODUCT DECISION, not statutory (§0.6 n/a — this is an internal role mapping, not a statutory
# value): Better Auth's organization plugin ships three default roles (owner/admin/member) plus
# support for dynamic custom roles the owner can name however they like server-side. "member" is
# the only non-privileged default, so it maps to our least-privileged *working* role (Accountant:
# read/write/export, no approvals, no user management) rather than to CA (read-only) — adjust this
# one row if product wants a stricter default. If the owner instead defines custom Better Auth
# roles named after our own role slugs (accountant/approver/ca/investor), those pass straight
# through unchanged. Anything else is UNMAPPED -> access denied.
BETTER_AUTH_ROLE_MAP: dict[str, Role] = {
    "owner": Role.OWNER,
    "admin": Role.ADMIN,
    "member": Role.ACCOUNTANT,
    "accountant": Role.ACCOUNTANT,
    "approver": Role.APPROVER,
    "ca": Role.CA,
    "investor": Role.INVESTOR,
}


def map_better_auth_role(raw_role: str | None) -> Role | None:
    """Better Auth role string -> our :class:`Role`, fail-closed.

    Missing, blank, unrecognised or typo'd input all resolve to ``None`` — never a guessed or
    default role. Matching is case-insensitive/whitespace-trimmed since it is only being compared
    against our own small fixed vocabulary, not parsed as free text.
    """
    if not raw_role:
        return None
    return BETTER_AUTH_ROLE_MAP.get(raw_role.strip().lower())


@dataclass(frozen=True)
class Principal:
    """The verified caller. Constructed ONLY from a signature-and-claims-checked JWT (§0.8) —
    never from a request body, query param, or client-controlled header. See
    :func:`app.core.betterauth.get_principal`.
    """

    user_id: str
    org_id: str
    role: Role
    email: str


# ---------------------------------------------------------------------------------------
# MFA policy — PORTED from the retired app.core.identity (WS4.3 local provider), which owned
# `mfa_required(role)`. Better Auth now owns the 2FA *mechanism* (enrolment, TOTP, recovery
# codes); this repo keeps only the POLICY question "which of OUR roles must have passed it",
# which Better Auth cannot know. Enforcement lives in
# :func:`app.core.betterauth.assert_mfa_satisfied` and is opt-in — see its docstring for why.
# ---------------------------------------------------------------------------------------

#: §WS4.3 policy (unchanged from the retired identity layer): MFA is required for Owner/Admin.
MFA_REQUIRED_ROLES: tuple[Role, ...] = (Role.OWNER, Role.ADMIN)


def mfa_required(role: Role) -> bool:
    """Must a caller in ``role`` have completed 2FA? (§WS4.3 — Owner/Admin only.)"""
    return role in MFA_REQUIRED_ROLES


# ---------------------------------------------------------------------------------------
# Postgres RLS binding — the verified org_id, and only that, reaches the database session.
# ---------------------------------------------------------------------------------------

#: The org of the request being served on this task/thread. Set ONLY by the authentication
#: middleware from a verified JWT claim (§0.8) — never from a body, query param or header.
_current_org: ContextVar[str | None] = ContextVar("maisha_current_org", default=None)

#: ``infra/db/multitenant/001_tenancy.sql`` defines ``app_current_org()`` as
#: ``current_setting('app.current_org', true)``. ``set_config(..., false)`` = session-scoped
#: (not transaction-scoped), which is what a pooled connection needs. Parameterised (§0.8).
SET_ORG_GUC_SQL = "SELECT set_config('app.current_org', %s, false)"


def set_current_org(org_id: str | None) -> Token[str | None]:
    """Bind the verified org for this request. Returns the token for :func:`reset_current_org`."""
    return _current_org.set(org_id)


def reset_current_org(token: Token[str | None]) -> None:
    _current_org.reset(token)


def current_org() -> str | None:
    return _current_org.get()


def bind_org_guc(dbapi_conn: object, dialect_name: str) -> bool:
    """Push the current org onto the DB connection so RLS (``app_current_org()``) sees it.

    Fail-closed: with no authenticated org the GUC is set to the EMPTY STRING, which
    ``app_current_org()`` turns into NULL, which every policy in ``002_domain_rls.sql`` matches
    zero rows against. It is never left holding the *previous* request's org — pooled
    connections are re-bound on every checkout.

    No-op (returns ``False``) on any non-Postgres dialect: SQLite, the dev/test database, has no
    GUCs and no RLS. Returns ``True`` when the GUC was actually issued.
    """
    if dialect_name != "postgresql":
        return False
    cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute(SET_ORG_GUC_SQL, (current_org() or "",))
    finally:
        cursor.close()
    return True


if __name__ == "__main__":  # ponytail: one runnable check for the role-mapping path
    assert map_better_auth_role("owner") is Role.OWNER
    assert map_better_auth_role("Admin") is Role.ADMIN
    assert map_better_auth_role(" member ") is Role.ACCOUNTANT
    assert map_better_auth_role("APPROVER") is Role.APPROVER
    assert map_better_auth_role("dictator") is None
    assert map_better_auth_role("") is None
    assert map_better_auth_role(None) is None

    p = Principal(user_id="u1", org_id="org1", role=Role.OWNER, email="a@b.com")
    assert p.role is Role.OWNER

    assert mfa_required(Role.OWNER) and mfa_required(Role.ADMIN)
    assert not mfa_required(Role.ACCOUNTANT)

    class _Cur:
        sql: object = None
        params: object = None

        def execute(self, sql, params):
            _Cur.sql, _Cur.params = sql, params

        def close(self):
            pass

    class _Conn:
        def cursor(self):
            return _Cur()

    assert bind_org_guc(_Conn(), "sqlite") is False
    tok = set_current_org("org-9")
    assert bind_org_guc(_Conn(), "postgresql") is True
    assert _Cur.params == ("org-9",)
    reset_current_org(tok)
    assert bind_org_guc(_Conn(), "postgresql") is True
    assert _Cur.params == ("",)  # fail-closed: no org -> NULL -> RLS matches nothing
    print("principal self-check ok")
