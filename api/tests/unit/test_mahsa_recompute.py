"""Client-side parsing of the Prime-Directive recompute results (§0.4, live /fold wiring).

The live block behaviour is proven end-to-end in dif/tests/integration.rs; here we only pin the
Python client's model shape and the honest-pending vs mismatch distinction it must preserve."""

from app.core.mahsa_client import FoldResult, RecomputeClaim


def _fold_payload(recompute: list[dict]) -> dict:
    return {
        "global_intent": [1.0] * 8,
        "global_dims": ["a"] * 8,
        "validation": {"status": "green", "triggered": []},
        "shape": {
            "status": "green", "color": "green", "layout": "global",
            "requires_approval": False, "global_score": 100.0,
        },
        "rules_version": "test",
        "recompute": recompute,
    }


def test_claim_serialises_without_none_label():
    c = RecomputeClaim(
        target="esi_employee", inputs={"gross_monthly": 2000100}, claimed_paise=15100
    )
    dumped = c.model_dump(exclude_none=True)
    assert "label" not in dumped
    assert dumped["target"] == "esi_employee"
    assert dumped["inputs"] == {"gross_monthly": 2000100}
    assert dumped["claimed_paise"] == 15100


def test_verified_and_mismatch_and_honest_pending_parse():
    res = FoldResult.model_validate(_fold_payload([
        {"target": "esi_employee", "claimed_paise": 15100, "recomputed_paise": 15100,
         "matches": True, "note": "verified"},
        {"target": "tds_on_payment", "claimed_paise": 999999, "recomputed_paise": 500000,
         "matches": False, "note": "MISMATCH"},
        {"target": "itr_computation", "claimed_paise": 1, "recomputed_paise": None,
         "matches": False, "note": "honest-pending"},
    ]))
    verified, mismatch, pending = res.recompute
    assert verified.matches and not verified.honest_pending
    # a real mismatch is NOT honest-pending — it is a hard block signal
    assert not mismatch.matches and not mismatch.honest_pending
    # an unrecomputable target is honest-pending (◐), never treated as a verified figure
    assert not pending.matches and pending.honest_pending


def test_empty_recompute_defaults():
    res = FoldResult.model_validate(_fold_payload([]))
    assert res.recompute == []
