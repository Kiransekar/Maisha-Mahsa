from datetime import date

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
    assert first["retention_until"] == "2033-05-10"  # 7-year statutory

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


def test_build_snapshot_metrics(session):
    svc = VaultService()
    svc.ingest(session, file_name="inv.pdf", content="invoice 100", upload_date="2026-05-10")
    snap = svc.build_snapshot(session, date(2026, 6, 16))
    assert snap["metrics"]["documents_count"] == 1
    assert snap["metrics"]["integrity_failures"] == 0  # healthy by default
