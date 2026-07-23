"""WS9.1 — Tally XML parser: real-shaped fixture corpus, exact-paise conversion, hardening,
reconciliation checksums, and the round-trip (import -> trial balance ties to the fixture's
known totals to the paisa)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import tally_import
from app.core.tally_import import TallyImportError, parse_tally_xml, rupees_to_paise_exact
from app.domains.ledger.service import LedgerService

FIXTURES = Path(__file__).parent / "fixtures" / "tally"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ── exact money conversion ─────────────────────────────────────────────────────────


def test_rupees_to_paise_exact() -> None:
    assert rupees_to_paise_exact("50000.00") == 5000000
    assert rupees_to_paise_exact("-12345.67") == -1234567
    assert rupees_to_paise_exact("0") == 0
    assert rupees_to_paise_exact("1.5") == 150  # one decimal is still whole paise


@pytest.mark.parametrize("bad", ["10.005", "0.001", "-99.999"])
def test_sub_paisa_amounts_are_refused_not_rounded(bad: str) -> None:
    with pytest.raises(ValueError, match="refusing to round"):
        rupees_to_paise_exact(bad)


def test_non_numeric_amount_is_refused() -> None:
    with pytest.raises(ValueError, match="not a decimal rupee"):
        rupees_to_paise_exact("1,000.00 Dr")


# ── hardening (untrusted upload) ───────────────────────────────────────────────────


def test_doctype_is_rejected_outright() -> None:
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><ENVELOPE/>'
    with pytest.raises(TallyImportError, match="DOCTYPE"):
        parse_tally_xml(evil)


def test_size_cap_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tally_import, "MAX_BYTES", 64)
    with pytest.raises(TallyImportError, match="cap"):
        parse_tally_xml(b"<ENVELOPE>" + b" " * 100 + b"</ENVELOPE>")


def test_non_envelope_xml_is_refused() -> None:
    with pytest.raises(TallyImportError, match="ENVELOPE"):
        parse_tally_xml(b"<html></html>")


def test_malformed_xml_is_refused() -> None:
    with pytest.raises(TallyImportError, match="not well-formed"):
        parse_tally_xml(b"<ENVELOPE><unclosed></ENVELOPE>")


def test_utf16_export_parses_identically() -> None:
    """Tally commonly exports UTF-16 with a BOM; the decoded parse must be byte-for-byte the
    same result as the UTF-8 fixture."""
    text = _load("daybook_minimal.xml").decode("utf-8")
    utf16 = text.replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16")  # BOM'd
    a = parse_tally_xml(_load("daybook_minimal.xml"))
    b = parse_tally_xml(utf16)
    assert a.ledgers == b.ledgers
    assert a.vouchers == b.vouchers


# ── fixture 1: minimal Day Book ────────────────────────────────────────────────────


def test_daybook_minimal_parses_exactly() -> None:
    p = parse_tally_xml(_load("daybook_minimal.xml"))
    assert p.errors == []
    assert p.unbalanced == []
    assert [m.name for m in p.ledgers] == ["HDFC Bank", "Sales", "Rent", "Sharma & Co"]
    assert [v.voucher_id for v in p.vouchers] == ["1", "2", "3"]
    assert p.vouchers[0].date == "2026-04-01"
    # tally credit-positive -> debit-positive conversion, exact paise
    hdfc = p.ledgers[0]
    assert hdfc.opening_paise == 0
    assert hdfc.closing_paise == 1765433  # Dr ₹17,654.33
    sales = p.ledgers[1]
    assert sales.opening_paise is None  # absent tag is None, not a guessed 0
    assert sales.closing_paise == -5000000  # Cr ₹50,000
    rent_line = p.vouchers[2].lines[0]
    assert (rent_line.debit_paise, rent_line.credit_paise) == (1234567, 0)


def test_daybook_group_suggestions() -> None:
    p = parse_tally_xml(_load("daybook_minimal.xml"))
    assert {m.name: m.suggested_type for m in p.ledgers} == {
        "HDFC Bank": "asset",
        "Sales": "income",
        "Rent": "expense",
        "Sharma & Co": "asset",
    }


def test_daybook_reconciliation_all_match() -> None:
    rows = {r["name"]: r for r in parse_tally_xml(_load("daybook_minimal.xml")).reconciliation()}
    assert all(r["match"] is True for r in rows.values()), rows
    assert rows["HDFC Bank"]["computed_closing_paise"] == 1765433
    assert rows["Sharma & Co"]["computed_closing_paise"] == 2000000
    assert rows["Rent"]["debits_paise"] == 1234567


# ── fixture 2: unmatched ledgers + a stated-closing mismatch ───────────────────────


def test_unmatched_fixture_subgroup_chain_and_mismatch() -> None:
    p = parse_tally_xml(_load("unmatched_ledgers.xml"))
    assert p.errors == []
    # custom sub-group "Vehicle Running" resolves through the GROUP master to expense
    diesel = next(m for m in p.ledgers if m.name == "Diesel Expense")
    assert diesel.suggested_type == "expense"
    rows = {r["name"]: r for r in p.reconciliation()}
    # Cash ties out: Dr 1000 opening − 500 credit = Dr 500 = stated
    assert rows["Cash"]["match"] is True
    # Diesel does not: computed Dr 500 vs stated Dr 600 — the mismatch is LISTED, not absorbed
    assert rows["Diesel Expense"]["match"] is False
    assert rows["Diesel Expense"]["computed_closing_paise"] == 50000
    assert rows["Diesel Expense"]["stated_closing_paise"] == 60000


# ── fixture 3: unbalanced voucher ──────────────────────────────────────────────────


def test_unbalanced_voucher_is_flagged_with_its_id() -> None:
    p = parse_tally_xml(_load("unbalanced_voucher.xml"))
    assert [v.voucher_id for v in p.unbalanced] == ["R-99"]
    v = p.unbalanced[0]
    assert (v.total_debit, v.total_credit) == (100000, 99999)  # off by exactly one paisa


# ── fixture 4: non-lossless amount ─────────────────────────────────────────────────


def test_non_lossless_amount_is_an_error_naming_the_voucher() -> None:
    p = parse_tally_xml(_load("non_lossless_amount.xml"))
    assert p.vouchers == []  # the whole voucher is withheld, never partially parsed
    assert any("R-100" in e and "refusing to round" in e for e in p.errors)


# ── round-trip: import through the REAL ledger service, trial balance to the paisa ─


def test_roundtrip_daybook_trial_balance_ties_to_the_paisa(session) -> None:  # type: ignore[no-untyped-def]
    svc = LedgerService()
    p = parse_tally_xml(_load("daybook_minimal.xml"))
    ids = {
        "hdfc bank": svc.create_account(
            session, code="1100", name="HDFC Bank", account_type="asset"
        ),
        "sales": svc.create_account(session, code="4000", name="Sales", account_type="income"),
        "rent": svc.create_account(session, code="5100", name="Rent", account_type="expense"),
        "sharma & co": svc.create_account(
            session, code="1200", name="Sharma & Co", account_type="asset"
        ),
    }
    for v in p.vouchers:
        svc.post_journal_entry(
            session,
            entry_date=v.date or "",
            description=v.narration,
            lines=[
                {"account_id": ids[ln.ledger.casefold()], "debit": ln.debit_paise,
                 "credit": ln.credit_paise}
                for ln in v.lines
            ],
            source="tally",
            reference=v.voucher_id,
        )
    session.flush()
    tb = svc.trial_balance(session)
    # 50,000.00 + 30,000.00 + 12,345.67 = ₹92,345.67 on each side — to the paisa
    assert tb == {
        "total_debit": 9234567,
        "total_credit": 9234567,
        "diff": 0,
        "balanced": True,
    }
    # and each ledger's closing balance matches Tally's own stated closing (debit-positive)
    gl = svc.general_ledger(session, ids["hdfc bank"])
    assert gl["closing_balance"] == 1765433
