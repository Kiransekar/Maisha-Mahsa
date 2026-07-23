"""WS5.1-wiring — the FastAPI dependency layer that makes ``app.core.rbac`` actually enforce.

``app.core.rbac`` is a pure, request-free policy: ``can(role, capability, context)``. It is
reused UNCHANGED here — this module's entire job is (a) get the role from the VERIFIED caller,
and (b) turn a ``can() is False`` into a 403 that names the missing capability without leaking
what the resource contains, with the denial chained onto the audit log.

WHERE THE ROLE COMES FROM. ``Depends(app.core.betterauth.get_principal)`` — the
:class:`~app.core.principal.Principal` the ``_authenticate`` middleware in :mod:`app.main`
resolved from a JWKS-verified Better Auth JWT, and nothing else. There is no
``request.state.role`` contract any more: the previous version invented one, nothing populated
it, and wiring it as written would have 403'd every caller including the Owner. If the request
was not authenticated by that middleware (e.g. the dev-only shared-password cookie, which
carries no role and no org), ``get_principal`` raises 401 before any capability is considered —
fail-closed by construction, not by convention.

TWO DELIBERATE PROPERTIES, both regression-locked in the tests:

1. **A denial never commits the caller's session.** The previous version called ``db.commit()``
   on the request-scoped session inside the deny branch, so a *denial* flushed whatever else the
   request had already staged. The denial audit is now written on its OWN short-lived session
   from :func:`app.db.session.session_factory`; the caller's session is never touched.
2. **The 403 body names the capability, never the resource.** ``request.url.path`` goes into the
   audit payload (server-side, where it belongs) and never into the response detail.

INVESTOR LINKS. ``can(Role.INVESTOR, INVEST_VIEW, ...)`` additionally needs an
:class:`~app.core.rbac.InvestorContext`, which is minted by a time-boxed share link. No such link
exists in the product yet and nothing verified carries one, so :func:`enforce` passes ``None``
and every Investor request is denied. That is the honest fail-closed state — inventing a context
here would be a control that always passes. Wire the real one in when share links land.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core import audit_store
from app.core.approval_matrix import STATUTORY_FILING_ACTIONS, decide_approval
from app.core.betterauth import get_principal
from app.core.principal import Principal
from app.core.rbac import Capability, Role, can, role_change_event
from app.db.session import session_factory

#: Matches app.core.rbac.role_change_event's default so both event kinds share one rules epoch.
RULES_VERSION = "rbac.2026.1"


def resolve_principal(principal: Principal = Depends(get_principal)) -> Principal:
    """The verified caller (§0.8). A thin named seam over
    :func:`app.core.betterauth.get_principal` so every capability check in the app goes through
    one place. Reads nothing from the request body, query string, or any client-set header —
    identity comes from the JWT signature check the middleware already performed."""
    return principal


def _denial_payload(principal: Principal, capability: Capability, path: str) -> dict[str, object]:
    """Audit payload for a denied-access event — same ``AuditEntry``-core shape as
    :func:`app.core.rbac.role_change_event` so it chains through the existing
    ``audit_store.append``. No PII: the opaque user id, the role name, the capability, and the
    path. The path is recorded HERE (server-side) and never returned to the caller."""
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": "rbac.access_denied",
        "domain": "rbac",
        "user_id": principal.user_id,
        "query": f"{principal.role.value} denied {capability.value} on {path}",
        "intent_global": None,
        "intent_domain": None,
        "validation_status": "denied",
        "rules_version": RULES_VERSION,
    }


def _audit_denial(payload: dict[str, object]) -> None:
    """Chain the denial on a session of our own.

    Never the request-scoped session: committing that as a side effect of a DENIAL would flush
    whatever else the request had staged. Short-lived, opened and closed here.
    """
    db = session_factory()()
    try:
        audit_store.append(db, payload)
        db.commit()
    finally:
        db.close()


def enforce(principal: Principal, capability: Capability, path: str) -> None:
    """Raise 403 unless ``principal`` may exercise ``capability``. Fails CLOSED.

    Used both by :func:`require` (whole-route gating) and directly by routes whose required
    capability depends on what the request is asking for — ``POST /api/inbox/bulk`` needs only
    ``read`` to preview but ``approve_payment`` to commit, and a preview and a commit are the
    same route. Same denial semantics either way: one audit event, one 403, no resource content.
    """
    if can(principal.role, capability, None):
        return
    _audit_denial(_denial_payload(principal, capability, path))
    raise HTTPException(status_code=403, detail=f"missing capability: {capability.value}")


def require(capability: Capability) -> Callable[..., Principal]:
    """Dependency factory: ``Depends(require(Capability.APPROVE_PAYMENT))``.

    Returns the verified :class:`Principal` when allowed, so a route that gates on a capability
    also gets the caller for free and never has to re-resolve identity.
    """

    def _dependency(
        request: Request, principal: Principal = Depends(resolve_principal)
    ) -> Principal:
        enforce(principal, capability, request.url.path)
        return principal

    # Machine-readable declaration: the route-coverage guard in tests/integration/
    # test_rbac_matrix.py walks every /api route's dependencies looking for this attribute,
    # so a new route with no capability declared fails CI rather than shipping unguarded.
    _dependency.required_capability = capability  # type: ignore[attr-defined]
    return _dependency


def require_filing(action: str) -> Callable[..., Principal]:
    """Dependency factory for statutory-filing routes: the WS5.2 HARD gate, wired not duplicated.

    ``action`` must be a member of ``approval_matrix.STATUTORY_FILING_ACTIONS`` — checked at
    definition time (router import), so a typo'd action can never silently take the softer
    amount-matrix path. The decision itself is :func:`app.core.approval_matrix.decide_approval`,
    whose statutory branch admits Owner/Admin ONLY and ignores any configured matrix. Plan and
    amount are irrelevant on that branch (it consults neither), so fixed valid placeholders are
    passed rather than resolving a plan this gate would not use.
    """
    if action not in STATUTORY_FILING_ACTIONS:
        raise ValueError(
            f"{action!r} is not a statutory filing action; expected one of "
            f"{sorted(STATUTORY_FILING_ACTIONS)}"
        )

    def _dependency(
        request: Request, principal: Principal = Depends(resolve_principal)
    ) -> Principal:
        verdict = decide_approval("basics", principal.role, action, 0)
        if verdict["required_role_ok"]:
            return principal
        _audit_denial(_denial_payload(principal, Capability.APPROVE_FILING, request.url.path))
        raise HTTPException(status_code=403, detail=str(verdict["reason"]))

    _dependency.required_capability = Capability.APPROVE_FILING  # type: ignore[attr-defined]
    _dependency.filing_action = action  # type: ignore[attr-defined]
    return _dependency


def emit_role_change(
    db: Session,
    *,
    actor_user_id: str,
    target_user_id: str,
    old_role: Role,
    new_role: Role,
) -> None:
    """Chain a role-change event onto the audit log via
    :func:`app.core.rbac.role_change_event` (WS5.1). Call this from the ``manage_users`` route
    that actually changes a membership's role; this module does not perform the change itself.
    Takes the caller's session explicitly — a role change IS the caller's work, so committing it
    here is correct (unlike a denial)."""
    payload = role_change_event(
        timestamp=datetime.now(UTC).isoformat(),
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        old_role=old_role,
        new_role=new_role,
        rules_version=RULES_VERSION,
    )
    audit_store.append(db, payload)
    db.commit()


if __name__ == "__main__":  # ponytail: one runnable check for the enforcement path

    def _principal(role: Role) -> Principal:
        return Principal(user_id="u1", org_id="org1", role=role, email="a@b.com")

    audited: list[dict[str, object]] = []
    # NB: `python -m app.core.rbac_deps` runs this file as __main__, so `import
    # app.core.rbac_deps` here would be a SECOND module object and patching it would do nothing.
    globals()["_audit_denial"] = audited.append

    enforce(_principal(Role.OWNER), Capability.APPROVE_PAYMENT, "/api/approvals")
    assert audited == []

    for role, cap in (
        (Role.ACCOUNTANT, Capability.APPROVE_PAYMENT),
        (Role.CA, Capability.WRITE),
        (Role.APPROVER, Capability.MANAGE_USERS),
        (Role.INVESTOR, Capability.READ),
        (Role.INVESTOR, Capability.INVEST_VIEW),  # no share-link context -> denied
    ):
        try:
            enforce(_principal(role), cap, "/api/secret-thing")
        except HTTPException as exc:
            assert exc.status_code == 403 and cap.value in exc.detail
            assert "secret-thing" not in exc.detail  # resource never named to the caller
        else:
            raise AssertionError(f"{role} must be denied {cap}")

    assert len(audited) == 5
    assert all("secret-thing" in str(p["query"]) for p in audited)  # but it IS audited
    print("rbac_deps self-check ok")
