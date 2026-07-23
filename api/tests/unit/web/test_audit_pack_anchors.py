"""CITE.P1-1 (SPEC-MEMCITE-1.0 §B4.2) — the audit-pack assembler populates
``AuditFigure.anchors`` for the figure genuinely derived from imported bank statements,
reusing the ONE anchor resolution service (``app.core.anchors`` — never forked)."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.core.audit_pack import build_audit_pack, verify_pack_integrity
from app.db.models.treasury import BankAccount
from app.db.models.vault import Document
from app.domains.treasury.service import TreasuryService
from app.web.api_domains import _audit_pack_entity_data

_CSV = "date,description,debit,credit\n2026-07-01,NEFT-000123,0,120000\n"


def _import_statement(session: Session) -> None:
    acct = BankAccount(bank_name="HDFC", account_number="1", ifsc="HDFC0001")
    session.add(acct)
    session.flush()
    TreasuryService().import_csv(session, acct.id, _CSV, file_name="HDFC-May.csv")


def test_pack_cash_figure_carries_resolved_bank_anchors(session: Session) -> None:
    _import_statement(session)
    data = _audit_pack_entity_data(session, org_id="org1", rules_version="rv1")
    [extra] = data["balance_sheet"]["extra_figures"]
    assert extra["value_paise"] == 1_20_000_00  # the imported ₹1,20,000 credit, in paise
    [anchor] = extra["anchors"]
    assert anchor["file_name"] == "HDFC-May.csv"
    assert anchor["locator"] == {"kind": "csv_row", "source_row": 2}
    assert anchor["resolution"] == "resolved"
    assert "NEFT-000123" in anchor["excerpt"]

    pack = build_audit_pack(data)
    [fig] = [
        f
        for f in pack["sections"]["balance_sheet"]
        if f["label"].startswith("Cash & bank balances")
    ]
    assert fig["badge"] == "honest_pending"  # unported target — never a fabricated ✓
    assert fig["anchors"][0]["resolution"] == "resolved"
    assert verify_pack_integrity(pack) is True


def test_pack_anchor_resolves_broken_when_source_file_is_tampered(session: Session) -> None:
    """§B2 honesty at export time: the stored source bytes fail their own sha → the pack's
    sealed anchor says BROKEN, never a stale RESOLVED claim."""
    _import_statement(session)
    doc = session.get(Document, hashlib.sha256(_CSV.encode("utf-8")).hexdigest())
    assert doc is not None
    doc.raw_content = b"tampered"
    session.flush()

    data = _audit_pack_entity_data(session, org_id="org1", rules_version="rv1")
    [anchor] = data["balance_sheet"]["extra_figures"][0]["anchors"]
    assert anchor["resolution"] == "broken"
    assert anchor["note"]


def test_pack_without_bank_accounts_has_no_treasury_figure(session: Session) -> None:
    """Honest-empty, backward compatible: no bank data → no cash figure, no fabricated ₹0,
    and the balance-sheet section is exactly the pre-P1-1 shape."""
    data = _audit_pack_entity_data(session, org_id="org1", rules_version="rv1")
    assert "extra_figures" not in data["balance_sheet"]
