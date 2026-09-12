"""Tool implementations and the schemas handed to the Messages API.

Every tool is a plain function returning a dict. Everything that changes state
writes to SQLite, so the sidebar and the care team see the same thing.
"""

from __future__ import annotations

import json

import db
import engine

_RULES: list[dict] | None = None
_CONDITIONS: list[dict] | None = None
DEFAULT_PHASE = "post_op"


def _rules() -> list[dict]:
    global _RULES
    if _RULES is None:
        _RULES = db.load_rules()
    return _RULES


def _conditions() -> list[dict]:
    global _CONDITIONS
    if _CONDITIONS is None:
        _CONDITIONS = db.load_conditions()
    return _CONDITIONS


def _describe_patient(ctx: dict) -> str:
    who = f"{ctx['name']} ({ctx['patient_id']})"
    if ctx["phase"] == "post_op":
        return f"{who}, post-op day {ctx['post_op_day']}, {ctx['procedure']}"
    if ctx["phase"] == "pre_op":
        return f"{who}, {ctx['days_until_surgery']} days before {ctx['procedure']} on {ctx['surgery_date']}"
    return f"{who}, age {ctx['age']}, no procedure planned"


# --- the tools ------------------------------------------------------------

def get_patient_context(conv_id: str | None = None, phase: str = DEFAULT_PHASE) -> dict:
    return db.get_patient_context(phase=phase)


def assess_urgency(symptom_report: dict, conv_id: str | None = None, phase: str = DEFAULT_PHASE) -> dict:
    """The only place urgency is decided. Persists both the report and the result."""
    ctx = db.get_patient_context(phase=phase)
    assessment = engine.assess(symptom_report, ctx, _rules())
    if conv_id:
        db.insert_symptom_report(conv_id, symptom_report)
        db.insert_assessment(conv_id, assessment)
    return assessment


def explore_possibilities(symptom_report: dict, conv_id: str | None = None, phase: str = DEFAULT_PHASE) -> dict:
    """Curated things the complaint could be. Not a diagnosis, and not ranked by
    likelihood - only by how much of what the patient described each involves."""
    conditions_file = db.load_conditions_file()
    found = engine.possibilities(symptom_report, _conditions())
    return {
        "possibilities": found,
        "count": len(found),
        "disclaimer": conditions_file["disclaimer"],
        "ordering": "By how many of the things you described each one involves. This is not a ranking by likelihood.",
        "if_empty": (
            "Nothing in the curated list matches what was described. Say so plainly and point them at a clinician; "
            "do not fill the gap with possibilities of your own."
        ),
    }


def message_care_team(
    level: str,
    summary: str,
    symptoms: list | None = None,
    conv_id: str | None = None,
    phase: str = DEFAULT_PHASE,
) -> dict:
    ctx = db.get_patient_context(phase=phase)
    urgent = engine.rank(level) >= 3  # URGENT or EMERGENCY

    if phase == "post_op":
        surgeon = ctx["surgeon"]
        sent_to = (
            f"{surgeon['name']} on-call, {surgeon['practice']} ({surgeon['on_call_phone']})"
            if urgent
            else f"Ortho clinic nurse, {surgeon['practice']} ({surgeon['office_phone']})"
        )
        eta_hours = 0 if urgent else 24
    elif phase == "pre_op":
        sent_to = f"Surgical scheduling, {ctx['hospital']} ({ctx['scheduler_phone']})"
        eta_hours = 0 if urgent else 24
    else:  # no_procedure - there is no care team, so this reaches primary care
        gp = ctx["primary_care"]
        sent_to = f"{gp['clinician']}, {gp['practice']} ({gp['phone']})"
        eta_hours = 24

    body = summary
    if symptoms:
        body += "\nReported: " + json.dumps(symptoms, separators=(",", ":"))

    message_id = db.insert_care_team_message(conv_id, level, body, sent_to, eta_hours) if conv_id else 0
    return {
        "message_id": message_id,
        "sent_to": sent_to,
        "eta_hours": eta_hours,
        "status": "sent",
        "patient": _describe_patient(ctx),
    }


def schedule_checkin(
    hours_from_now: float, question: str, conv_id: str | None = None, phase: str = DEFAULT_PHASE
) -> dict:
    if not conv_id:
        return {"checkin_id": 0, "due_at": None, "status": "not_persisted"}
    checkin_id, due_at = db.insert_checkin(conv_id, hours_from_now, question)
    return {"checkin_id": checkin_id, "due_at": due_at, "question": question, "status": "scheduled"}


def log_symptom(entry: str, level: str, conv_id: str | None = None, phase: str = DEFAULT_PHASE) -> dict:
    diary_id = db.insert_diary(conv_id, entry, level) if conv_id else 0
    return {"diary_id": diary_id, "entry": entry, "level": level, "status": "logged"}


IMPLEMENTATIONS = {
    "get_patient_context": get_patient_context,
    "assess_urgency": assess_urgency,
    "explore_possibilities": explore_possibilities,
    "message_care_team": message_care_team,
    "schedule_checkin": schedule_checkin,
    "log_symptom": log_symptom,
}


def dispatch(name: str, arguments: dict, conv_id: str | None = None, phase: str = DEFAULT_PHASE) -> dict:
    fn = IMPLEMENTATIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(conv_id=conv_id, phase=phase, **(arguments or {}))
    except Exception as exc:  # a tool must never take the conversation down
        return {"error": f"{type(exc).__name__}: {exc}"}


# --- schemas --------------------------------------------------------------

SYMPTOM_ITEM = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "canonical symptom name from the vocabulary"},
        "side": {"type": ["string", "null"], "enum": ["left", "right", "both", None]},
        "location": {"type": ["string", "null"], "description": "calf, knee, thigh, shin or incision"},
        "severity": {"type": ["string", "null"], "enum": ["mild", "moderate", "severe", None]},
        "onset": {"type": ["string", "null"], "description": "when it started, in the patient's words"},
        "trend": {"type": ["string", "null"], "enum": ["better", "same", "worse", None]},
    },
    "required": ["name"],
}

TOOL_SCHEMAS = [
    {
        "name": "get_patient_context",
        "description": (
            "Return the patient's merged record: baseline history, discharge summary, medications, "
            "the surgeon's warning list, follow-up dates, and computed fields (post_op_day, "
            "on_anticoagulant, days to the next appointment). Read-only."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "assess_urgency",
        "description": (
            "Run the patient's structured symptom report through the curated post-operative red-flag "
            "rules. Returns the urgency level, the rules that matched with their rationale and source, "
            "and required actions. You MUST call this before telling the patient how urgent anything is. "
            "Never state urgency without it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symptom_report": {
                    "type": "object",
                    "properties": {
                        "symptoms": {"type": "array", "items": SYMPTOM_ITEM},
                        "qualifiers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "e.g. location:calf, one_sided, temp_reading_given",
                        },
                        "vitals": {"type": "object", "properties": {"temp_f": {"type": ["number", "null"]}}},
                        "duration_hours": {"type": ["number", "null"]},
                        "missed_meds": {"type": "boolean"},
                        "patient_words": {"type": "string", "description": "what the patient actually said"},
                    },
                    "required": ["symptoms", "qualifiers", "patient_words"],
                }
            },
            "required": ["symptom_report"],
        },
    },
    {
        "name": "explore_possibilities",
        "description": (
            "For a patient with NO procedure booked or completed: look up the curated list of things "
            "their complaint could be, with what makes each more or less likely and what the usual next "
            "step is. Call this AFTER assess_urgency, never instead of it. The list is data, not a "
            "diagnosis: present it as things to raise with a clinician, and never say which one it is. "
            "If it returns nothing, say so - do not supply possibilities of your own."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symptom_report": {
                    "type": "object",
                    "properties": {
                        "symptoms": {"type": "array", "items": SYMPTOM_ITEM},
                        "qualifiers": {"type": "array", "items": {"type": "string"}},
                        "patient_words": {"type": "string"},
                    },
                    "required": ["symptoms"],
                }
            },
            "required": ["symptom_report"],
        },
    },
    {
        "name": "message_care_team",
        "description": (
            "Send a structured message to the patient's care team. Required for every EMERGENCY, "
            "URGENT and CONTACT_TEAM result - a human sees every escalation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["EMERGENCY", "URGENT", "CONTACT_TEAM", "UNCERTAIN"]},
                "summary": {
                    "type": "string",
                    "description": "Two or three clinical sentences: what was reported, which rules matched, what was advised.",
                },
                "symptoms": {"type": "array", "items": SYMPTOM_ITEM},
            },
            "required": ["level", "summary"],
        },
    },
    {
        "name": "schedule_checkin",
        "description": "Schedule a follow-up question to the patient. Use after a MONITOR result, 12 to 24 hours out.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours_from_now": {"type": "number"},
                "question": {"type": "string", "description": "the one question to ask them then"},
            },
            "required": ["hours_from_now", "question"],
        },
    },
    {
        "name": "log_symptom",
        "description": "Add an entry to the patient's symptom diary so the care team can see the pattern over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry": {"type": "string"},
                "level": {"type": "string", "enum": ["EMERGENCY", "URGENT", "CONTACT_TEAM", "MONITOR", "UNCERTAIN"]},
            },
            "required": ["entry", "level"],
        },
    },
]
