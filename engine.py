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

# The patient-facing action for each level. The rule supplies the nuance; this
# supplies the instruction, identically every time.
LEVEL_ACTIONS = {
    "EMERGENCY": "Call 911 now. Do not drive yourself.",
    "URGENT": "Call the surgeon's on-call line now at 616-555-0199, or go to urgent care or the ER today.",
    "CONTACT_TEAM": "I am sending a message to your care team. They will call you within 24 to 48 hours.",
    "MONITOR": "This is expected recovery. Use the self-care below, and come back to me if anything on the watch list happens.",
    "UNCERTAIN": "I cannot tell from here. Please call the nurse helpline at 616-555-0142.",
}

# Location words the engine will recognise inside a symptom's `location` field.
KNOWN_SITES = ("calf", "knee", "thigh", "shin", "incision")


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
    if cond == "temp_f_ge_101":
        temp = (report.get("vitals") or {}).get("temp_f")
        return temp is not None and float(temp) >= 101.0
    # A typo in the rules file must fail loudly, not silently never fire.
    raise ValueError(f"unknown modifier condition: {cond!r}")


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


def _assessment(level: str, matched: list[dict], confidence: str, ctx: dict) -> dict:
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
        "level_action": LEVEL_ACTIONS[level],
        "confidence": confidence,
        "top_rule": matched[0]["id"] if (matched and level != "UNCERTAIN") else None,
        "matched": matched,
        "watch_for": watch_for,
        "actions_required": actions,
        "helpline": ctx.get("helpline"),
        "on_call": ctx.get("on_call"),
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

    matches: list[dict] = []
    for rule in rules:
        if rule.get("applies_to") not in ("general", ctx.get("procedure_code")):
            continue
        if not (set(rule["triggers"]) & names):
            continue
        if set(rule.get("excludes") or []) & names:
            continue

        required = rule.get("requires") or []
        confidence = "high"
        if required and not any(q in quals for q in required):
            confidence = "low"

        level = rule["level"]
        for mod in rule.get("modifiers") or []:
            conds = mod["if"] if isinstance(mod["if"], list) else [mod["if"]]
            if all(_condition(c, ctx, report, names) for c in conds):
                level = mod["level"]

        matches.append(_match_to_dict(rule, level, confidence))

    # Policy 3: nothing matched is not reassurance.
    if not matches:
        return _assessment("UNCERTAIN", [], "none", ctx)

    # Policy 4: only low-confidence matches means a qualifier is missing. The
    # agent gets one clarifying question; if it is still low, this stays
    # UNCERTAIN.
    high = [m for m in matches if m["confidence"] == "high"]
    if not high:
        return _assessment("UNCERTAIN", matches, "low", ctx)

    # Policies 1 and 2: highest rank wins, ties broken by order in the rules
    # file. sorted() is stable, so EMERGENCY rules stay ahead of everything.
    ordered = sorted(high, key=lambda m: -rank(m["level"]))
    return _assessment(ordered[0]["level"], ordered, "high", ctx)
