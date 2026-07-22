"""F4 — the approvals queue and the decision flow. Pending items come from Mahsa: any domain
whose fold sets ``requires_approval`` (a yellow/red verdict). A human decision is sealed into
the hash-chained audit log and recorded as a :class:`Decision`, which resolves the item until
the underlying books (and thus the snapshot hash) change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.core import audit_store, decision_store, trace_store
from app.core.domain import BaseDomainService
from app.core.mahsa_client import MahsaClient
from app.core.router import DomainRouter

_COLOUR = {"green": "green", "yellow": "amber", "red": "red"}


@dataclass
class ApprovalItem:
    domain: str
    status: str
    color: str
    score: float | None
    citations: list[dict[str, str]] = field(default_factory=list)
    state_hash: str = ""
    resolution: str | None = None  # "approved" | "rejected" | None (pending)


def _build_snapshot(service: BaseDomainService, session: Session, as_of: date | None) -> dict:
    try:
        return service.build_snapshot(session, as_of)  # type: ignore[call-arg]
    except TypeError:
        return service.build_snapshot(session)


async def pending_approvals(
    session: Session,
    mahsa: MahsaClient,
    registry: DomainRouter,
    *,
    as_of: date | None = None,
) -> list[ApprovalItem]:
    """Every domain Mahsa flags for approval, annotated with its resolution status. Raises
    ``MahsaError`` if the sidecar is unreachable (the caller decides how to degrade)."""
    out: list[ApprovalItem] = []
    for domain in registry.domains():
        service = registry.get(domain)
        if service is None:
            continue
        snapshot = _build_snapshot(service, session, as_of)
        fold = await mahsa.fold(snapshot, domain=domain)
        if not fold.shape.requires_approval:
            continue
        state_hash = trace_store.input_hash(domain=domain, query=None, snapshot=snapshot)
        shape = fold.shape
        score = shape.domain_score if shape.domain_score is not None else shape.global_score
        out.append(
            ApprovalItem(
                domain=domain,
                status=fold.validation.status,
                color=_COLOUR.get(fold.validation.status, "green"),
                score=round(score, 1) if score is not None else None,
                citations=[
                    {
                        "rule_id": t.id,
                        "text": t.description,
                        "citation": f"{t.statute} / {t.section}",
                    }
                    for t in fold.validation.triggered
                ],
                state_hash=state_hash,
                resolution=decision_store.resolution(session, domain, state_hash),
            )
        )
    return out


async def record_decision(
    session: Session,
    *,
    domain: str,
    decision: str,
    mahsa: MahsaClient,
    registry: DomainRouter,
    as_of: date | None = None,
    user_id: str = "founder",
    timestamp: str | None = None,
    item_id: str | None = None,
) -> str:
    """Seal an approve/reject onto the audit chain and persist the Decision. Re-folds the
    domain so the decision is bound to the *current* books (state_hash + rules_version).

    ``item_id`` is WHICH inbox row was decided (e.g. ``"approval:gst"``) — without it, two
    previewed rows in one domain would seal two byte-identical, indistinguishable decisions
    (WS7-E2E fix:bulk-rows). It is carried inside ``query``, which sits in the hashed
    ``core_payload`` — the row identity is tamper-evident, and no new payload key is added
    (a new key would break ``verify_chain``'s recomputation for this entry). ``None`` keeps
    the exact pre-fix entry shape for whole-domain decisions from the approvals page."""
    if decision not in ("approved", "rejected"):
        raise ValueError(f"decision must be approved/rejected, got {decision!r}")
    service = registry.get(domain)
    if service is None:
        raise ValueError(f"unknown domain '{domain}'")
    snapshot = _build_snapshot(service, session, as_of)
    fold = await mahsa.fold(snapshot, domain=domain)
    state_hash = trace_store.input_hash(domain=domain, query=None, snapshot=snapshot)
    ts = timestamp or datetime.now(UTC).isoformat()

    entry = audit_store.append(
        session,
        {
            "timestamp": ts,
            "action": f"approval.{decision}",
            "domain": domain,
            "user_id": user_id,
            "query": f"{decision} {domain}" + (f" [row {item_id}]" if item_id else ""),
            "intent_global": fold.global_intent,
            "intent_domain": fold.domain_intent,
            "validation_status": fold.validation.status,
            "rules_version": fold.rules_version,
        },
    )
    decision_store.append(
        session,
        timestamp=ts,
        domain=domain,
        decision=decision,
        state_hash=state_hash,
        audit_hash=entry.this_hash,
        user_id=user_id,
        item_id=item_id,
    )
    # A domain may hold writes that only an approval releases (payroll: drafted runs flagged by
    # PAYROLL-005). The hook is optional and generic — every decision surface (HTMX, JSON, bulk)
    # routes through here, so the release cannot drift per surface. Shares this commit.
    resolve_pending = getattr(service, "resolve_pending_runs", None)
    if resolve_pending is not None:
        resolve_pending(session, decision=decision)
    session.commit()
    verb = "approved" if decision == "approved" else "rejected"
    return f"{domain.capitalize()} {verb} · sealed to audit {entry.this_hash[:8]}…"
