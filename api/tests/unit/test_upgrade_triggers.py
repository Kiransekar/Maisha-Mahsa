"""WS6.3 — upgrade-trigger event tests.

Each of the 5 named triggers is checked at its threshold (fires) and just below it
(does not fire), plus the emitted event's target. No router wiring — this is a pure
detector: ``detect(event_type, payload, plan) -> UpgradeTrigger | None``.
"""

import pytest

from app.core import entitlements as ent
from app.core import upgrade_triggers as ut

# --- employee #11 -> Bonus/Gratuity -------------------------------------------------


def test_employee_10_does_not_fire() -> None:
    assert ut.detect("employee_added", {"employee_count": 10}, "basics") is None


def test_employee_11_fires_bonus_gratuity() -> None:
    trig = ut.detect("employee_added", {"employee_count": 11}, "basics")
    assert trig is not None
    assert trig.name == "employee_11"
    assert trig.target == "Bonus/Gratuity"
    assert trig.target_feature == "gratuity"
    assert trig.target_feature in ent.DOMAIN_FEATURES  # names a real feature, not a typo
    assert trig.target_plan in ent.PLAN_ORDER


def test_employee_count_above_11_still_fires() -> None:
    # not a one-shot edge case — every headcount past the threshold is still the moment
    assert ut.detect("employee_added", {"employee_count": 40}, "basics") is not None


# --- first SAFE -> Equity -------------------------------------------------------------


def test_zero_safes_does_not_fire() -> None:
    assert ut.detect("safe_note_recorded", {"safe_count": 0}, "basics") is None


def test_first_safe_fires_equity() -> None:
    trig = ut.detect("safe_note_recorded", {"safe_count": 1}, "basics")
    assert trig is not None
    assert trig.name == "first_safe"
    assert trig.target == "Equity"
    assert trig.target_feature == "safe_notes"
    assert trig.target_plan == ent.min_plan_for("safe_notes")


def test_second_safe_does_not_refire() -> None:
    # only the FIRST SAFE is the product moment, not every subsequent note
    assert ut.detect("safe_note_recorded", {"safe_count": 2}, "startup") is None


# --- AATO ₹5Cr -> e-invoice add-on ----------------------------------------------------


def test_aato_just_below_5cr_does_not_fire() -> None:
    below = int(ut.AATO_5CR_PAISE) - 1
    assert ut.detect("aato_updated", {"aato_paise": below}, "basics") is None


def test_aato_5cr_fires_e_invoice() -> None:
    trig = ut.detect("aato_updated", {"aato_paise": int(ut.AATO_5CR_PAISE)}, "basics")
    assert trig is not None
    assert trig.name == "aato_5cr"
    assert trig.target == "e-invoice add-on"
    assert trig.target_feature == "e_invoice"
    assert trig.target_plan == ent.min_plan_for("e_invoice")


def test_aato_above_5cr_also_fires() -> None:
    above = int(ut.AATO_5CR_PAISE) + 1_00_00_000
    assert ut.detect("aato_updated", {"aato_paise": above}, "basics") is not None


# --- second GSTIN -> Growth -----------------------------------------------------------


def test_first_gstin_does_not_fire() -> None:
    assert ut.detect("gstin_registered", {"gstin_count": 1}, "startup") is None


def test_second_gstin_fires_growth() -> None:
    trig = ut.detect("gstin_registered", {"gstin_count": 2}, "startup")
    assert trig is not None
    assert trig.name == "second_gstin"
    assert trig.target == "Growth"
    assert trig.target_plan == "growth"
    assert trig.target_feature is None  # multi-GSTIN is architectural, not one feature key


# --- board meeting -> secretarial -----------------------------------------------------


def test_unrelated_event_does_not_fire_board_meeting_trigger() -> None:
    assert ut.detect("expense_created", {}, "growth") is None


def test_board_meeting_fires_secretarial() -> None:
    trig = ut.detect("board_meeting_scheduled", {}, "basics")
    assert trig is not None
    assert trig.name == "board_meeting"
    assert trig.target == "secretarial"
    assert trig.target_feature == "secretarial"
    assert trig.target_plan == ent.min_plan_for("secretarial")


# --- already-entitled flag reflects the ORG's current plan, not just the feature ------


def test_already_entitled_true_when_org_plan_already_covers_it() -> None:
    # safe_notes lands on Startup; an org already ON Startup gets the pitch with
    # already_entitled=True (informational), not a phantom "you need to upgrade".
    trig = ut.detect("safe_note_recorded", {"safe_count": 1}, "startup")
    assert trig is not None
    assert trig.already_entitled is True


def test_already_entitled_false_when_plan_lacks_it() -> None:
    trig = ut.detect("safe_note_recorded", {"safe_count": 1}, "basics")
    assert trig is not None
    assert trig.already_entitled is False


# --- defensive: unknown plan fails loud ------------------------------------------------


def test_unknown_plan_raises() -> None:
    with pytest.raises(ValueError, match="unknown plan"):
        ut.detect("employee_added", {"employee_count": 11}, "enterprise")


# --- every named trigger references a real feature key when it has one ----------------


def test_every_target_feature_is_a_real_registry_key() -> None:
    fired = [
        ut.detect("employee_added", {"employee_count": 11}, "basics"),
        ut.detect("safe_note_recorded", {"safe_count": 1}, "basics"),
        ut.detect("aato_updated", {"aato_paise": int(ut.AATO_5CR_PAISE)}, "basics"),
        ut.detect("gstin_registered", {"gstin_count": 2}, "basics"),
        ut.detect("board_meeting_scheduled", {}, "basics"),
    ]
    assert all(t is not None for t in fired)
    for trig in fired:
        assert trig is not None  # narrow for mypy
        if trig.target_feature is not None:
            assert trig.target_feature in ent.DOMAIN_FEATURES
