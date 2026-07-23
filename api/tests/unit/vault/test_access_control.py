"""Vault: RBAC access control (feature access_control)."""

from app.domains.vault import vault_calc
from app.domains.vault.service import VaultService


def test_role_permissions():
    assert "manage_access" in vault_calc.role_permissions("owner")
    assert vault_calc.role_permissions("viewer") == {"read"}
    assert vault_calc.role_permissions("nobody") == set()


def test_can_access_action_and_sensitivity():
    # viewer can read internal, but not write, and not restricted docs
    assert vault_calc.can_access("viewer", "read", sensitivity="internal") is True
    assert vault_calc.can_access("viewer", "write", sensitivity="internal") is False
    assert vault_calc.can_access("viewer", "read", sensitivity="restricted") is False
    # owner can do everything incl. restricted
    assert vault_calc.can_access("owner", "delete", sensitivity="restricted") is True
    # accountant can read confidential but not restricted
    assert vault_calc.can_access("accountant", "read", sensitivity="confidential") is True
    assert vault_calc.can_access("accountant", "read", sensitivity="restricted") is False


def test_document_sensitivity_mapping():
    assert vault_calc.document_sensitivity("board_resolution") == "restricted"
    assert vault_calc.document_sensitivity("contract") == "confidential"
    assert vault_calc.document_sensitivity("invoice") == "internal"


def test_accessible_documents_filters_by_role(session):
    svc = VaultService()
    svc.ingest(
        session,
        file_name="invoice-1.pdf",
        content="inv",
        upload_date="2026-05-01",
        doc_type="invoice",
    )
    svc.ingest(
        session,
        file_name="board-min.pdf",
        content="board",
        upload_date="2026-05-01",
        doc_type="board_resolution",
    )
    viewer_docs = svc.accessible_documents(session, "viewer")
    owner_docs = svc.accessible_documents(session, "owner")
    assert {d["file_name"] for d in viewer_docs} == {"invoice-1.pdf"}  # not the restricted one
    assert len(owner_docs) == 2
