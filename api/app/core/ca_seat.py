"""WS8.3 — CA seat onboarding (free + unlimited) + referral instrumentation.

The CA seat is the channel, not a seat to monetize (MASTER_PLAN §10, risk register §16.5):
free, unlimited, and NEVER counted against the plan's seat quantity gate — the explicit
exemption lives in ``app.core.entitlements`` (``SEAT_EXEMPT_ROLES`` / ``seat_addition_gate``)
and is consulted here so it is load-bearing, not decorative.

The flow REUSES the existing identity layer — ``app_users`` + ``memberships``
(infra/db/multitenant/001_tenancy.sql; migration 0007 adds only a ``status`` column) and the
Better Auth-verified :class:`app.core.principal.Principal` — no parallel auth system. An
invite is a ``memberships`` row with ``role='ca', status='pending'``; acceptance (by the
invitee's own verified token, matched on their verified email) flips it to ``active``.

Referral instrumentation is APPEND-ONLY events sealed onto the org's hash-chained audit log
via :func:`app.core.audit_store.append_for`, PII-minimal per the ``trace_store`` discipline:
the chain carries ``sha256(email)``, never the address.

  * ``ca_invited``      — owner/admin invited a CA by email (membership → pending)
  * ``ca_joined``       — the CA accepted (membership → active)
  * ``ca_referred_org`` — at join time this CA already held an active CA seat in ≥1 OTHER
    org: this org's arrival is attributable to an existing platform CA. That is the
    instrumentable referral signal available today (no referral-code machinery exists);
    only a COUNT crosses the org boundary, never another org's id.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit_store
from app.core.audit import canonical_json
from app.core.entitlements import GateState, seat_addition_gate
from app.core.principal import Principal
from app.core.rbac import Capability, can
from app.db.models.shared import AppUser, Membership

RULES_VERSION = "ca_seat.2026.1"

EVENT_INVITED = "ca_invited"
EVENT_JOINED = "ca_joined"
EVENT_REFERRED_ORG = "ca_referred_org"


def email_sha256(email: str) -> str:
    """PII-minimal event key (the ``trace_store`` discipline): normalized address, hashed."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _seal(
    session: Session,
    *,
    org_id: str,
    action: str,
    timestamp: str,
    user_id: str,
    email_hash: str,
    membership_id: int,
    extra: dict[str, Any] | None = None,
) -> None:
    """Seal one referral event onto ``org_id``'s independent audit chain (append-only).

    The descriptor rides inside the hashed ``query`` field (the ``thread_event_payload``
    precedent), so the hashed email, membership id and extras are all tamper-evident."""
    descriptor = canonical_json(
        {"email_sha256": email_hash, "membership": membership_id, **(extra or {})}
    )
    audit_store.append_for(
        session,
        org_id,
        {
            "timestamp": timestamp,
            "action": action,
            "domain": "platform",
            "user_id": user_id,
            "query": descriptor,
            "intent_global": None,
            "intent_domain": None,
            "validation_status": "recorded",
            "rules_version": RULES_VERSION,
        },
    )


def invite_ca(
    session: Session, *, principal: Principal, email: str, plan: str, timestamp: str
) -> Membership:
    """Owner/Admin invites a CA by email → PENDING membership + sealed ``ca_invited`` event.

    Free + unlimited (§WS8.3): the seat gate is consulted through
    :func:`entitlements.seat_addition_gate`, whose CA exemption means an org already over its
    seat limit can STILL add a CA (tested; removing the exemption breaks that test).
    A refused invite seals NOTHING.
    """
    if not can(principal.role, Capability.MANAGE_USERS):
        raise PermissionError("missing capability: manage_users")
    norm = email.strip().lower()
    if "@" not in norm.strip("@") or " " in norm:
        raise ValueError("not an email address")

    existing_roles = list(
        session.scalars(select(Membership.role).where(Membership.org_id == principal.org_id))
    )
    gate = seat_addition_gate(existing_roles, "ca", plan)
    if gate.state is GateState.BLOCK:
        # Unreachable while "ca" is in SEAT_EXEMPT_ROLES — kept so the exemption is
        # load-bearing: dropping it would make over-limit orgs unable to add their CA.
        raise ValueError(gate.reason)

    user = session.scalars(select(AppUser).where(AppUser.email == norm)).first()
    if user is None:
        user = AppUser(id=str(uuid.uuid4()), email=norm)
        session.add(user)
        session.flush()
    dupe = session.scalars(
        select(Membership).where(
            Membership.org_id == principal.org_id, Membership.user_id == user.id
        )
    ).first()
    if dupe is not None:
        raise ValueError("already a member of (or already invited to) this org")

    membership = Membership(org_id=principal.org_id, user_id=user.id, role="ca", status="pending")
    session.add(membership)
    session.flush()
    _seal(
        session,
        org_id=principal.org_id,
        action=EVENT_INVITED,
        timestamp=timestamp,
        user_id=principal.user_id,
        email_hash=email_sha256(norm),
        membership_id=membership.id,
        extra={"invited_by": principal.user_id, "seat": "free_unlimited"},
    )
    return membership


def list_pending(session: Session, *, org_id: str) -> list[dict[str, Any]]:
    """Pending CA invites for this org (owner-facing settings surface, P1-3). No capability
    check here — the router gates the route itself (manage_users), same split as ``invite_ca``
    gating in-function: this helper is a plain query, reused freely once a caller is already
    past the gate."""
    rows = session.execute(
        select(Membership.id, Membership.created_at, AppUser.email)
        .join(AppUser, AppUser.id == Membership.user_id)
        .where(
            Membership.org_id == org_id,
            Membership.role == "ca",
            Membership.status == "pending",
        )
        .order_by(Membership.created_at)
    ).all()
    return [
        {"membership_id": r.id, "email": r.email, "invited_at": r.created_at.isoformat()}
        for r in rows
    ]


def accept_ca(session: Session, *, principal: Principal, timestamp: str) -> tuple[Membership, bool]:
    """The invited CA accepts their pending seat → ACTIVE + sealed ``ca_joined`` event.

    Identity comes ONLY from the caller's verified token (§0.8): the pending membership is
    matched on ``principal.email`` within ``principal.org_id``. Returns ``(membership,
    referred)`` — ``referred`` is True when the CA already held an active CA seat in another
    org, in which case ``ca_referred_org`` is also sealed (on THIS org's chain only).
    """
    norm = principal.email.strip().lower()
    user = session.scalars(select(AppUser).where(AppUser.email == norm)).first()
    membership = (
        None
        if user is None
        else session.scalars(
            select(Membership).where(
                Membership.org_id == principal.org_id,
                Membership.user_id == user.id,
                Membership.role == "ca",
                Membership.status == "pending",
            )
        ).first()
    )
    if user is None or membership is None:
        raise LookupError("no pending CA invite for this account in this org")

    prior_ca_orgs = len(
        session.scalars(
            select(Membership.id).where(
                Membership.user_id == user.id,
                Membership.role == "ca",
                Membership.status == "active",
                Membership.org_id != principal.org_id,
            )
        ).all()
    )
    membership.status = "active"
    session.flush()

    email_hash = email_sha256(norm)
    _seal(
        session,
        org_id=principal.org_id,
        action=EVENT_JOINED,
        timestamp=timestamp,
        user_id=principal.user_id,
        email_hash=email_hash,
        membership_id=membership.id,
    )
    referred = prior_ca_orgs > 0
    if referred:
        _seal(
            session,
            org_id=principal.org_id,
            action=EVENT_REFERRED_ORG,
            timestamp=timestamp,
            user_id=principal.user_id,
            email_hash=email_hash,
            membership_id=membership.id,
            extra={"prior_ca_orgs": prior_ca_orgs},
        )
    return membership, referred
