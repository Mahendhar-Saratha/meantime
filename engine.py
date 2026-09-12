"""Meantime rule engine.

This module decides urgency. The language model never does.

Everything here is a pure function: no I/O, no network, no LLM. Give it a
symptom report, a patient context and the rule list from data/red_flags.json
and it returns the same answer every time.

The one rule that matters most: nothing matched is NOT "you are fine". It is
UNCERTAIN, which sends the patient to the nurse helpline.
"""

from __future__ import annotations

import re

LEVEL_RANK = {
    "UNCERTAIN": 0,
    "MONITOR": 1,
    "CONTACT_TEAM": 2,
    "URGENT": 3,
    "EMERGENCY": 4,
}

# Location words the engine will recognise inside a symptom's `location` field.
KNOWN_SITES = ("calf", "knee", "thigh", "shin", "incision")

# The three points in the arc this covers. A rule states which it belongs to;
# "any" means it holds in all of them (chest pain does not care what stage of
# treatment you are at).
PHASES = ("no_procedure", "pre_op", "post_op")
DEFAULT_PHASE = "post_op"


# The patient-facing action for each level. The rule supplies the nuance; this
# supplies the instruction, identically every time. Who you call changes with
# the phase - a patient waiting for surgery calls scheduling, and a patient with
# no procedure at all has no care team to message.
LEVEL_ACTIONS = {
    "post_op": {
        "EMERGENCY": "Call 911 now. Do not drive yourself.",
        "URGENT": "Call the surgeon's on-call line now at {on_call}, or go to urgent care or the ER today.",
        "CONTACT_TEAM": "I am sending a message to your care team. They will call you within 24 to 48 hours.",
        "MONITOR": "This is expected recovery. Use the self-care below, and come back to me if anything on the watch list happens.",
        "UNCERTAIN": "I cannot tell from here. Please call the nurse helpline at {helpline}.",
    },
    "pre_op": {
        "EMERGENCY": "Call 911 now. Do not drive yourself.",
        "URGENT": "Call surgical scheduling now at {scheduler}. Your operation may need to be moved, and that is their decision to make, not something to leave until the day.",
        "CONTACT_TEAM": "I am sending a message to the surgical team. They will call you within 24 to 48 hours, well before your operation.",
        "MONITOR": "This is expected in the run-up to surgery. Use the advice below, and come back to me if anything on the watch list happens.",
        "UNCERTAIN": "I cannot tell from here. Please call the nurse helpline at {helpline}, or surgical scheduling at {scheduler}.",
    },
    "no_procedure": {
        "EMERGENCY": "Call 911 now. Do not drive yourself.",
        "URGENT": "Go to urgent care or an emergency department today.",
        "CONTACT_TEAM": "Book an appointment with your GP. I can write down what you have told me so you can take it with you.",
        "MONITOR": "This is worth keeping an eye on rather than acting on today.",
        "UNCERTAIN": "I cannot tell from here. Please call your GP practice at {primary_care} and describe it in your own words.",
    },
}


def level_action(level: str, phase: str, ctx: dict) -> str:
    """The instruction for a level, with this patient's phone numbers filled in."""
    template = LEVEL_ACTIONS.get(phase, LEVEL_ACTIONS[DEFAULT_PHASE])[level]
    return template.format(
        on_call=ctx.get("on_call") or "the on-call line",
        helpline=ctx.get("helpline") or "the nurse helpline",
        scheduler=ctx.get("scheduler_phone") or "surgical scheduling",
        primary_care=(ctx.get("primary_care") or {}).get("phone") or "your GP practice",
    )

def rank(level: str) -> int:
    return LEVEL_RANK.get(level, 0)


def derive_qualifiers(report: dict) -> set[str]:
    """Turn structured fields of the report into qualifier strings.

    This is bookkeeping, not language understanding: it reads fields the model
    already filled in (`location`, `side`, `vitals.temp_f`) so that a report
    which says location="calf" counts as the qualifier "location:calf" even if
    the model forgot to also list it. No inference about what the patient meant.
    """
    out: set[str] = set()
    for s in report.get("symptoms") or []:
        loc = (s.get("location") or "").lower()
        for word in re.split(r"[^a-z]+", loc):
            if word in KNOWN_SITES:
                out.add(f"location:{word}")
        side = (s.get("side") or "").lower()
        if side in ("left", "right"):
            out.add("one_sided")
        elif side == "both":
            out.add("both_sides")
    if (report.get("vitals") or {}).get("temp_f") is not None:
        out.add("temp_reading_given")
    return out


def _condition(cond: str, ctx: dict, report: dict, names: set[str]) -> bool:
    """Evaluate one modifier condition from red_flags.json."""
    if cond == "on_anticoagulant":
        return bool(ctx.get("on_anticoagulant"))
    if cond == "on_opioid":
        return bool(ctx.get("on_opioid"))
    if cond == "post_op_day_gt_3":
        return (ctx.get("post_op_day") or 0) > 3
    if cond == "post_op_day_le_3":
        return (ctx.get("post_op_day") or 0) <= 3
    if cond.startswith("has_symptom:"):
        return cond.split(":", 1)[1] in names
    if cond == "severity_severe":
        return any((s.get("severity") == "severe") for s in report.get("symptoms") or [])
    if cond == "duration_gt_24h":
        return (report.get("duration_hours") or 0) > 24
    if cond == "symptom_recurring":
        # The patient has raised one of these before. Something that was worth a
        # call yesterday and is still here today is not the same as a first report.
        return bool(set(ctx.get("history_symptoms") or []) & names)
    if cond == "temp_f_ge_101":
        temp = (report.get("vitals") or {}).get("temp_f")
        return temp is not None and float(temp) >= 101.0
    # A typo in the rules file must fail loudly, not silently never fire.
    raise ValueError(f"unknown modifier condition: {cond!r}")


def applies_in_phase(rule: dict, phase: str) -> bool:
    """Does this rule hold at this point in the patient's arc?"""
    declared = rule.get("phase", DEFAULT_PHASE)
    if isinstance(declared, str):
        declared = [declared]
    return "any" in declared or phase in declared


def _match_to_dict(rule: dict, level: str, confidence: str) -> dict:
    return {
        "id": rule["id"],
        "level": level,
        "base_level": rule["level"],
        "confidence": confidence,
        "rationale": rule["rationale"],
        "action": rule["action"],
        "watch_for": rule.get("watch_for", []),
        "source": rule["source"],
        "source_url": rule.get("source_url"),
    }


def _assessment(level: str, matched: list[dict], confidence: str, ctx: dict, trace: dict | None = None) -> dict:
    phase = ctx.get("phase") or DEFAULT_PHASE

    actions: list[str] = []
    if rank(level) >= 2:
        actions.append("message_care_team")
    if level == "MONITOR":
        actions.append("schedule_checkin")

    watch_for: list[str] = []
    if level == "MONITOR" and matched:
        watch_for = matched[0].get("watch_for", [])

    return {
        "level": level,
        "phase": phase,
        "level_action": level_action(level, phase, ctx),
        "confidence": confidence,
        "top_rule": matched[0]["id"] if (matched and level != "UNCERTAIN") else None,
        "matched": matched,
        "watch_for": watch_for,
        "actions_required": actions,
        "helpline": ctx.get("helpline"),
        "on_call": ctx.get("on_call"),
        "trace": trace or {},
    }


def assess(report: dict, ctx: dict, rules: list[dict]) -> dict:
    """Match a symptom report against the rules and apply the decision policy.

    Returns a plain dict so it can be handed straight back to the model as a
    tool result and straight into SQLite.
    """
    report = report or {}
    symptoms = report.get("symptoms") or []
    names = {s.get("name") for s in symptoms if s.get("name")}
    quals = set(report.get("qualifiers") or []) | derive_qualifiers(report)

    phase = ctx.get("phase") or DEFAULT_PHASE

    # The narrowing is recorded as it happens, so the interface can show which
    # rules were in play for THIS message and which were ruled out and why.
    # Without this the filtering is real but invisible, and "the rules are
    # dynamic" is a claim rather than something you can watch.
    trace: dict = {
        "library": len(rules),
        "procedure": 0,
        "phase": 0,
        "symptoms": sorted(names),
        "triggered": [],
        "excluded": [],
        "low_confidence": [],
        "upgraded": [],
        "chosen": None,
    }

    matches: list[dict] = []
    for rule in rules:
        if rule.get("applies_to") not in ("general", ctx.get("procedure_code")):
            continue
        trace["procedure"] += 1
        if not applies_in_phase(rule, phase):
            continue
        trace["phase"] += 1

        hit = set(rule["triggers"]) & names
        if not hit:
            continue
        trace["triggered"].append(rule["id"])

        blocked = set(rule.get("excludes") or []) & names
        if blocked:
            trace["excluded"].append(
                {"id": rule["id"], "level": rule["level"], "by": sorted(blocked), "rationale": rule["rationale"]}
            )
            continue

        required = rule.get("requires") or []
        confidence = "high"
        if required and not any(q in quals for q in required):
            confidence = "low"
            trace["low_confidence"].append({"id": rule["id"], "needs": required})

        level = rule["level"]
        for mod in rule.get("modifiers") or []:
            conds = mod["if"] if isinstance(mod["if"], list) else [mod["if"]]
            if all(_condition(c, ctx, report, names) for c in conds):
                if mod["level"] != level:
                    trace["upgraded"].append(
                        {"id": rule["id"], "from": level, "to": mod["level"], "because": conds}
                    )
                level = mod["level"]

        matches.append(_match_to_dict(rule, level, confidence))

    trace["surviving"] = [m["id"] for m in matches]

    # Policy 3: nothing matched is not reassurance.
    if not matches:
        return _assessment("UNCERTAIN", [], "none", ctx, trace)

    # Policy 4: only low-confidence matches means a qualifier is missing. The
    # agent gets one clarifying question; if it is still low, this stays
    # UNCERTAIN.
    high = [m for m in matches if m["confidence"] == "high"]
    if not high:
        return _assessment("UNCERTAIN", matches, "low", ctx, trace)

    # Policies 1 and 2: highest rank wins, ties broken by order in the rules
    # file. sorted() is stable, so EMERGENCY rules stay ahead of everything.
    ordered = sorted(high, key=lambda m: -rank(m["level"]))
    trace["chosen"] = ordered[0]["id"]
    return _assessment(ordered[0]["level"], ordered, "high", ctx, trace)


def rules_for_phase(rules: list[dict], phase: str, procedure_code: str | None) -> list[dict]:
    """Every rule that could fire right now. Used by the dashboard."""
    return [
        r
        for r in rules
        if r.get("applies_to") in ("general", procedure_code) and applies_in_phase(r, phase)
    ]


def possibilities(report: dict, conditions: list[dict], limit: int = 4) -> list[dict]:
    """Curated things a knee complaint could be, for a patient with no procedure.

    This is deliberately NOT a diagnosis and carries no probability. A condition
    is listed when it involves something the patient described; the ordering is
    by how much of what they described it involves, nothing more. The
    more_likely_if / less_likely_if lines are handed to the patient as the
    questions a clinician would use to tell these apart - the software never
    evaluates them, because it cannot.
    """
    names = {s.get("name") for s in report.get("symptoms") or [] if s.get("name")}
    if not names:
        return []

    scored: list[dict] = []
    for condition in conditions:
        overlap = set(condition["triggers"]) & names
        if not overlap:
            continue
        scored.append(
            {
                "id": condition["id"],
                "name": condition["name"],
                "plain": condition["plain"],
                "matched_symptoms": sorted(overlap),
                "match_count": len(overlap),
                "more_likely_if": condition["more_likely_if"],
                "less_likely_if": condition["less_likely_if"],
                "next_step": condition["next_step"],
                "source": condition["source"],
                "source_url": condition.get("source_url"),
            }
        )

    # sorted() is stable, so equal match counts keep the order of the file.
    scored.sort(key=lambda c: -c["match_count"])
    return scored[:limit]
