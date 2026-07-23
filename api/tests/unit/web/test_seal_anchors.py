"""CITE.P1-3 (SPEC-MEMCITE-1.0 §B4.4) — anchor lists sealed into the ``_seal`` detail.

The spec sentence, implemented precisely: "include the anchor list in the sealed preview
detail (``api_filings._seal`` — detail already rides inside the hash-chained audit ``query``
field), so input provenance rides the existing chain with no change to
``compute_verdict_hash``". These tests must be able to fail:

* backward compatibility — an anchor-less figure serializes byte-identically to the
  pre-CITE.P1-3 shape, so every existing chain still verifies and every existing hash is
  reproducible;
* provenance rides the chain — a sealed anchored figure carries its anchors inside the
  hashed ``query`` payload, and tampering an anchor after the fact breaks chain verification.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit_store
from app.core.audit import canonical_json, verify_chain
from app.db.models.shared import AuditLog
from app.web.api_filings import _detail, _figure, _seal

_ANCHOR = {
    "doc_sha256": "a" * 64,
    "file_name": "HDFC-May.csv",
    "locator": {"kind": "csv_row", "source_row": 47},
    "row_hash": "b" * 64,
    "occurrence": 1,
    "excerpt": "HDFC-May.csv, row 47: 12/05 NEFT-000123 ₹1,20,000.00 Dr",
    "resolution": "resolved",
    "note": None,
}


def _plain_figure() -> dict:
    return _figure(
        target="late_fee_3b", label="Late fee", value_paise=5_000, chk=None, mahsa_up=True
    )


def _anchored_figure() -> dict:
    return _figure(
        target="itc_setoff",
        label="Cash payable after ITC set-off",
        value_paise=90_000,
        chk=None,
        mahsa_up=True,
        anchors=[dict(_ANCHOR)],
    )


def test_detail_without_anchors_is_byte_identical_to_the_pre_p13_shape() -> None:
    """Backward-compat pin: the exact key set (and therefore the exact canonical JSON, and
    therefore every existing chain hash) is unchanged for anchor-less figures."""
    detail = _detail(kind="gstr3b", figures=[_plain_figure()], verdict_hash=None, trace_id="t-1")
    [fig] = detail["figures"]
    assert set(fig) == {"target", "label", "value_paise", "state"}
    assert canonical_json(detail) == canonical_json(
        {
            "kind": "gstr3b",
            "figures": [
                {
                    "target": "late_fee_3b",
                    "label": "Late fee",
                    "value_paise": 5_000,
                    "state": "honest_pending",
                }
            ],
            "verdict_hash": None,
            "trace_id": "t-1",
        }
    )


def test_detail_seals_the_anchor_list_for_an_anchored_figure() -> None:
    detail = _detail(kind="gstr3b", figures=[_anchored_figure()], verdict_hash=None, trace_id="t-2")
    [fig] = detail["figures"]
    assert fig["anchors"] == [_ANCHOR]


def test_existing_chain_still_verifies_and_anchored_entry_chains_onto_it(
    session: Session,
) -> None:
    """An old-style (anchor-less) sealed entry followed by an anchored one: the whole chain
    verifies, and the anchors are recoverable from the sealed ``query`` payload."""
    _seal(
        session,
        action="filing.preview",
        domain="gst",
        user_id="u1",
        detail=_detail(kind="gstr3b", figures=[_plain_figure()], verdict_hash=None, trace_id="t-1"),
        status="previewed",
        rules_version=None,
    )
    entry = _seal(
        session,
        action="filing.preview",
        domain="gst",
        user_id="u1",
        detail=_detail(
            kind="gstr3b", figures=[_anchored_figure()], verdict_hash=None, trace_id="t-2"
        ),
        status="previewed",
        rules_version=None,
    )
    session.commit()

    chain = audit_store.load_chain(session)
    assert verify_chain(chain) is True
    sealed = json.loads(entry.query)
    assert sealed["figures"][0]["anchors"] == [_ANCHOR]
    # The old-style entry is untouched by the new code path — no anchors key materialized.
    first = json.loads(chain[0].query)
    assert "anchors" not in first["figures"][0]


def test_tampering_a_sealed_anchor_breaks_chain_verification(session: Session) -> None:
    """The anchor list is inside the hashed core payload: rewriting a sealed anchor (e.g.
    pointing the citation at a different row) is detected by ``verify_chain``."""
    entry = _seal(
        session,
        action="filing.preview",
        domain="gst",
        user_id="u1",
        detail=_detail(
            kind="gstr3b", figures=[_anchored_figure()], verdict_hash=None, trace_id="t-3"
        ),
        status="previewed",
        rules_version=None,
    )
    session.commit()
    assert verify_chain(audit_store.load_chain(session)) is True

    row = session.scalars(select(AuditLog).where(AuditLog.this_hash == entry.this_hash)).one()
    tampered = json.loads(row.query)
    tampered["figures"][0]["anchors"][0]["locator"]["source_row"] = 99
    row.query = canonical_json(tampered)
    session.flush()
    assert verify_chain(audit_store.load_chain(session)) is False
