"""WS9.1 — the Tally import flow over HTTP: parse report mutates NOTHING (row-count asserted),
the token binds the exact file, the confirm word is required, mapping create-new goes through
the real create-account seam, and an unbalanced voucher / non-lossless amount refuses the whole
commit naming its Tally voucher id. RBAC for these two routes (every role, both directions) is
covered by test_rbac_matrix.API_ROUTE_GATES."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.betterauth import get_principal
from app.core.principal import Principal
from app.core.rbac import Role
from app.db.models.ledger import ChartOfAccounts, JournalEntry, JournalLine
from app.db.session import get_session
from app.domains.ledger.service import LedgerService
from app.web.api_tally import router

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parents[1] / "unit" / "ledger" / "fixtures" / "tally"


def _client(session: Session, role: Role = Role.OWNER) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=f"u-{role.value}", org_id="org-7", role=role, email=f"{role.value}@example.com"
    )
    return TestClient(app, raise_server_exceptions=True)


def _file(name: str):
    return {"file": (name, (FIXTURES / name).read_bytes(), "text/xml")}


def _counts(session: Session) -> tuple[int, int, int]:
    n = lambda t: session.scalar(select(func.count()).select_from(t)) or 0  # noqa: E731
    return (n(ChartOfAccounts), n(JournalEntry), n(JournalLine))


def _seed_daybook_accounts(session: Session) -> dict[str, int]:
    svc = LedgerService()
    ids = {
        "HDFC Bank": svc.create_account(
            session, code="1100", name="HDFC Bank", account_type="asset"
        ),
        "Sales": svc.create_account(session, code="4000", name="Sales", account_type="income"),
        "Rent": svc.create_account(session, code="5100", name="Rent", account_type="expense"),
        "Sharma & Co": svc.create_account(
            session, code="1200", name="Sharma & Co", account_type="asset"
        ),
    }
    session.commit()
    return ids


def test_parse_report_is_complete_and_mutates_nothing(session: Session) -> None:
    _seed_daybook_accounts(session)
    before = _counts(session)
    r = _client(session).post("/api/ledger/tally/parse", files=_file("daybook_minimal.xml"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["committed"] is False
    assert body["counts"] == {"ledger_masters": 4, "vouchers": 3, "voucher_lines": 6}
    assert body["errors"] == [] and body["unbalanced"] == []
    assert body["unmatched"] == []  # all four names match existing accounts
    assert {m["name"] for m in body["matched"]} == {"HDFC Bank", "Sales", "Rent", "Sharma & Co"}
    recon = {row["name"]: row for row in body["reconciliation"]}
    assert all(row["match"] is True for row in recon.values())
    assert recon["HDFC Bank"]["computed_closing_paise"] == 1765433
    assert body["preview_token"]
    assert _counts(session) == before, "a parse (preview) must never write"


def test_commit_without_matching_token_is_409_and_writes_nothing(session: Session) -> None:
    _seed_daybook_accounts(session)
    before = _counts(session)
    r = _client(session).post(
        "/api/ledger/tally/commit",
        files=_file("daybook_minimal.xml"),
        data={"preview_token": "forged", "confirm_text": "import", "mapping": "{}"},
    )
    assert r.status_code == 409
    assert "Nothing was changed" in r.json()["detail"]
    assert _counts(session) == before


def test_commit_requires_the_typed_confirm_word(session: Session) -> None:
    _seed_daybook_accounts(session)
    client = _client(session)
    token = client.post("/api/ledger/tally/parse", files=_file("daybook_minimal.xml")).json()[
        "preview_token"
    ]
    before = _counts(session)
    r = client.post(
        "/api/ledger/tally/commit",
        files=_file("daybook_minimal.xml"),
        data={"preview_token": token, "confirm_text": "yes please", "mapping": "{}"},
    )
    assert r.status_code == 422
    assert '"import"' in r.json()["detail"]
    assert _counts(session) == before


def test_swapping_the_file_after_parse_is_409(session: Session) -> None:
    """The token binds the sha256 of the exact previewed bytes — a different file cannot ride
    an old report's approval."""
    _seed_daybook_accounts(session)
    client = _client(session)
    token = client.post("/api/ledger/tally/parse", files=_file("daybook_minimal.xml")).json()[
        "preview_token"
    ]
    r = client.post(
        "/api/ledger/tally/commit",
        files=_file("unbalanced_voucher.xml"),  # not the file that was parsed
        data={"preview_token": token, "confirm_text": "import", "mapping": "{}"},
    )
    assert r.status_code == 409


def test_full_roundtrip_matched_books_tie_to_the_paisa(session: Session) -> None:
    ids = _seed_daybook_accounts(session)
    client = _client(session)
    token = client.post("/api/ledger/tally/parse", files=_file("daybook_minimal.xml")).json()[
        "preview_token"
    ]
    r = client.post(
        "/api/ledger/tally/commit",
        files=_file("daybook_minimal.xml"),
        data={"preview_token": token, "confirm_text": "import", "mapping": "{}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["committed"] is True
    assert body["journals_posted"] == 3
    assert body["accounts_created"] == []
    assert body["trial_balance"] == {
        "total_debit": 9234567,
        "total_credit": 9234567,
        "diff": 0,
        "balanced": True,
    }
    # per-ledger closing matches Tally's stated closing, to the paisa
    gl = LedgerService().general_ledger(session, ids["HDFC Bank"])
    assert gl["closing_balance"] == 1765433
    # the journals carry their Tally voucher ids and the tally source tag
    refs = set(session.scalars(select(JournalEntry.reference)).all())
    assert refs == {"1", "2", "3"}
    assert set(session.scalars(select(JournalEntry.source)).all()) == {"tally"}


def test_unmatched_ledger_blocks_commit_until_mapped_then_create_new_flows(
    session: Session,
) -> None:
    svc = LedgerService()
    svc.create_account(session, code="1000", name="Cash", account_type="asset")
    session.commit()
    client = _client(session)

    report = client.post("/api/ledger/tally/parse", files=_file("unmatched_ledgers.xml")).json()
    assert [u["name"] for u in report["unmatched"]] == ["Diesel Expense"]
    assert report["unmatched"][0]["suggested_type"] == "expense"  # via the GROUP sub-chain
    recon = {row["name"]: row for row in report["reconciliation"]}
    assert recon["Diesel Expense"]["match"] is False  # the checksum mismatch is LISTED
    assert recon["Cash"]["match"] is True

    # committing WITHOUT mapping the unmatched name refuses and names it
    before = _counts(session)
    r = client.post(
        "/api/ledger/tally/commit",
        files=_file("unmatched_ledgers.xml"),
        data={"preview_token": report["preview_token"], "confirm_text": "import", "mapping": "{}"},
    )
    assert r.status_code == 422
    assert "Diesel Expense" in r.json()["detail"]
    assert _counts(session) == before, "a refused commit must write nothing"

    # mapping it to a create-new commits through the real create-account seam
    mapping = {
        "Diesel Expense": {
            "create": {"code": "5200", "name": "Diesel Expense", "account_type": "expense"}
        }
    }
    r = client.post(
        "/api/ledger/tally/commit",
        files=_file("unmatched_ledgers.xml"),
        data={
            "preview_token": report["preview_token"],
            "confirm_text": "import",
            "mapping": json.dumps(mapping),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["journals_posted"] == 1
    assert [c["name"] for c in body["accounts_created"]] == ["Diesel Expense"]
    created = session.scalar(
        select(ChartOfAccounts).where(ChartOfAccounts.name == "Diesel Expense")
    )
    assert created is not None and created.account_type == "expense"
    assert body["trial_balance"]["diff"] == 0


def test_partially_mapped_commit_rolls_back_the_accounts_it_already_created(
    session: Session,
) -> None:
    """All-or-nothing, the hard direction: with NO existing accounts, mapping 'Cash' to a
    create-new but leaving 'Diesel Expense' unmapped means create_account('Cash') has already
    staged a write by the time the refusal fires — the refusal must take that write down with
    it, not commit a half-imported chart."""
    client = _client(session)
    report = client.post("/api/ledger/tally/parse", files=_file("unmatched_ledgers.xml")).json()
    assert {u["name"] for u in report["unmatched"]} == {"Diesel Expense", "Cash"}

    before = _counts(session)
    r = client.post(
        "/api/ledger/tally/commit",
        files=_file("unmatched_ledgers.xml"),
        data={
            "preview_token": report["preview_token"],
            "confirm_text": "import",
            "mapping": json.dumps(
                {"Cash": {"create": {"code": "1000", "name": "Cash", "account_type": "asset"}}}
            ),
        },
    )
    assert r.status_code == 422
    assert "Diesel Expense" in r.json()["detail"]
    session.expire_all()  # read the DB truth, not the identity map
    assert _counts(session) == before, "the staged Cash account must have been rolled back"


def test_unbalanced_voucher_refuses_the_whole_commit_naming_the_voucher(
    session: Session,
) -> None:
    svc = LedgerService()
    svc.create_account(session, code="1000", name="Cash", account_type="asset")
    svc.create_account(session, code="4100", name="Misc Income", account_type="income")
    session.commit()
    client = _client(session)

    report = client.post("/api/ledger/tally/parse", files=_file("unbalanced_voucher.xml")).json()
    assert [u["voucher_id"] for u in report["unbalanced"]] == ["R-99"]
    assert report["unbalanced"][0]["diff_paise"] == 1  # off by exactly one paisa

    before = _counts(session)
    r = client.post(
        "/api/ledger/tally/commit",
        files=_file("unbalanced_voucher.xml"),
        data={"preview_token": report["preview_token"], "confirm_text": "import", "mapping": "{}"},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any("R-99" in e for e in detail["errors"])
    assert _counts(session) == before


def test_non_lossless_amount_refuses_commit(session: Session) -> None:
    svc = LedgerService()
    svc.create_account(session, code="1000", name="Cash", account_type="asset")
    svc.create_account(session, code="4200", name="Interest Income", account_type="income")
    session.commit()
    client = _client(session)

    report = client.post(
        "/api/ledger/tally/parse", files=_file("non_lossless_amount.xml")
    ).json()
    assert any("refusing to round" in e for e in report["errors"])

    before = _counts(session)
    r = client.post(
        "/api/ledger/tally/commit",
        files=_file("non_lossless_amount.xml"),
        data={"preview_token": report["preview_token"], "confirm_text": "import", "mapping": "{}"},
    )
    assert r.status_code == 422
    assert any("R-100" in e for e in r.json()["detail"]["errors"])
    assert _counts(session) == before


def test_doctype_upload_is_refused_at_parse(session: Session) -> None:
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><ENVELOPE/>'
    r = _client(session).post(
        "/api/ledger/tally/parse", files={"file": ("evil.xml", evil, "text/xml")}
    )
    assert r.status_code == 422
    assert "DOCTYPE" in r.json()["detail"]


def test_commit_stores_voucher_anchors_and_vault_ingests_the_source_xml(
    session: Session,
) -> None:
    """CITE.P0-4 (SPEC-MEMCITE-1.0 §B3.2): committing a Tally file vault-ingests the exact
    bytes (content-addressed) and stamps every journal entry with its voucher content hash +
    the source document id. Expected values recomputed independently with hashlib/json."""
    import hashlib

    from app.db.models.vault import Document

    _seed_daybook_accounts(session)
    client = _client(session)
    raw = (FIXTURES / "daybook_minimal.xml").read_bytes()
    token = client.post("/api/ledger/tally/parse", files=_file("daybook_minimal.xml")).json()[
        "preview_token"
    ]
    r = client.post(
        "/api/ledger/tally/commit",
        files=_file("daybook_minimal.xml"),
        data={"preview_token": token, "confirm_text": "import", "mapping": "{}"},
    )
    assert r.status_code == 200, r.text

    doc_sha = hashlib.sha256(raw).hexdigest()
    doc = session.get(Document, doc_sha)
    assert doc is not None, "the source XML must be a content-addressed vault document"
    assert doc.raw_content == raw

    entries = list(session.scalars(select(JournalEntry)).all())
    assert len(entries) == 3
    assert all(e.source_doc_id == doc_sha for e in entries)

    # voucher "3" recomputed independently: Rent 12,345.67 Dr / HDFC Bank 12,345.67 Cr
    payload = json.dumps(
        {
            "voucher_number": "3",
            "date": "2026-04-07",
            "voucher_type": "Payment",
            "narration": "Office rent April (with paise)",
            "lines": [["Rent", 1234567, 0], ["HDFC Bank", 0, 1234567]],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    by_ref = {e.reference: e.voucher_hash for e in entries}
    assert by_ref["3"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert all(h and len(h) == 64 for h in by_ref.values())
