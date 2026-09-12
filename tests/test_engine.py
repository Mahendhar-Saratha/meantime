"""The eight cases from the build plan, section 8.4.

These run against the real data/red_flags.json - no mocks, no fixtures copied
by hand. If a rule is edited, these tests are what catches it.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import assess  # noqa: E402

RULES = json.load(
    open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "red_flags.json"),
        encoding="utf-8",
    )
)["rules"]

# Robert on post-op day 4: on apixaban, on oxycodone, knee replacement.
CTX = {
    "procedure_code": "tka",
    "post_op_day": 4,
    "on_anticoagulant": True,
    "on_opioid": True,
    "helpline": "616-555-0142",
    "on_call": "616-555-0199",
}


def sx(name, **kw):
    """A symptom with every optional field defaulted to null, never guessed."""
    base = {"name": name, "side": None, "location": None, "severity": None, "onset": None, "trend": None}
    base.update(kw)
    return base


def report(symptoms, qualifiers=None, temp_f=None, duration_hours=None, words=""):
    return {
        "symptoms": symptoms,
        "qualifiers": qualifiers or [],
        "vitals": {"temp_f": temp_f},
        "duration_hours": duration_hours,
        "missed_meds": False,
        "patient_words": words,
    }


def ids(result):
    return [m["id"] for m in result["matched"]]


def test_1_calf_beats_expected_swelling():
    """M1 says leg swelling is normal. The calf qualifier must stop it firing."""
    r = assess(
        report(
            [sx("calf_swelling"), sx("calf_pain")],
            qualifiers=["location:calf", "one_sided"],
            words="my right calf is really sore and kind of swollen",
        ),
        CTX,
        RULES,
    )
    assert r["level"] == "URGENT"
    assert r["top_rule"] == "K1"
    assert "M1" not in ids(r)
    assert "message_care_team" in r["actions_required"]


def test_2_chest_symptoms_are_emergency():
    r = assess(report([sx("chest_tightness"), sx("shortness_of_breath")]), CTX, RULES)
    assert r["level"] == "EMERGENCY"
    assert r["top_rule"] == "G1"
    assert "G2" in ids(r)


def test_3_itching_and_bruising_is_monitor_with_watchlist():
    r = assess(report([sx("incision_itching"), sx("bruising")]), CTX, RULES)
    assert r["level"] == "MONITOR"
    assert r["top_rule"] in ("M2", "M4")
    assert len(r["watch_for"]) == 3
    assert r["actions_required"] == ["schedule_checkin"]


def test_4_nothing_matched_is_uncertain_not_fine():
    r = assess(report([], words="I just feel kind of off today"), CTX, RULES)
    assert r["level"] == "UNCERTAIN"
    assert r["confidence"] == "none"
    assert r["matched"] == []
    assert "616-555-0142" in r["level_action"]


def test_5_missing_qualifier_is_low_confidence_not_an_answer():
    r = assess(report([sx("leg_swelling_one_sided")]), CTX, RULES)
    assert r["level"] == "UNCERTAIN"
    assert r["confidence"] == "low"
    assert ids(r) == ["K1"]  # the agent now has something to ask about


def test_6_bleeding_on_a_blood_thinner_escalates_to_emergency():
    r = assess(
        report([sx("bleeding_soaking_dressing"), sx("bleeding_not_stopping")], qualifiers=["pressure_applied_10min"]),
        CTX,
        RULES,
    )
    assert r["level"] == "EMERGENCY"
    assert r["top_rule"] in ("G9", "K5")
    assert {"G9", "K5"} <= set(ids(r))


def test_7_temperature_over_101_upgrades_to_urgent():
    r = assess(
        report(
            [sx("fever"), sx("wound_redness_spreading")],
            qualifiers=["temp_reading_given"],
            temp_f=101.8,
        ),
        CTX,
        RULES,
    )
    assert r["level"] == "URGENT"
    assert r["top_rule"] == "K2"
    assert "K4" in ids(r)


def test_8_clear_drainage_after_day_3_is_no_longer_expected():
    r = assess(report([sx("wound_drainage_clear_small")]), CTX, RULES)
    assert r["level"] == "CONTACT_TEAM"
    assert r["top_rule"] == "M5"
    assert "message_care_team" in r["actions_required"]


# --- Extra guards on the behaviour the demo depends on -------------------


def test_derived_qualifier_rescues_a_report_without_an_explicit_qualifier():
    """Model fills location/side but forgets the qualifiers list: still URGENT."""
    r = assess(report([sx("calf_pain", side="right", location="right calf")]), CTX, RULES)
    assert r["level"] == "URGENT"
    assert r["top_rule"] == "K1"


def test_emergency_outranks_a_monitor_match_in_the_same_report():
    r = assess(report([sx("bruising"), sx("chest_pain")]), CTX, RULES)
    assert r["level"] == "EMERGENCY"


def test_same_report_on_day_2_keeps_drainage_expected():
    day2 = dict(CTX, post_op_day=2)
    r = assess(report([sx("wound_drainage_clear_small")]), day2, RULES)
    assert r["level"] == "MONITOR"
    assert len(r["watch_for"]) == 3


def test_every_modifier_condition_in_the_rules_file_is_implemented():
    """A typo in red_flags.json must not silently become a rule that never fires."""
    for rule in RULES:
        for mod in rule.get("modifiers") or []:
            conds = mod["if"] if isinstance(mod["if"], list) else [mod["if"]]
            for cond in conds:
                from engine import _condition

                _condition(cond, CTX, report([]), set())  # raises on unknown


def test_monitor_rules_all_carry_three_watch_items():
    for rule in RULES:
        if rule["level"] == "MONITOR":
            assert len(rule["watch_for"]) == 3, rule["id"]


@pytest.mark.parametrize("level", ["EMERGENCY", "URGENT", "CONTACT_TEAM"])
def test_every_escalation_reaches_a_human(level):
    """Policy 6: nothing above MONITOR resolves without messaging the team."""
    trigger = {"EMERGENCY": "chest_pain", "URGENT": "wound_opening", "CONTACT_TEAM": "constipation"}[level]
    r = assess(report([sx(trigger)]), CTX, RULES)
    assert r["level"] == level
    assert "message_care_team" in r["actions_required"]
