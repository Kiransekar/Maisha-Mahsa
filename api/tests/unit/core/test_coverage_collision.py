"""QG.4 finding F3 (RECONCILIATION_2026-07-23 §4.4) — the coverage/fact-key non-collision
invariant.

``ask._verdict`` and the hub assemblers mint a ✓ from coverage membership alone (fact key ∈
ported oracle targets) with no per-request Mahsa call. That is only honest while NO snapshot
fact key collides with a ported target name — otherwise a figure would render ✓ without Mahsa
recomputing that number (§0.4 breach). Zero collisions exist today; this test keeps it that
way: whoever adds a colliding fact key must either rename it or thread a live recompute claim
for it before this gate goes green again.
"""

from __future__ import annotations

from datetime import date

from app.core.mahsa_coverage import load_coverage
from app.dev.seed import seed
from app.domains import build_registry
from app.llm.tools import enrich

AS_OF = date(2026, 7, 15)


def test_no_snapshot_fact_key_collides_with_a_ported_target(session):
    assert seed(session).get("skipped") is None
    ported = {t for t, e in load_coverage()["targets"].items() if e.get("ported")}
    assert ported, "coverage map lists no ported targets — regenerate mahsa_coverage.json"

    registry = build_registry()
    all_facts: set[str] = set()
    for domain in registry.domains():
        snapshot = registry.get(domain).build_snapshot(session, AS_OF)
        facts = set(enrich(snapshot)) - {"as_of"}
        assert facts, f"empty snapshot for '{domain}' — collision check would be vacuous"
        collisions = facts & ported
        assert not collisions, (
            f"domain '{domain}' fact key(s) {sorted(collisions)} collide with ported oracle "
            f"targets: these would render ✓ WITHOUT a live Mahsa recompute (§0.4). Rename the "
            f"fact key or thread a real recompute claim for it."
        )
        all_facts |= facts
    assert len(all_facts) > 50  # the seeded books exercise every hub — keep this non-vacuous
