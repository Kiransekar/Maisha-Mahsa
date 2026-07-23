"""SPEC-MEMCITE-1.0 Part A (MEM.P0-2) — the per-company memory service.

Ports the proven api-nest mechanisms (``memory.service.ts``, ``tax-optimizer.service.ts``)
onto the main product's Principal/RLS plumbing, fixing the four §A3 defects:

* **Org identity comes ONLY from the verified Principal** — every function takes the
  :class:`~app.core.principal.Principal` and scopes to ``principal.org_id``. There is no org
  parameter and no first-row fallback (api-nest ``resolveCompanyId()`` is the defect, not the
  precedent). RLS is the floor; every query still filters ``org_id`` explicitly
  (defense-in-depth both directions).
* **Explicit-write only** (§A5): no LLM auto-extraction — MINJA (arXiv:2503.03704) shows any
  user can poison auto-extracted memory through normal queries alone.
* **Memory is CONTEXT, never a figure source** (§0.4/§A4): nothing here ever touches
  ``tools.enrich()``'s facts map, and the rendered block carries the context-only label
  verbatim. A rupee figure smuggled into memory cannot survive ``retry.generate_verified``.
* **Every write is audit-sealed** onto the org's own hash-chained audit log
  (``audit_store.append_for``), with the superseded version archived first — soft/temporal
  updates (survey §5.2.2), never destructive replacement. Only content HASHES enter the
  sealed ``query`` field (trace-store precedent), never the content itself.

Playbook feedback (§A1 type 4): adopt/dismiss verdicts demote dismissed moves and zero their
claimed savings out of the quantified total — the behaviour verified live in api-nest
(GST-LATEFEE dismissal: ₹800 → ₹0, commit ``c0b075f``). Rupee figures come from the existing
deterministic statutory engine (``gst_calc.late_fee_3b``), never re-derived here (§0.6).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit_store
from app.core.principal import Principal
from app.db.models.memory import OrgMemory, OrgMemoryHistory, PlaybookFeedback
from app.db.models.shared import AuditLog, Org
from app.domains.gst.gst_calc import late_fee_3b

#: Hard cap, chars not tokens (api-nest ``CFO_CHAR_LIMIT``). OWNER-DECISION (spec §A9): keep
#: 2200 unchanged — the cap IS the forgetting-pressure mechanism. Mirrors the DB CHECK.
CFO_CHAR_LIMIT = 2200
KIND_CFO = "cfo_posture"
RULES_VERSION = "memory/v1"

#: Ported verbatim from api-nest ``memory.service.ts`` (spec §A4: "Block label ports
#: verbatim"). The label is the §0.4 contract made visible in the prompt.
CONTEXT_ONLY_LABEL = "CFO POSTURE (durable preferences — context only, NEVER a source of numbers)"

_BULLET_PREFIXES = ("- ", "* ", "• ", "-", "*", "•")


class MemoryOverflow(Exception):
    """The consolidated block exceeds the cap. Reject-on-overflow — NEVER silent truncation
    (§0.4 culture): the human prunes, the machine refuses."""

    def __init__(self, used: int) -> None:
        self.used = used
        self.limit = CFO_CHAR_LIMIT
        super().__init__(
            f"CFO memory is {used} chars after consolidation; the limit is {CFO_CHAR_LIMIT}. "
            "Remove or shorten a line to make room (durable facts only)."
        )


class UnknownPlaybook(Exception):
    """Feedback for a playbook id that does not exist — refused, never recorded."""


def consolidate(content: str) -> str:
    """Deterministic, LLM-free dedupe (port of api-nest ``consolidate``): trim each line,
    drop empties, dedupe case-insensitively ignoring a leading bullet; first occurrence wins."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in content.split("\n"):
        line = raw.strip()
        if not line:
            continue
        key = line.lower()
        for prefix in _BULLET_PREFIXES:
            if key.startswith(prefix):
                key = key[len(prefix) :].strip()
                break
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------------------
# CFO posture block — get / set / append / history
# ---------------------------------------------------------------------------------------


def _row(db: Session, org_id: str) -> OrgMemory | None:
    return db.scalars(
        select(OrgMemory).where(OrgMemory.org_id == org_id, OrgMemory.kind == KIND_CFO)
    ).first()


def _shape(content: str) -> dict[str, Any]:
    return {"content": content, "used": len(content), "limit": CFO_CHAR_LIMIT}


def get_cfo(db: Session, principal: Principal) -> dict[str, Any]:
    """The learned CFO block for the caller's org, with its char budget."""
    row = _row(db, principal.org_id)
    return _shape(row.content if row else "")


def _seal(
    db: Session, org_id: str, user_id: str, action: str, query: str, now: str
) -> tuple[str, int | None]:
    """Seal an event onto the ORG'S OWN hash chain (WS4.4 per-tenant genesis) and return
    ``(this_hash, audit_log_row_id)`` so history rows can link to the sealed event. Takes the
    org/user directly so the cron path (:func:`evolve`, which has no human Principal) seals
    exactly like the API path does."""
    entry = audit_store.append_for(
        db,
        org_id,
        {
            "timestamp": now,
            "action": action,
            "domain": "memory",
            "user_id": user_id,
            "query": query,
            "intent_global": None,
            "intent_domain": None,
            "validation_status": "recorded",
            "rules_version": RULES_VERSION,
        },
    )
    seq = db.scalars(select(AuditLog.id).where(AuditLog.this_hash == entry.this_hash)).first()
    return entry.this_hash, seq


def set_cfo(db: Session, principal: Principal, content: str, *, now: str) -> dict[str, Any]:
    """Replace the posture block. Consolidates first; REJECTS (never truncates) when still
    over budget. Soft/temporal update: the prior version is archived to
    ``org_memory_history``, and the change is sealed as a ``memory.update`` event on the
    org's audit chain — the history row carries the sealed event's row id (``audit_seq``).

    ``now`` is injected (determinism doctrine) — this module never reads the clock.
    """
    next_content = consolidate(content)
    if len(next_content) > CFO_CHAR_LIMIT:
        raise MemoryOverflow(len(next_content))

    row = _row(db, principal.org_id)
    prior = row.content if row else ""
    if row is not None and prior == next_content:
        return _shape(next_content)  # no change: nothing archived, nothing sealed

    digest = hashlib.sha256(next_content.encode()).hexdigest()
    this_hash, seq = _seal(
        db,
        principal.org_id,
        principal.user_id,
        "memory.update",
        f"kind={KIND_CFO} sha256={digest} chars={len(next_content)}",
        now,
    )
    if row is not None and prior:
        db.add(
            OrgMemoryHistory(
                org_id=principal.org_id,
                kind=KIND_CFO,
                content=prior,
                superseded_at=now,
                superseded_by=principal.user_id,
                audit_seq=seq,
            )
        )
    if row is None:
        db.add(
            OrgMemory(
                org_id=principal.org_id,
                kind=KIND_CFO,
                content=next_content,
                updated_at=now,
                updated_by=principal.user_id,
            )
        )
    else:
        row.content = next_content
        row.updated_at = now
        row.updated_by = principal.user_id
    db.flush()
    return {**_shape(next_content), "audit_hash": this_hash}


def append_cfo(db: Session, principal: Principal, line: str, *, now: str) -> dict[str, Any]:
    """Append one durable line, then consolidate; overflow after consolidation is rejected,
    leaving the stored block untouched (port of api-nest ``appendCfo``)."""
    current = get_cfo(db, principal)["content"]
    clean = " ".join(line.split())
    next_content = f"{current}\n- {clean}" if current else f"- {clean}"
    return set_cfo(db, principal, next_content, now=now)


def get_history(db: Session, principal: Principal, limit: int = 50) -> list[dict[str, Any]]:
    """Superseded versions, newest first — the non-destructive trail (§7.7 auditable updates)."""
    rows = db.scalars(
        select(OrgMemoryHistory)
        .where(OrgMemoryHistory.org_id == principal.org_id, OrgMemoryHistory.kind == KIND_CFO)
        .order_by(OrgMemoryHistory.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "content": r.content,
            "superseded_at": r.superseded_at,
            "superseded_by": r.superseded_by,
            "audit_seq": r.audit_seq,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------------------
# Offline evolution (MEM.P1-1, survey §5.2/§7.8) — nightly re-consolidation + bounded archive
# ---------------------------------------------------------------------------------------

#: Author recorded on evolve-driven writes — the cron path has no human Principal, and a
#: sealed event must never fabricate one.
EVOLVE_USER = "system:evolve"
#: Bounded retention window for ``org_memory_history`` (api-nest ``evolve`` default, ported).
KEEP_VERSIONS = 20


def evolve(
    db: Session, org_id: str, *, now: str, keep_versions: int = KEEP_VERSIONS
) -> dict[str, Any]:
    """Port of api-nest ``evolve()``: re-consolidate the hot layer and cap the archive.

    Deterministic, LLM-free and idempotent — writes already consolidate on the way in
    (:func:`set_cfo`), so the re-consolidation is normally a no-op; it exists to heal any
    block that drifted past the write path (a direct DB edit, an import). When it DOES
    change the block it behaves exactly like a human update: prior version archived to
    ``org_memory_history`` and the change sealed as ``memory.update`` on the org's own
    chain, attributed to :data:`EVOLVE_USER`. The archive prune then bounds the history to
    ``keep_versions`` rows (survey §7.8 forgetting-pressure), oldest dropped first — the
    sealed audit events themselves are never touched. A second run the same day finds
    nothing to consolidate and nothing to prune: no-op, nothing sealed.
    """
    row = _row(db, org_id)
    consolidated = False
    if row is not None and row.content:
        deduped = consolidate(row.content)
        if deduped != row.content:
            digest = hashlib.sha256(deduped.encode()).hexdigest()
            _, seq = _seal(
                db,
                org_id,
                EVOLVE_USER,
                "memory.update",
                f"kind={KIND_CFO} sha256={digest} chars={len(deduped)}",
                now,
            )
            db.add(
                OrgMemoryHistory(
                    org_id=org_id,
                    kind=KIND_CFO,
                    content=row.content,
                    superseded_at=now,
                    superseded_by=EVOLVE_USER,
                    audit_seq=seq,
                )
            )
            row.content = deduped
            row.updated_at = now
            row.updated_by = EVOLVE_USER
            consolidated = True
    stale = db.scalars(
        select(OrgMemoryHistory)
        .where(OrgMemoryHistory.org_id == org_id, OrgMemoryHistory.kind == KIND_CFO)
        .order_by(OrgMemoryHistory.id.desc())
        .offset(keep_versions)
    ).all()
    for r in stale:
        db.delete(r)
    db.flush()
    return {"consolidated": consolidated, "history_pruned": len(stale)}


# ---------------------------------------------------------------------------------------
# Org profile block — derived live, never stored, never stale (Letta memory-block pattern)
# ---------------------------------------------------------------------------------------


def profile_block(db: Session, org_id: str) -> str:
    """The full profile for prompt injection, empty-safe. Context only — never a source of
    numbers. The ORG block is rendered live from the org row (spec §A1 type 1: derived ⇒
    never stale; needs no retrieval at all). Takes the org id directly so the ``run_loop``
    choke point (which holds the verified org from the request contextvar, not a full
    Principal) can call it; every API surface still goes through :func:`profile_text`."""
    org = db.get(Org, org_id)
    blocks: list[str] = []
    if org is not None:
        blocks.append(f"ORG:\n  {org.name}")
    row = _row(db, org_id)
    if row is not None and row.content:
        blocks.append(f"{CONTEXT_ONLY_LABEL}:\n{row.content}")
    return "\n\n".join(blocks)


def profile_text(db: Session, principal: Principal) -> str:
    """:func:`profile_block` for the verified caller's org (Principal-only scoping, §A3)."""
    return profile_block(db, principal.org_id)


# ---------------------------------------------------------------------------------------
# Episodic recall — lexical search over the org's OWN sealed audit chain (§A1 type 3)
# ---------------------------------------------------------------------------------------

#: Query words that carry no recall signal. Small and fixed — recall is precision-oriented
#: (survey §5.3.3: lexical for exact statutory terms), not a search engine.
_STOPWORDS = frozenset(
    ["the", "a", "an", "is", "are", "was", "were", "our", "we", "you", "what", "whats", "of",
     "on", "in", "for", "to", "do", "did", "and", "or", "it", "this", "that", "how", "much",
     "many", "with", "about"]
)


def _tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9-]+", text.lower()) if len(t) > 1 and t not in _STOPWORDS
    }


#: MEM.P1-3 light query rewrite — a tiny FIXED alias table from common user phrasing to the
#: vocabulary sealed entries actually use (our 12 domain names + hyphenated GST form ids).
#: Deterministic and LLM-free by design; extend the table, never add a model.
_ALIASES: dict[str, str] = {
    "gstr3b": "gstr-3b",
    "gstr1": "gstr-1",
    "salary": "payroll",
    "salaries": "payroll",
    "wages": "payroll",
    "vendor": "payables",
    "vendors": "payables",
    "customer": "revenue",
    "customers": "revenue",
    "invoice": "revenue",
    "invoices": "revenue",
    "cash": "treasury",
    "runway": "treasury",
}


def _rewrite(query: str) -> set[str]:
    """Light deterministic query rewrite (MEM.P1-3): every original token is KEPT, and the
    set is widened with its domain-vocabulary alias plus a naive singular/plural fold.
    Expansion-only — a rewrite can broaden recall but never redirect or drop a term."""
    out: set[str] = set()
    for t in _tokens(query):
        out.add(t)
        alias = _ALIASES.get(t)
        if alias:
            out.add(alias)
        if len(t) > 3:  # ponytail: naive s-fold; a stemmer if recall ever needs morphology
            out.add(t[:-1] if t.endswith("s") else t + "s")
    return out


def recall_decisions(
    db: Session, principal: Principal, query: str, limit: int = 3
) -> list[dict[str, Any]]:
    """Deterministic, LLM-free lexical recall over the caller's org's sealed decisions.

    Org isolation is structural, twice over: entries come from
    :func:`audit_store.load_chain_for`, which reconstructs ONLY this org's hash chain from its
    own tenant genesis (an entry sealed for another org can never link into it), and on
    Postgres the session is already bound to the org GUC so RLS is the floor beneath.
    Legacy entries sealed on the global chain carry no org attribution and are therefore
    EXCLUDED fail-closed — never guessed into an org.

    Returns decision + audit hash, never a number-as-truth (§A4): the caller renders these as
    citations pointing at the tamper-evident chain, not as figures.

    MEM.P1-3 polish, both deterministic and LLM-free: the query is widened by
    :func:`_rewrite` (fixed alias table + plural fold, expansion-only), and a recency
    post-filter re-ranks the top lexical matches (a 2x over-fetch) newest-first — an old
    strong match no longer buries a recent decision.
    """
    want = _rewrite(query)
    if not want:
        return []
    scored: list[tuple[int, int, Any]] = []
    for pos, e in enumerate(audit_store.load_chain_for(db, principal.org_id)):
        text = " ".join(filter(None, (e.action, e.domain, e.query, e.validation_status)))
        score = len(want & _tokens(text))
        if score:
            scored.append((score, pos, e))
    scored.sort(key=lambda t: (-t[0], -t[1]))  # best lexical match first, then most recent
    window = scored[: limit * 2]
    window.sort(key=lambda t: -t[1])  # recency post-filter: newest of the good matches first
    scored = window
    return [
        {
            "action": e.action,
            "domain": e.domain,
            "timestamp": e.timestamp,
            "decision": f"{e.action} ({e.validation_status or 'recorded'}) on {e.timestamp}",
            "audit_hash": e.this_hash,
        }
        for _, _, e in scored[:limit]
    ]


# ---------------------------------------------------------------------------------------
# Playbook feedback — experiential memory (§A1 type 4)
# ---------------------------------------------------------------------------------------

GST_LATEFEE = "GST-LATEFEE"

#: The playbook registry. One entry today — the move whose feedback behaviour was verified
#: live in api-nest (₹800→₹0); the fuller optimizer surface ports more entries with its own
#: ticket. Statute cites carried from the api-nest playbook; the ₹ figure is computed by the
#: EXISTING deterministic engine (gst_calc.late_fee_3b — per-day rate AND the s.47 cap),
#: never re-derived here (§0.6).
PLAYBOOK_IDS = frozenset({GST_LATEFEE})

VERDICTS = ("adopted", "dismissed")


def record_feedback(
    db: Session, principal: Principal, playbook_id: str, verdict: str, *, now: str
) -> dict[str, Any]:
    """Record adopt/dismiss for a playbook — upsert (latest verdict wins), sealed onto the
    org's audit chain as ``playbook.<verdict>`` so the learning is itself auditable."""
    if playbook_id not in PLAYBOOK_IDS:
        raise UnknownPlaybook(f"unknown playbook '{playbook_id}'")
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of: {', '.join(VERDICTS)}")
    row = db.scalars(
        select(PlaybookFeedback).where(
            PlaybookFeedback.org_id == principal.org_id,
            PlaybookFeedback.playbook_id == playbook_id,
        )
    ).first()
    if row is None:
        db.add(
            PlaybookFeedback(
                org_id=principal.org_id,
                playbook_id=playbook_id,
                verdict=verdict,
                created_at=now,
                created_by=principal.user_id,
            )
        )
    else:
        row.verdict = verdict
        row.created_at = now
        row.created_by = principal.user_id
    _seal(db, principal.org_id, principal.user_id, f"playbook.{verdict}", playbook_id, now)
    db.flush()
    return {"playbook_id": playbook_id, "verdict": verdict}


def playbook_moves(
    db: Session, principal: Principal, facts: Mapping[str, object]
) -> dict[str, Any]:
    """Evaluate the playbooks against deterministic FACTS, demoting dismissed moves: a
    dismissed move stays listed (honesty) but its claimed saving is EXCLUDED from the
    quantified total — the org learns; it stops double-counting (api-nest port, ₹800→₹0)."""
    feedback = {
        r.playbook_id: r.verdict
        for r in db.scalars(
            select(PlaybookFeedback).where(PlaybookFeedback.org_id == principal.org_id)
        )
    }
    moves: list[dict[str, Any]] = []
    days = facts.get("gstr3b_days_late")
    if isinstance(days, int) and not isinstance(days, bool) and days > 0:
        moves.append(
            {
                "id": GST_LATEFEE,
                "name": "File overdue GSTR-3B now to stop late fee + interest",
                "statute": "CGST Act 2017",
                "section": "Sec 47 / Sec 50",
                "risk": "low",
                "saving_paise": late_fee_3b(days),  # the ONE cited engine, cap included
                "note": (
                    f"{days} days late — late fee is accruing daily (plus 18% p.a. interest "
                    "on tax, s.50). Filing today caps it."
                ),
                "feedback": feedback.get(GST_LATEFEE),
            }
        )
    quantified = sum(m["saving_paise"] for m in moves if m["feedback"] != "dismissed")
    return {"moves": moves, "quantified_saving_paise": quantified}
