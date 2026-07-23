"""WS9.1 — the Tally import flow: upload -> PARSE REPORT -> mapping -> typed CONFIRM.

Three-step contract (the api_actions preview/commit pattern, adapted for a file):

* ``POST /api/ledger/tally/parse`` [read] — parses the uploaded XML (hardened, size-capped;
  app.core.tally_import), matches ledger names against the existing chart of accounts, and
  returns THE RECONCILIATION REPORT: counts, row-level errors, unbalanced vouchers, per-ledger
  checksum rows (opening + Σdr − Σcr vs Tally's own stated closing), the unmatched ledger names
  (with a suggested account type from the Tally group — a suggestion, never silently applied),
  and a ``preview_token``. MUTATES NOTHING — it performs only SELECTs (row-count asserted in
  tests).
* The mapping step is client-side: the user maps each unmatched name to an existing account or
  to a create-new (which goes through the SAME ``LedgerService.create_account`` seam the
  create-account drawer action uses).
* ``POST /api/ledger/tally/commit`` [read, write] — re-uploads the SAME bytes (the token is an
  HMAC over the file's sha256 for this org, so a swapped file 409s), requires the typed confirm
  word ``import``, re-validates everything, then commits masters + vouchers atomically through
  ``LedgerService.post_journal_entry`` — double-entry validation stays authoritative, and any
  refusal names the Tally voucher id and changes nothing.

Money: integer paise end to end; a Tally amount that does not convert losslessly was already
rejected at parse and blocks commit. Org comes from the verified principal (§0.8) via the same
``require``/``resolve_principal`` seams as every other route; the token binds it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import tally_import
from app.core.principal import Principal
from app.core.rbac import Capability
from app.core.rbac_deps import require, resolve_principal
from app.core.tally_import import TallyImportError, TallyParse
from app.db.models.ledger import ChartOfAccounts
from app.db.session import get_session
from app.domains.ledger.service import LedgerService
from app.web.api_actions import preview_token

router = APIRouter(
    prefix="/api/ledger/tally",
    tags=["tally"],
    dependencies=[Depends(require(Capability.READ))],
)
_service = LedgerService()

#: The typed confirm word. Committing someone's entire Tally books deserves the same explicit
#: gesture as a statutory filing's confirm_text.
CONFIRM_WORD = "import"


def _token(org_id: str, file_sha256: str) -> str:
    """Reuses api_actions.preview_token (same secret, same canonical HMAC construction) with the
    file hash as the previewed value — one token machine in the codebase, not two."""
    return preview_token(org_id, "ledger", "tally-import", {"file_sha256": file_sha256})


async def _read_capped(file: UploadFile) -> bytes:
    raw = await file.read(tally_import.MAX_BYTES + 1)
    if len(raw) > tally_import.MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds the {tally_import.MAX_BYTES}-byte import cap. "
            "Nothing was changed.",
        )
    return raw


def _parse_or_422(raw: bytes) -> TallyParse:
    try:
        return tally_import.parse_tally_xml(raw)
    except TallyImportError as exc:
        raise HTTPException(
            status_code=422, detail=f"{exc}. Nothing was changed."
        ) from exc


def _existing_accounts(db: Session) -> list[ChartOfAccounts]:
    return list(db.scalars(select(ChartOfAccounts)).all())


@router.post("/parse")
async def tally_parse(
    file: UploadFile,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Step 1: the parse + reconciliation report. Read-only by construction — no session write
    ever happens here; the tests assert every table's row-count is unchanged."""
    raw = await _read_capped(file)
    parsed = _parse_or_422(raw)

    accounts = _existing_accounts(db)
    by_name = {a.name.casefold(): a for a in accounts}
    masters = {m.name.casefold(): m for m in parsed.ledgers}

    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for name in parsed.ledger_names():
        acct = by_name.get(name.casefold())
        if acct is not None:
            matched.append({"name": name, "account_id": acct.id, "code": acct.code})
        else:
            master = masters.get(name.casefold())
            unmatched.append(
                {
                    "name": name,
                    "parent": master.parent if master else None,
                    # a suggestion for the mapping UI, or null — we don't guess
                    "suggested_type": master.suggested_type if master else None,
                }
            )

    file_sha256 = hashlib.sha256(raw).hexdigest()
    return {
        "committed": False,
        "counts": {
            "ledger_masters": len(parsed.ledgers),
            "vouchers": len(parsed.vouchers),
            "voucher_lines": sum(len(v.lines) for v in parsed.vouchers),
        },
        "errors": parsed.errors,
        "unbalanced": [
            {
                "voucher_id": v.voucher_id,
                "total_debit_paise": v.total_debit,
                "total_credit_paise": v.total_credit,
                "diff_paise": v.total_debit - v.total_credit,
            }
            for v in parsed.unbalanced
        ],
        "reconciliation": parsed.reconciliation(),
        "matched": matched,
        "unmatched": unmatched,
        # for the mapping dropdown — the accounts a name can be mapped onto
        "accounts": [
            {"id": a.id, "code": a.code, "name": a.name, "account_type": a.account_type}
            for a in accounts
        ],
        "file_sha256": file_sha256,
        "preview_token": _token(principal.org_id, file_sha256),
        "confirm_word": CONFIRM_WORD,
    }


def _resolve_mapping(
    db: Session,
    parsed: TallyParse,
    mapping: dict[str, Any],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Every referenced ledger name -> an account id. Existing exact (case-insensitive) name
    matches resolve themselves; the rest must be mapped, either to an existing account id or to
    a create-new that goes through LedgerService.create_account (the same seam as the
    create-account drawer action). Raises HTTPException 422 (nothing written — caller rolls
    back) when any name is left unresolved."""
    by_name = {a.name.casefold(): a.id for a in _existing_accounts(db)}
    by_id = {a.id for a in _existing_accounts(db)}
    masters = {m.name.casefold(): m for m in parsed.ledgers}

    resolution: dict[str, int] = {}
    created: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for name in parsed.ledger_names():
        key = name.casefold()
        if key in by_name:
            resolution[key] = by_name[key]
            continue
        entry = mapping.get(name) or mapping.get(key)
        if not isinstance(entry, dict):
            unresolved.append(name)
            continue
        if "account_id" in entry:
            account_id = int(entry["account_id"])
            if account_id not in by_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"mapping for {name!r} points at account {account_id}, which does "
                    "not exist. Nothing was changed.",
                )
            resolution[key] = account_id
            continue
        create = entry.get("create")
        if not isinstance(create, dict):
            unresolved.append(name)
            continue
        master = masters.get(key)
        opening = master.opening_paise if master and master.opening_paise is not None else 0
        try:
            account_id = _service.create_account(
                db,
                code=str(create.get("code") or "").strip(),
                name=str(create.get("name") or name).strip(),
                account_type=str(create.get("account_type") or "").strip(),
                opening_balance=opening,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"creating an account for {name!r} failed: {exc}. Nothing was changed.",
            ) from exc
        resolution[key] = account_id
        created.append({"name": name, "account_id": account_id, "opening_paise": opening})
    if unresolved:
        raise HTTPException(
            status_code=422,
            detail="unmapped Tally ledger(s): "
            + ", ".join(repr(n) for n in unresolved)
            + ". Map each to an existing account or a create-new, then confirm again. "
            "Nothing was changed.",
        )
    return resolution, created


@router.post("/commit", dependencies=[Depends(require(Capability.WRITE))])
async def tally_commit(
    file: UploadFile,
    mapping: str = Form("{}"),
    confirm_text: str = Form(""),
    body_token: str = Form("", alias="preview_token"),
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Step 3: typed CONFIRM. All-or-nothing: one transaction commits masters + every voucher,
    or a single refusal (naming its Tally voucher id) rolls all of it back."""
    raw = await _read_capped(file)
    expected = _token(principal.org_id, hashlib.sha256(raw).hexdigest())
    if not hmac.compare_digest(body_token, expected):
        raise HTTPException(
            status_code=409,
            detail="No matching parse report for this exact file — upload and review the "
            "report first, then confirm. Nothing was changed.",
        )
    if confirm_text.strip().casefold() != CONFIRM_WORD:
        raise HTTPException(
            status_code=422,
            detail=f'Type "{CONFIRM_WORD}" to confirm the import. Nothing was changed.',
        )
    try:
        mapping_dict = json.loads(mapping)
        if not isinstance(mapping_dict, dict):
            raise ValueError("mapping must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=422, detail=f"bad mapping: {exc}. Nothing was changed."
        ) from exc

    parsed = _parse_or_422(raw)
    if parsed.errors:
        raise HTTPException(
            status_code=422,
            detail={
                "errors": parsed.errors,
                "note": "The file has rows that cannot be imported exactly. Nothing was changed.",
            },
        )
    if parsed.unbalanced:
        raise HTTPException(
            status_code=422,
            detail={
                "errors": [
                    f"Tally voucher {v.voucher_id} is not balanced "
                    f"(debits {v.total_debit} paise vs credits {v.total_credit} paise)"
                    for v in parsed.unbalanced
                ],
                "note": "An unbalanced voucher cannot enter the books. Nothing was changed.",
            },
        )

    try:
        resolution, created = _resolve_mapping(db, parsed, mapping_dict)
        journals = 0
        for v in parsed.vouchers:
            try:
                # post_journal_entry re-checks balance — the double-entry gate stays
                # authoritative even if the pre-check above ever drifts.
                _service.post_journal_entry(
                    db,
                    entry_date=v.date or "",
                    description=v.narration or v.voucher_type or f"Tally {v.voucher_id}",
                    lines=[
                        {
                            "account_id": resolution[ln.ledger.casefold()],
                            "debit": ln.debit_paise,
                            "credit": ln.credit_paise,
                        }
                        for ln in v.lines
                    ],
                    source="tally",
                    reference=v.voucher_id,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Tally voucher {v.voucher_id}: {exc}. Nothing was imported.",
                ) from exc
            journals += 1
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    return {
        "committed": True,
        "accounts_created": created,
        "journals_posted": journals,
        # the books immediately after — the same arithmetic /api/ledger/trial-balance serves
        "trial_balance": _service.trial_balance(db),
    }
