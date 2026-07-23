"""CITE.P0-3 (SPEC-MEMCITE-1.0 §B2/§B4.1): anchor resolution — verifiable or loudly broken.

Three outcomes, none silent: RESOLVED (locator + content hash match), MOVED (hash found at
exactly one other row+occurrence — resolves WITH a visible note, the stored anchor is never
rewritten), BROKEN (no match, or the stored bytes fail the document's own sha — the badge
downgrades, never a quiet render). Anchors are minted by the REAL import path
(``TreasuryService.import_csv``), so these tests also pin that mint→resolve round-trips.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.anchors import (
    BROKEN,
    MOVED,
    RESOLVED,
    any_broken,
    bank_documents,
    resolve_csv_anchors,
)
from app.db.models.treasury import BankAccount, BankTransaction
from app.db.models.vault import Document
from app.domains.treasury.service import TreasuryService
from app.domains.vault.service import VaultService

CSV_TEXT = (
    "date,description,reference,debit,credit,balance\n"
    "2026-05-05,Opening,REF1,0,100000,100000\n"
    "\n"
    "2026-05-10, AWS invoice ,REF2,20000,0, 80000\n"
)

# The same two data rows, re-exported in the opposite order (header intact) — the "source
# file churned" case §B2's MOVED outcome exists for.
CSV_REORDERED = (
    "date,description,reference,debit,credit,balance\n"
    "2026-05-10, AWS invoice ,REF2,20000,0, 80000\n"
    "2026-05-05,Opening,REF1,0,100000,100000\n"
)

# Two byte-identical rows — occurrence is the only thing telling them apart.
CSV_TWINS = (
    "date,description,reference,debit,credit\n"
    "2026-05-05,NEFT UPI,REF9,0,50000\n"
    "2026-05-05,NEFT UPI,REF9,0,50000\n"
)


def _account(session: Session) -> BankAccount:
    acct = BankAccount(bank_name="HDFC", account_number="0001", ifsc="HDFC0000001")
    session.add(acct)
    session.flush()
    return acct


def _import(session: Session, csv_text: str = CSV_TEXT, file_name: str = "hdfc-may.csv") -> str:
    acct = _account(session)
    TreasuryService().import_csv(session, acct.id, csv_text, file_name=file_name)
    return hashlib.sha256(csv_text.encode("utf-8")).hexdigest()


def _txns(session: Session) -> list[BankTransaction]:
    return list(session.scalars(select(BankTransaction).order_by(BankTransaction.id)).all())


def _anchors(txns: list[BankTransaction]) -> list[tuple[int | None, str, int | None]]:
    return [(t.source_row, t.row_hash, t.occurrence) for t in txns]  # type: ignore[misc]


# ── the three outcomes (§B2) ──────────────────────────────────────────────────────────────


def test_untouched_file_resolves(session: Session) -> None:
    doc_id = _import(session)
    out = resolve_csv_anchors(session, doc_id, _anchors(_txns(session)))
    assert [r.status for r in out] == [RESOLVED, RESOLVED]
    assert all(r.note is None for r in out), "a clean resolution carries no scary note"


def test_locator_mismatch_moves_with_visible_note(session: Session) -> None:
    """Hash present at exactly one row, locator wrong → MOVED, and the note says from→to.
    The exact wording is load-bearing: it is what the working panel shows the user."""
    doc_id = _import(session)
    first = _txns(session)[0]  # its content really lives at raw line 2
    [res] = resolve_csv_anchors(session, doc_id, [(99, str(first.row_hash), 1)])
    assert res.status == MOVED
    assert res.note == "row moved from 99 to 2"


def test_reordered_reexport_resolves_every_row_as_moved(session: Session) -> None:
    """The spec's churn case: anchors minted against the original file, resolved against a
    re-exported reordering — every row still resolves (content identity), all visibly MOVED."""
    doc_id = _import(session)
    txns = _txns(session)
    new_doc = VaultService().ingest_bytes(
        session,
        file_name="hdfc-may-reexport.csv",
        content=CSV_REORDERED.encode("utf-8"),
        upload_date="2026-05-31",
    )
    out = resolve_csv_anchors(session, new_doc["id"], _anchors(txns))
    assert [r.status for r in out] == [MOVED, MOVED]
    # original raw lines 2 and 4 (blank line counted) land at 3 and 2 in the re-export
    assert out[0].note == "row moved from 2 to 3"
    assert out[1].note == "row moved from 4 to 2"
    assert doc_id != new_doc["id"], "changed bytes are a NEW document (content addressing)"


def test_tampered_stored_bytes_break_every_anchor_loudly(session: Session) -> None:
    """§B2 BROKEN via the file's own sha: the stored bytes no longer hash to the document id.
    Nothing resolves — not even rows whose text would still match — because the file itself
    can no longer be trusted."""
    doc_id = _import(session)
    doc = session.get(Document, doc_id)
    assert doc is not None
    doc.raw_content = CSV_TEXT.replace("100000", "999999").encode("utf-8")
    session.flush()
    out = resolve_csv_anchors(session, doc_id, _anchors(_txns(session)))
    assert [r.status for r in out] == [BROKEN, BROKEN]
    assert all(r.note and "integrity" in r.note for r in out)


def test_unknown_content_hash_breaks(session: Session) -> None:
    doc_id = _import(session)
    [res] = resolve_csv_anchors(session, doc_id, [(2, "0" * 64, 1)])
    assert res.status == BROKEN
    assert res.note is not None and "content hash" in res.note


def test_missing_document_breaks(session: Session) -> None:
    [res] = resolve_csv_anchors(session, "f" * 64, [(2, "0" * 64, 1)])
    assert res.status == BROKEN
    assert res.note is not None and "not found" in res.note


def test_twin_rows_resolve_by_occurrence_and_a_third_occurrence_breaks(session: Session) -> None:
    _import(session, CSV_TWINS, file_name="twins.csv")
    doc_id = hashlib.sha256(CSV_TWINS.encode("utf-8")).hexdigest()
    t1, t2 = _txns(session)
    assert (t1.occurrence, t2.occurrence) == (1, 2)
    r1, r2, r3 = resolve_csv_anchors(
        session,
        doc_id,
        [
            (t1.source_row, str(t1.row_hash), 1),
            (t2.source_row, str(t2.row_hash), 2),
            (5, str(t1.row_hash), 3),  # a third identical row never existed
        ],
    )
    assert (r1.status, r2.status) == (RESOLVED, RESOLVED)
    assert r3.status == BROKEN
    assert r3.note is not None and "occurrence 3" in r3.note


# ── working.documents assembly (§B4.1) ────────────────────────────────────────────────────


def test_bank_documents_renders_spec_rule_excerpts(session: Session) -> None:
    """The render rule: "file, row N: <date> <narration> <₹amount> Dr/Cr" — human-rendered
    from the row's own stored fields, machine-resolved via the anchor."""
    _import(session)
    docs = bank_documents(session, _txns(session))
    assert [d["label"] for d in docs] == [
        "hdfc-may.csv, row 2: 2026-05-05 Opening ₹1,00,000.00 Cr",
        "hdfc-may.csv, row 4: 2026-05-10 AWS invoice ₹20,000.00 Dr",
    ]
    assert all(d["resolution"] == RESOLVED for d in docs)
    assert all(d["url"].startswith("/vault?doc=") for d in docs)
    assert not any_broken(docs)


def test_bank_documents_caps_rows_with_an_honest_summary_line(session: Session) -> None:
    rows = "\n".join(f"2026-05-{5 + i:02d},Txn {i},R{i},100,0" for i in range(5))
    csv_text = f"date,description,reference,debit,credit\n{rows}\n"
    _import(session, csv_text, file_name="big.csv")
    docs = bank_documents(session, _txns(session))
    assert len(docs) == 4  # 3 excerpts + the aggregate line, never a silent truncation
    assert docs[3]["label"] == "big.csv: 2 more anchored row(s)"
    assert docs[3]["resolution"] == RESOLVED
    assert docs[3]["note"] is None


def test_bank_documents_summary_line_carries_broken_state(session: Session) -> None:
    """A broken row hidden behind the display cap still surfaces: the aggregate line goes
    BROKEN and says how many — the badge downgrade cannot be dodged by row count."""
    rows = "\n".join(f"2026-05-{5 + i:02d},Txn {i},R{i},100,0" for i in range(5))
    csv_text = f"date,description,reference,debit,credit\n{rows}\n"
    doc_id = _import(session, csv_text, file_name="big.csv")
    doc = session.get(Document, doc_id)
    assert doc is not None
    doc.raw_content = b"tampered"
    session.flush()
    docs = bank_documents(session, _txns(session))
    assert any_broken(docs)
    assert docs[3]["resolution"] == BROKEN
    assert docs[3]["note"] == "2 broken among these rows"


def test_legacy_rows_without_anchors_render_document_less(session: Session) -> None:
    """§B5: no minted anchor → no fabricated provenance. A pre-anchor transaction contributes
    nothing to working.documents."""
    acct = _account(session)
    session.add(BankTransaction(account_id=acct.id, txn_date="2026-01-01", debit=100, credit=0))
    session.flush()
    assert bank_documents(session, _txns(session)) == []
