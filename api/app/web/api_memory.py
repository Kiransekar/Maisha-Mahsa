"""SPEC-MEMCITE-1.0 MEM.P0-2 — the ``/api/memory`` surface + ``/api/playbook/{id}/feedback``.

Thin wrappers over :mod:`app.core.memory`; org identity comes only from the verified
Principal (§0.8) — no body field, no query param, no fallback.

RBAC (spec §A9 OWNER-DECISION): **Owner/Admin write, everyone with ``read`` may view.**
Memory steers the agent's narrative, so editing it is an admin surface — the write routes
wear ``manage_users``, the existing Owner/Admin-only capability, rather than a new one.
Viewing stays open to Approver/CA read-only (a CA seeing the standing instructions builds
trust; the block contains no figures by construction). Playbook feedback is a books-side
working decision, so it wears ``write`` (Owner/Admin/Accountant), the drawer-commit
precedent.

Overflow is a 422 with the service's verbatim message — reject-on-overflow, never silent
truncation (§0.4 culture).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import memory
from app.core.principal import Principal
from app.core.rbac import Capability
from app.core.rbac_deps import require, resolve_principal
from app.db.session import get_session

router = APIRouter(
    prefix="/api/memory", tags=["memory"], dependencies=[Depends(require(Capability.READ))]
)
playbook_router = APIRouter(
    prefix="/api/playbook", tags=["memory"], dependencies=[Depends(require(Capability.READ))]
)


class MemoryPut(BaseModel):
    content: str


class MemoryAppend(BaseModel):
    line: str


class FeedbackBody(BaseModel):
    verdict: Literal["adopted", "dismissed"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@router.get("")
async def get_memory(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Current blocks: the live-rendered org profile (derived, never stale) + the CFO
    posture block with its char budget."""
    return {
        "profile": memory.profile_text(db, principal),
        "cfo": memory.get_cfo(db, principal),
    }


@router.put("", dependencies=[Depends(require(Capability.MANAGE_USERS))])
async def put_memory(
    body: MemoryPut,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Replace the CFO posture block; >2200 chars after consolidation → 422 reject."""
    try:
        out = memory.set_cfo(db, principal, body.content, now=_now())
    except memory.MemoryOverflow as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return out


@router.post("/append", dependencies=[Depends(require(Capability.MANAGE_USERS))])
async def append_memory(
    body: MemoryAppend,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Append one durable line, then deterministic LLM-free consolidation; overflow after
    consolidation → 422, stored block untouched."""
    try:
        out = memory.append_cfo(db, principal, body.line, now=_now())
    except memory.MemoryOverflow as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return out


@router.get("/history")
async def memory_history(
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """The org_memory_history version trail, newest first, each row linked to its sealed
    ``memory.update`` audit event (survey §7.7 — auditable updates made visible)."""
    return {"history": memory.get_history(db, principal)}


@playbook_router.post("/{playbook_id}/feedback", dependencies=[Depends(require(Capability.WRITE))])
async def playbook_feedback(
    playbook_id: str,
    body: FeedbackBody,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Adopt/dismiss upsert for a playbook — sealed onto the org's audit chain; a dismissed
    move's claimed saving stops counting toward the quantified total."""
    try:
        out = memory.record_feedback(db, principal, playbook_id, body.verdict, now=_now())
    except memory.UnknownPlaybook as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return out
