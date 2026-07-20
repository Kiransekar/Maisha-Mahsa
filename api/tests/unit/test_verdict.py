"""WS3.4 — Verdict object binding tests.

These must be *able to fail*: each proves that changing one bound input changes the hash, and
that tampering is detectable. No vacuous asserts.
"""

from __future__ import annotations

from app.core.verdict import Figure, build_verdict, compute_verdict_hash

FIGS = [Figure("tds_192", 15050), Figure("esi_employee", 651)]
RPV = "2026.07.0"
ORG = "org_alpha"


def test_deterministic_same_inputs_same_hash() -> None:
    a = build_verdict(list(FIGS), RPV, org_id=ORG)
    b = build_verdict(list(FIGS), RPV, org_id=ORG)
    assert a.hash == b.hash
    assert a.is_intact()


def test_hash_changes_when_a_figure_value_changes() -> None:
    base = build_verdict(list(FIGS), RPV, org_id=ORG)
    changed = build_verdict([Figure("tds_192", 15051), FIGS[1]], RPV, org_id=ORG)
    assert changed.hash != base.hash


def test_hash_changes_when_a_figure_key_changes() -> None:
    base = build_verdict(list(FIGS), RPV, org_id=ORG)
    changed = build_verdict([Figure("tds_194j", 15050), FIGS[1]], RPV, org_id=ORG)
    assert changed.hash != base.hash


def test_hash_changes_when_rule_pack_version_changes() -> None:
    base = build_verdict(list(FIGS), RPV, org_id=ORG)
    changed = build_verdict(list(FIGS), "2026.08.0", org_id=ORG)
    assert changed.hash != base.hash


def test_org_id_is_bound_two_orgs_same_figures_differ() -> None:
    a = build_verdict(list(FIGS), RPV, org_id="org_alpha")
    b = build_verdict(list(FIGS), RPV, org_id="org_beta")
    assert a.hash != b.hash


def test_tamper_after_sealing_is_detectable() -> None:
    v = build_verdict(list(FIGS), RPV, org_id=ORG)
    assert v.is_intact()
    # Recompute against tampered figures: the stored hash no longer matches.
    tampered = [Figure("tds_192", 99999), FIGS[1]]
    assert compute_verdict_hash(tampered, v.rule_pack_version, v.org_id) != v.hash


def test_figure_order_is_part_of_the_seal() -> None:
    a = build_verdict([FIGS[0], FIGS[1]], RPV, org_id=ORG)
    b = build_verdict([FIGS[1], FIGS[0]], RPV, org_id=ORG)
    assert a.hash != b.hash
