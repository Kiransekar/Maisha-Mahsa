from app.core.mahsa_coverage import badge_state, is_recomputed, load_coverage

# The four targets Rust recomputes today (dif/tests/parity.rs PORTED, §WS3.1).
PORTED = ["esi", "statutory_wage_base", "tds_on_payment", "gratuity_hybrid"]

# A known-unported oracle target (present in the vectors, absent from PORTED).
UNPORTED = ["itr_computation", "retention_until"]


def test_ported_targets_are_recomputed():
    for target in PORTED:
        assert is_recomputed(target) is True, target
        assert badge_state(target) == "verified", target


def test_unported_targets_are_honest_pending():
    for target in UNPORTED:
        assert is_recomputed(target) is False, target
        assert badge_state(target) == "honest_pending", target


def test_unknown_target_is_honest_pending_not_a_crash():
    # A target absent from the coverage map entirely must never be treated as verified.
    assert is_recomputed("no_such_target") is False
    assert badge_state("no_such_target") == "honest_pending"


def test_json_and_loader_agree():
    coverage = load_coverage()
    targets = coverage["targets"]
    assert set(PORTED) <= set(targets)
    assert set(UNPORTED) <= set(targets)
    for name, entry in targets.items():
        assert is_recomputed(name) == bool(entry["ported"])
