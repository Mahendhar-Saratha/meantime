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


# --- phases -------------------------------------------------------------

import engine as _engine  # noqa: E402

CONDITIONS = json.load(
    open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "conditions.json"),
        encoding="utf-8",
    )
)["conditions"]

PRE_OP_CTX = dict(
    CTX, phase="pre_op", on_anticoagulant=False, on_opioid=False, post_op_day=None, scheduler_phone="616-555-0150"
)
NO_PROC_CTX = {
    "phase": "no_procedure",
    "procedure_code": None,
    "helpline": "616-555-0142",
    "primary_care": {"phone": "616-555-0120"},
}


def test_emergencies_fire_in_every_phase():
    """Chest pain does not care what stage of treatment you are at."""
    for ctx in (dict(CTX, phase="post_op"), PRE_OP_CTX, NO_PROC_CTX):
        r = assess(report([sx("chest_pain")]), ctx, RULES)
        assert r["level"] == "EMERGENCY", ctx["phase"]
        assert r["top_rule"] == "G1"


def test_post_op_rules_do_not_fire_before_surgery():
    """K1 is about a leg that has been operated on. It must not fire pre-op."""
    r = assess(report([sx("calf_pain")], qualifiers=["location:calf"]), PRE_OP_CTX, RULES)
    assert "K1" not in ids(r)


def test_infection_before_surgery_is_urgent():
    r = assess(report([sx("sore_throat"), sx("fever")], temp_f=100.4), PRE_OP_CTX, RULES)
    assert r["level"] == "URGENT"
    assert r["top_rule"] == "P1"
    assert "message_care_team" in r["actions_required"]


def test_breaking_the_fast_is_urgent_not_embarrassing():
    r = assess(report([sx("ate_after_cutoff")]), PRE_OP_CTX, RULES)
    assert r["level"] == "URGENT"
    assert r["top_rule"] == "P5"


def test_the_same_symptom_answers_differently_by_phase():
    """Aching, stiff knee: expected while waiting, expected after surgery, and
    worth a GP visit when nobody has ever assessed it."""
    r = report([sx("knee_pain"), sx("stiffness")])
    assert assess(r, PRE_OP_CTX, RULES)["top_rule"] == "P10"
    assert assess(r, dict(CTX, phase="post_op"), RULES)["top_rule"] == "M7"
    assert assess(r, NO_PROC_CTX, RULES)["level"] == "CONTACT_TEAM"


def test_hot_swollen_knee_with_fever_escalates_without_a_procedure():
    mild = assess(report([sx("knee_warmth"), sx("knee_swelling")]), NO_PROC_CTX, RULES)
    assert mild["level"] == "CONTACT_TEAM"
    febrile = assess(report([sx("knee_warmth"), sx("knee_swelling"), sx("fever")]), NO_PROC_CTX, RULES)
    assert febrile["level"] == "URGENT"


def test_level_action_names_the_right_contact_for_the_phase():
    assert "616-555-0199" in _engine.level_action("URGENT", "post_op", CTX)
    assert "616-555-0150" in _engine.level_action("URGENT", "pre_op", PRE_OP_CTX)
    assert "urgent care" in _engine.level_action("URGENT", "no_procedure", NO_PROC_CTX)
    assert "616-555-0120" in _engine.level_action("UNCERTAIN", "no_procedure", NO_PROC_CTX)


# --- possibilities ------------------------------------------------------


def test_possibilities_are_ordered_by_overlap_not_by_likelihood():
    found = _engine.possibilities(report([sx("knee_pain"), sx("stiffness"), sx("pain_on_stairs")]), CONDITIONS)
    assert found[0]["id"] == "C1"
    assert found[0]["match_count"] == 3
    assert [c["match_count"] for c in found] == sorted((c["match_count"] for c in found), reverse=True)


def test_possibilities_returns_nothing_for_an_empty_report():
    assert _engine.possibilities(report([]), CONDITIONS) == []


def test_possibilities_never_claims_a_probability():
    """No field in the output may look like a likelihood the software computed."""
    found = _engine.possibilities(report([sx("knee_pain")]), CONDITIONS)
    assert found
    for candidate in found:
        assert not {"probability", "likelihood", "confidence", "score"} & set(candidate)
        assert candidate["more_likely_if"] and candidate["less_likely_if"]
        assert candidate["next_step"] and candidate["source"]


def test_every_rule_declares_a_phase_the_engine_knows():
    for rule in RULES:
        declared = rule["phase"]
        declared = [declared] if isinstance(declared, str) else declared
        for phase in declared:
            assert phase == "any" or phase in _engine.PHASES, (rule["id"], phase)


# --- the "always assess" invariant is enforced in code, not just the prompt ---


def test_needs_assessment_detects_a_turn_with_no_verdict():
    from agent import needs_assessment

    assert needs_assessment([])
    assert needs_assessment([{"tool": "log_symptom", "output": {}}])
    assert not needs_assessment([{"tool": "assess_urgency", "output": {"level": "MONITOR"}}])


def test_needs_lookup_only_when_the_rules_came_back_uncertain():
    from agent import needs_lookup

    uncertain = [{"tool": "assess_urgency", "output": {"level": "UNCERTAIN", "matched": []}}]
    assert needs_lookup(uncertain)
    assert not needs_lookup(uncertain + [{"tool": "lookup_guidance", "output": {}}])
    assert not needs_lookup([{"tool": "assess_urgency", "output": {"level": "URGENT", "matched": []}}])
    assert not needs_lookup([])


def test_recurrence_escalates_pain_that_was_already_reported():
    """The alert-system behaviour: same complaint, second time, moves up."""
    first = assess(report([sx("pain_uncontrolled")]), CTX, RULES)
    assert first["level"] == "CONTACT_TEAM"
    again = assess(report([sx("pain_uncontrolled")]), dict(CTX, history_symptoms=["pain_uncontrolled"]), RULES)
    assert again["level"] == "URGENT"
    assert again["top_rule"] == "K8"


# --- the filter trace: what makes the narrowing visible ------------------


def test_trace_records_every_narrowing_step():
    """'my knee is swollen and my calf hurts' - 44 -> 31 -> 2 -> 1."""
    r = assess(
        report([sx("knee_swelling"), sx("calf_pain", side="right", location="calf")]), CTX, RULES
    )
    t = r["trace"]
    assert t["library"] == len(RULES)
    assert t["procedure"] == len(RULES)  # tka patient: general + tka both apply
    assert t["phase"] == 31
    assert t["triggered"] == ["K1", "M1"]
    assert t["surviving"] == ["K1"]
    assert t["chosen"] == "K1"


def test_trace_names_the_rule_that_was_ruled_out_and_what_ruled_it_out():
    """The M1-vs-K1 moment is the whole demo; the trace has to explain it."""
    r = assess(
        report([sx("knee_swelling"), sx("calf_pain", side="right", location="calf")]), CTX, RULES
    )
    dropped = r["trace"]["excluded"]
    assert [d["id"] for d in dropped] == ["M1"]
    assert dropped[0]["by"] == ["calf_pain"]
    assert dropped[0]["rationale"]


def test_trace_records_an_upgrade_with_its_reason():
    r = assess(report([sx("wound_drainage_clear_small")]), CTX, RULES)
    assert r["level"] == "CONTACT_TEAM"
    upgrade = r["trace"]["upgraded"][0]
    assert upgrade["id"] == "M5"
    assert upgrade["from"] == "MONITOR" and upgrade["to"] == "CONTACT_TEAM"
    assert upgrade["because"] == ["post_op_day_gt_3"]


def test_trace_on_nothing_matched_shows_zero_triggered():
    t = assess(report([]), CTX, RULES)["trace"]
    assert t["triggered"] == [] and t["surviving"] == [] and t["chosen"] is None
    assert t["phase"] == 31  # the rules were there; none of them fit


def test_trace_narrows_differently_per_phase():
    r = report([sx("knee_pain"), sx("stiffness")])
    assert assess(r, PRE_OP_CTX, RULES)["trace"]["phase"] == 19
    assert assess(r, dict(CTX, phase="post_op"), RULES)["trace"]["phase"] == 31
    assert assess(r, NO_PROC_CTX, RULES)["trace"]["phase"] == 12
