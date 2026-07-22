"""WS8.3 — CA seat onboarding: free+unlimited seat, invite→accept flow, referral events.

Referral instrumentation is proven against the REAL per-tenant audit chain (append-only,
``verify_chain_for``), and PII-minimality is asserted directly: the sealed descriptor carries
sha256(email), never the address.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ca_seat
from app.core.audit_store import load_chain_for, verify_chain_for
from app.core.entitlements import QUANTITY_LIMITS
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.shared import AppUser, Membership

TS = "2026-07-22T09:00:00+00:00"
CA_EMAIL = "ca@firm.in"


def _principal(
    role: Role = Role.OWNER, org: str = "org-a", user: str = "u-owner", email: str = "own@x.in"
) -> Principal:
    return Principal(user_id=user, org_id=org, role=role, email=email)


def _ca_principal(org: str = "org-a") -> Principal:
    return Principal(user_id="ba-ca-1", org_id=org, role=Role.CA, email=CA_EMAIL)


def test_invite_creates_pending_membership_and_seals_ca_invited(session: Session) -> None:
    m = ca_seat.invite_ca(
        session, principal=_principal(), email=" Ca@Firm.In ", plan="basics", timestamp=TS
    )
    assert (m.role, m.status, m.org_id) == ("ca", "pending", "org-a")

    chain = load_chain_for(session, "org-a")
    assert [e.action for e in chain] == [ca_seat.EVENT_INVITED]
    assert verify_chain_for(session, "org-a")
    # PII-minimal: the chain carries the hash, never the address (trace_store discipline)
    assert CA_EMAIL not in (chain[0].query or "")
    assert ca_seat.email_sha256(CA_EMAIL) in (chain[0].query or "")
    # normalization: the identity row stores the canonical address
    user = session.scalars(select(AppUser)).one()
    assert user.email == CA_EMAIL


def test_invite_refused_without_manage_users_and_seals_nothing(session: Session) -> None:
    for role in (Role.ACCOUNTANT, Role.APPROVER, Role.CA, Role.INVESTOR):
        with pytest.raises(PermissionError, match="manage_users"):
            ca_seat.invite_ca(
                session, principal=_principal(role=role), email=CA_EMAIL,
                plan="basics", timestamp=TS,
            )
    assert load_chain_for(session, "org-a") == []
    assert session.scalars(select(Membership)).first() is None


def test_duplicate_invite_refused_and_not_double_sealed(session: Session) -> None:
    ca_seat.invite_ca(session, principal=_principal(), email=CA_EMAIL, plan="basics", timestamp=TS)
    with pytest.raises(ValueError, match="already"):
        ca_seat.invite_ca(
            session, principal=_principal(), email=CA_EMAIL.upper(), plan="basics", timestamp=TS
        )
    assert len(load_chain_for(session, "org-a")) == 1


def test_bad_email_refused(session: Session) -> None:
    for bad in ("", "not-an-email", "@", "a@", "@b", "two words@x.in"):
        with pytest.raises(ValueError, match="email"):
            ca_seat.invite_ca(
                session, principal=_principal(), email=bad, plan="basics", timestamp=TS
            )


def test_ca_invite_succeeds_with_org_over_its_seat_limit(session: Session) -> None:
    """THE §WS8.3 exemption, load-bearing: an org already BLOCK-deep in countable seats can
    still add a CA. Removing 'ca' from SEAT_EXEMPT_ROLES makes this fail (mutation-proof)."""
    limit = QUANTITY_LIMITS["seats"]["basics"]
    for i in range(limit + 3):  # past limit + grace band → BLOCK for a countable addition
        session.add(Membership(org_id="org-a", user_id=f"u{i}", role="accountant"))
    session.flush()

    m = ca_seat.invite_ca(
        session, principal=_principal(), email=CA_EMAIL, plan="basics", timestamp=TS
    )
    assert m.status == "pending"


def test_accept_activates_and_seals_ca_joined(session: Session) -> None:
    ca_seat.invite_ca(session, principal=_principal(), email=CA_EMAIL, plan="basics", timestamp=TS)
    m, referred = ca_seat.accept_ca(session, principal=_ca_principal(), timestamp=TS)
    assert m.status == "active"
    assert referred is False

    chain = load_chain_for(session, "org-a")
    assert [e.action for e in chain] == [ca_seat.EVENT_INVITED, ca_seat.EVENT_JOINED]
    assert verify_chain_for(session, "org-a")
    assert all(CA_EMAIL not in (e.query or "") for e in chain)


def test_accept_without_invite_raises_and_seals_nothing(session: Session) -> None:
    with pytest.raises(LookupError, match="no pending CA invite"):
        ca_seat.accept_ca(session, principal=_ca_principal(), timestamp=TS)
    assert load_chain_for(session, "org-a") == []


def test_accept_is_org_scoped(session: Session) -> None:
    """A pending invite in org-a cannot be accepted through an org-b-bound token (§0.8)."""
    ca_seat.invite_ca(session, principal=_principal(), email=CA_EMAIL, plan="basics", timestamp=TS)
    with pytest.raises(LookupError):
        ca_seat.accept_ca(session, principal=_ca_principal(org="org-b"), timestamp=TS)
    assert load_chain_for(session, "org-b") == []


def test_second_org_join_seals_ca_referred_org(session: Session) -> None:
    """The referral signal: joining org-b while already an active CA of org-a."""
    ca_seat.invite_ca(session, principal=_principal(), email=CA_EMAIL, plan="basics", timestamp=TS)
    ca_seat.accept_ca(session, principal=_ca_principal(), timestamp=TS)

    org_b_owner = _principal(org="org-b", user="u-owner-b", email="own@b.in")
    ca_seat.invite_ca(session, principal=org_b_owner, email=CA_EMAIL, plan="basics", timestamp=TS)
    m, referred = ca_seat.accept_ca(session, principal=_ca_principal(org="org-b"), timestamp=TS)
    assert referred is True
    assert m.org_id == "org-b"

    chain_b = load_chain_for(session, "org-b")
    assert [e.action for e in chain_b] == [
        ca_seat.EVENT_INVITED, ca_seat.EVENT_JOINED, ca_seat.EVENT_REFERRED_ORG,
    ]
    assert verify_chain_for(session, "org-b")
    assert '"prior_ca_orgs":1' in (chain_b[-1].query or "")  # canonical_json, no whitespace
    # no cross-tenant leak: org-b's chain never names org-a
    assert all("org-a" not in (e.query or "") for e in chain_b)
    # org-a's chain is untouched by the org-b join
    assert [e.action for e in load_chain_for(session, "org-a")] == [
        ca_seat.EVENT_INVITED, ca_seat.EVENT_JOINED,
    ]
