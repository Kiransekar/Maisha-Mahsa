from datetime import date

from app.core.rbac import Role
from app.db.models.vault import Document
from app.domains.vault.service import VaultService


def test_ingest_and_dedup(session):
    svc = VaultService()
    first = svc.ingest(
        session,
        file_name="May_invoice.pdf",
        content="invoice total 600",
        upload_date="2026-05-10",
        domain="revenue",
    )
    assert first["duplicate"] is False
    assert first["doc_type"] == "invoice"  # classified from file name
    assert first["retention_until"] == "2035-03-31"  # 8-year statutory from FY-end (§WS1.C5)

    # re-ingesting identical content is detected as a duplicate (same content hash = id)
    again = svc.ingest(
        session,
        file_name="May_invoice_copy.pdf",
        content="invoice total 600",
        upload_date="2026-05-11",
    )
    assert again["duplicate"] is True
    assert again["id"] == first["id"]


def test_search_and_integrity(session):
    svc = VaultService()
    res = svc.ingest(
        session,
        file_name="contract.pdf",
        content="master services agreement with acme",
        upload_date="2026-05-10",
    )
    assert [d["id"] for d in svc.search(session, "acme")] == [res["id"]]
    assert svc.verify_integrity(session, res["id"], "master services agreement with acme") is True
    assert svc.verify_integrity(session, res["id"], "forged contract") is False


def test_browse_masks_by_role_clearance_and_reports_integrity(session):
    # P2-1: an "internal" doc (default sensitivity) and a "restricted" one (board_resolution).
    svc = VaultService()
    plain = svc.ingest(
        session, file_name="inv.pdf", content="invoice acme 500", upload_date="2026-05-10"
    )
    board = svc.ingest(
        session,
        file_name="minutes.pdf",
        content="board resolution acme",
        upload_date="2026-05-10",
        doc_type="board_resolution",
    )

    # Investor's clearance tops out at "internal" (app.core.landing.ROLE_CLEARANCE) — sees the
    # plain doc in full, but the board resolution is a visible LOCK, never absent, never leaked.
    investor = {r["id"]: r for r in svc.browse(session, "acme", role=Role.INVESTOR)}
    assert investor[plain["id"]]["restricted"] is False
    assert investor[plain["id"]]["integrity_ok"] is True
    assert "ocr_text" not in investor[plain["id"]]  # never the raw content, restricted or not
    assert investor[board["id"]]["restricted"] is True
    assert investor[board["id"]]["reason"] == "requires restricted clearance"
    assert "tags" not in investor[board["id"]] and "integrity_ok" not in investor[board["id"]]

    # Owner clears everything, sees both.
    owner = {r["id"]: r for r in svc.browse(session, "acme", role=Role.OWNER)}
    assert owner[board["id"]]["restricted"] is False
    assert owner[board["id"]]["integrity_ok"] is True

    # An empty query is the document LIST, not "no results" (reuses vault_calc.search's
    # empty-string-matches-everything behaviour — no second listing endpoint needed).
    assert {r["id"] for r in svc.browse(session, "", role=Role.OWNER)} == {plain["id"], board["id"]}


def test_browse_reports_integrity_failure_loudly(session):
    # A directly-tampered row (no ingest path in this app can produce this — the id/sha256 are
    # always the content hash at write time — but a DB-level mismatch must still surface, not
    # be silently trusted). Same seed shape as tests/integration/test_rbac_matrix.py's
    # _seed_vault_doc.
    tampered_id = "e" * 64
    session.add(
        Document(
            id=tampered_id,
            file_name="invoice.pdf",
            file_path="/vault/invoice.pdf",
            doc_type="invoice",
            upload_date="2026-07-01",
            sha256=tampered_id,
            ocr_text="this text does not hash to the stored sha256",
        )
    )
    session.commit()

    svc = VaultService()
    rows = svc.browse(session, "", role=Role.OWNER)
    assert rows[0]["integrity_ok"] is False


def test_build_snapshot_metrics(session):
    svc = VaultService()
    svc.ingest(session, file_name="inv.pdf", content="invoice 100", upload_date="2026-05-10")
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["metrics"]["documents_count"] == 1
    assert snap["metrics"]["integrity_failures"] == 0  # healthy by default
