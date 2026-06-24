"""Vault eval cases. One ingested document, content hash intact → one document, zero integrity
failures. Ground truth mirrors ``tests/unit/vault/test_vault_service.py`` (as_of 2026-06-16)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.domains.vault.service import VaultService
from app.llm.schema import ActionClaim

from ..types import EvalCase, Expectation

_AS_OF = date(2026, 6, 16)


def _seed_one_doc(session: Session) -> None:
    VaultService().ingest(
        session, file_name="inv.pdf", content="invoice 100", upload_date="2026-05-10"
    )


CASES: list[EvalCase] = [
    EvalCase(
        id="vault-integrity-clean",
        domain="vault",
        query="How many documents are on file and are any corrupted?",
        seed=_seed_one_doc,
        as_of=_AS_OF,
        expect=Expectation(
            claims={"documents_count": "1", "integrity_failures": "0"},
        ),
        stub_claim=ActionClaim(
            domain="vault",
            narrative="One document on file; its content hash verifies — no integrity failures.",
            claims={"documents_count": "1", "integrity_failures": "0"},
        ),
    ),
]
