"""CITE.P0-3 (SPEC-MEMCITE-1.0 §B2/§B4) — cell-level citation anchor resolution.

An anchor minted at import time (CITE.P0-1/P0-2) names BOTH the containing file (its content
sha — the vault document id) and the specialized part: a 1-based RAW source line (CSVW
source-number semantics) plus the sha256 of ``canonical_json`` over the trimmed cells, with an
``occurrence`` ordinal distinguishing genuinely identical rows. This module resolves such an
anchor against the immutably stored vault bytes. Exactly three outcomes, all explicit, none
silent — RFC 7111's locator syntax with its silent-clamp error model INVERTED (§0.4):

  RESOLVED — a row at the anchored line hashes to the anchored content hash
  MOVED    — the line does not match, but exactly one row+occurrence in the file carries the
             content hash → resolves, with a visible "row moved from N to M" note (the stored
             anchor is NEVER rewritten — owner decision §B2: render-only, no auto-heal)
  BROKEN   — no row matches, or the stored bytes fail the document's own sha, or the document
             is gone → the working panel says so and the figure's badge downgrades from ✓

File-level references (OCR docs, voucher↔vault links) stay coarse — they get no row claim
here, per §B5: absence of a minted anchor renders as absence, never fabricated precision.
Tally voucher locators extend this module in CITE.P0-4.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit import canonical_json
from app.core.money import Paise
from app.db.models.vault import Document
from app.domains.vault.service import VaultService

RESOLVED = "resolved"
MOVED = "moved"
BROKEN = "broken"

#: How many row-level excerpts a working panel shows per source document before the honest
#: "+N more" summary line. ponytail: display cap only — every anchored row is still resolved.
_PER_DOC_ROWS = 3


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving one anchor. ``note`` is user-facing and always present for
    MOVED ("row moved from N to M") and BROKEN (the reason)."""

    status: str  # RESOLVED | MOVED | BROKEN
    note: str | None = None


# ── the two primitives shared with the minting path (treasury import) ─────────────────────


def csv_records(csv_text: str) -> list[tuple[int, list[str]]]:
    """Non-blank CSV records with their 1-based RAW start line numbers. ``reader.line_num`` is
    the count of physical lines consumed so far, so a record's start line is the previous
    count + 1 — correct even for quoted multi-line fields, and blank lines still advance the
    count (CSVW *source number* semantics: checkable against the raw file, zero parser
    config). The ONE parser both minting and resolution use — a fork here would drift."""
    reader = csv.reader(io.StringIO(csv_text))
    records: list[tuple[int, list[str]]] = []
    consumed = 0
    for row in reader:
        start_line = consumed + 1
        consumed = reader.line_num
        if any(cell.strip() for cell in row):
            records.append((start_line, row))
    return records


def row_hash(cells: Sequence[str]) -> str:
    """sha256(canonical_json([trimmed cells in column order])) — content identity for a row
    with no trustworthy business key (Dolt keyless-table model, spec §B1)."""
    payload = canonical_json([c.strip() for c in cells])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── resolution (§B2) ──────────────────────────────────────────────────────────────────────


def resolve_csv_anchors(
    session: Session,
    doc_id: str,
    anchors: Sequence[tuple[int | None, str, int | None]],
) -> list[Resolution]:
    """Resolve ``(source_row, row_hash, occurrence)`` anchors against one stored document —
    the file is fetched (integrity-re-verified) and parsed ONCE for all of them. A document
    that cannot be fetched or read breaks every anchor on it, loudly, with the reason."""
    try:
        raw = VaultService().get_bytes(session, doc_id)
        text = raw.decode("utf-8-sig")
    except (ValueError, UnicodeDecodeError) as exc:
        return [Resolution(BROKEN, str(exc)) for _ in anchors]

    # (content hash, occurrence) -> raw line. By construction each pair occurs at most once,
    # so a hash match is never ambiguous; "zero matches" is the only broken case left.
    index: dict[tuple[str, int], int] = {}
    counts: dict[str, int] = {}
    for line_no, cells in csv_records(text):
        h = row_hash(cells)
        counts[h] = counts.get(h, 0) + 1
        index[(h, counts[h])] = line_no

    out: list[Resolution] = []
    for source_row, rhash, occurrence in anchors:
        occ = occurrence or 1
        found = index.get((rhash, occ))
        if found is None:
            out.append(
                Resolution(
                    BROKEN,
                    f"no row in the stored source file matches this citation's content hash "
                    f"(occurrence {occ})",
                )
            )
        elif found == source_row:
            out.append(Resolution(RESOLVED))
        else:
            out.append(Resolution(MOVED, f"row moved from {source_row} to {found}"))
    return out


# ── working.documents assembly (§B4.1) ────────────────────────────────────────────────────


def _excerpt(file_name: str, txn: Any) -> str:
    """The spec's render rule: "Bank stmt HDFC-May.csv, row 47: 12/05 NEFT-000123 ₹1,20,000
    Dr" — machine-resolved anchor, human-rendered from the row's own stored fields."""
    what = txn.description or txn.reference or ""
    debit = int(txn.debit or 0)
    amount = debit if debit else int(txn.credit or 0)
    side = "Dr" if debit else "Cr"
    body = " ".join(s for s in (txn.txn_date, what, f"{Paise(amount).format_inr()} {side}") if s)
    return f"{file_name}, row {txn.source_row}: {body}"


def _worst(statuses: Sequence[str]) -> str:
    if BROKEN in statuses:
        return BROKEN
    if MOVED in statuses:
        return MOVED
    return RESOLVED


def bank_documents(session: Session, txns: Sequence[Any]) -> list[dict[str, Any]]:
    """The ``working.documents`` entries for figures derived from bank transactions: one
    excerpt line per anchored source row (capped per document, with an honest aggregate line
    for the rest — never a silent truncation), each carrying its resolution state so the
    caller's badge can downgrade on BROKEN. Rows without anchors (legacy imports) contribute
    NOTHING — no fabricated provenance (§B5).

    ponytail: resolves on every call (one file parse + hash per document). Cache per
    (doc_sha, anchor-set) if the today page ever measures slow — content-addressed docs make
    that cache trivially correct.
    """
    anchored = [t for t in txns if t.source_doc_id and t.row_hash]
    by_doc: dict[str, list[Any]] = {}
    for t in anchored:
        by_doc.setdefault(t.source_doc_id, []).append(t)

    entries: list[dict[str, Any]] = []
    for doc_id, rows in by_doc.items():
        doc = session.get(Document, doc_id)
        file_name = doc.file_name if doc is not None else f"vault document {doc_id[:12]}…"
        url = f"/vault?doc={doc_id}"
        resolutions = resolve_csv_anchors(
            session, doc_id, [(t.source_row, t.row_hash, t.occurrence) for t in rows]
        )
        shown = rows[:_PER_DOC_ROWS]
        for t, res in zip(shown, resolutions[: len(shown)], strict=True):
            entries.append(
                {
                    "label": _excerpt(file_name, t),
                    "url": url,
                    "resolution": res.status,
                    "note": res.note,
                }
            )
        rest = resolutions[len(shown) :]
        if rest:
            statuses = [r.status for r in rest]
            broken = statuses.count(BROKEN)
            moved = statuses.count(MOVED)
            problems = []
            if broken:
                problems.append(f"{broken} broken")
            if moved:
                problems.append(f"{moved} moved")
            entries.append(
                {
                    "label": f"{file_name}: {len(rest)} more anchored row(s)",
                    "url": url,
                    "resolution": _worst(statuses),
                    "note": ", ".join(problems) + " among these rows" if problems else None,
                }
            )
    return entries


def any_broken(documents: Sequence[dict[str, Any]]) -> bool:
    """Whether any citation behind a figure is BROKEN — drives the badge downgrade (§B2)."""
    return any(d.get("resolution") == BROKEN for d in documents)
