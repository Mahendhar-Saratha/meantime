"""SQLite storage and the merged patient context.

Two JSON files go in (the record before surgery, and the discharge summary
appended after it); one context dict comes out, with the fields that change the
answer computed rather than typed: post_op_day, on_anticoagulant, days to the
next appointment.

DEMO_TODAY pins "today" so the demo behaves identically whenever it is run.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.path.join(ROOT, "meantime.db")
PATIENT_ID = "P-1001"

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY, name TEXT, dob TEXT, sex TEXT, json_baseline TEXT);
CREATE TABLE IF NOT EXISTS discharge_records (
    encounter_id TEXT PRIMARY KEY, patient_id TEXT, procedure_code TEXT,
    surgery_date TEXT, json_discharge TEXT);
CREATE TABLE IF NOT EXISTS scheduled_procedures (
    booking_id TEXT PRIMARY KEY, patient_id TEXT, procedure_code TEXT,
    surgery_date TEXT, json_booking TEXT);
CREATE TABLE IF NOT EXISTS prior_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, occurred_at TEXT, phase TEXT,
    entry TEXT, level TEXT, symptoms TEXT, rules TEXT);
CREATE TABLE IF NOT EXISTS conversations (
    conv_id TEXT PRIMARY KEY, patient_id TEXT, started_at TEXT);
CREATE TABLE IF NOT EXISTS symptom_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT, created_at TEXT, json_report TEXT);
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT, created_at TEXT, level TEXT,
    matched_rule_ids TEXT, confidence TEXT, json_full TEXT);
CREATE TABLE IF NOT EXISTS care_team_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT, created_at TEXT, level TEXT,
    summary TEXT, sent_to TEXT, eta_hours INTEGER, status TEXT DEFAULT 'sent');
CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT, created_at TEXT, due_at TEXT,
    question TEXT, status TEXT DEFAULT 'scheduled');
CREATE TABLE IF NOT EXISTS symptom_diary (
    id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, conv_id TEXT, created_at TEXT,
    entry TEXT, level TEXT);
"""

CONVERSATION_TABLES = (
    "conversations",
    "symptom_reports",
    "assessments",
    "care_team_messages",
    "checkins",
    "symptom_diary",
)


# --- time -----------------------------------------------------------------

def demo_today() -> date:
    """The pinned demo date. Only drives post_op_day and appointment maths -
    wall-clock timestamps on messages and check-ins stay real."""
    return date.fromisoformat(os.environ.get("DEMO_TODAY") or "2026-09-12")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- connection and schema ------------------------------------------------

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def seed() -> None:
    """Load both JSON records into SQLite. Safe to call on every startup."""
    init_db()
    with open(os.path.join(DATA_DIR, "patient_baseline.json"), encoding="utf-8") as fh:
        baseline = json.load(fh)
    with open(os.path.join(DATA_DIR, "discharge_summary.json"), encoding="utf-8") as fh:
        discharge = json.load(fh)
    with open(os.path.join(DATA_DIR, "scheduled_procedure.json"), encoding="utf-8") as fh:
        booking = json.load(fh)
    with open(os.path.join(DATA_DIR, "prior_contacts.json"), encoding="utf-8") as fh:
        prior = json.load(fh)

    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO patients VALUES (?,?,?,?,?)",
            (baseline["patient_id"], baseline["name"], baseline["dob"], baseline["sex"], json.dumps(baseline)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO discharge_records VALUES (?,?,?,?,?)",
            (
                discharge["encounter_id"],
                discharge["patient_id"],
                discharge["procedure_code"],
                discharge["surgery_date"],
                json.dumps(discharge),
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO scheduled_procedures VALUES (?,?,?,?,?)",
            (
                booking["booking_id"],
                booking["patient_id"],
                booking["procedure_code"],
                booking["surgery_date"],
                json.dumps(booking),
            ),
        )
        # Prior contacts are the patient's history, not session state, so they
        # are reseeded from scratch rather than accumulated.
        conn.execute("DELETE FROM prior_contacts WHERE patient_id=?", (prior["patient_id"],))
        today = demo_today()
        for item in prior["entries"]:
            conn.execute(
                "INSERT INTO prior_contacts (patient_id, occurred_at, phase, entry, level, symptoms, rules)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    prior["patient_id"],
                    (today - timedelta(days=item["days_ago"])).isoformat(),
                    item["phase"],
                    item["entry"],
                    item["level"],
                    ",".join(item["symptoms"]),
                    ",".join(item["rules"]),
                ),
            )


def load_rules() -> list[dict]:
    with open(os.path.join(DATA_DIR, "red_flags.json"), encoding="utf-8") as fh:
        return json.load(fh)["rules"]


def load_rules_file() -> dict:
    with open(os.path.join(DATA_DIR, "red_flags.json"), encoding="utf-8") as fh:
        return json.load(fh)


def load_conditions() -> list[dict]:
    """The curated possibilities list used before any procedure."""
    with open(os.path.join(DATA_DIR, "conditions.json"), encoding="utf-8") as fh:
        return json.load(fh)["conditions"]


def load_conditions_file() -> dict:
    with open(os.path.join(DATA_DIR, "conditions.json"), encoding="utf-8") as fh:
        return json.load(fh)


def patient_history(patient_id: str = PATIENT_ID, phase: str | None = None) -> list[dict]:
    """What this patient has told Meantime before today, oldest first."""
    with connect() as conn:
        if phase:
            rows = conn.execute(
                "SELECT * FROM prior_contacts WHERE patient_id=? AND phase=? ORDER BY occurred_at",
                (patient_id, phase),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM prior_contacts WHERE patient_id=? ORDER BY occurred_at", (patient_id,)
            ).fetchall()
    today = demo_today()
    out = []
    for row in rows:
        occurred = date.fromisoformat(row["occurred_at"])
        days = (today - occurred).days
        out.append(
            {
                "date": row["occurred_at"],
                "days_ago": days,
                "when": "today" if days == 0 else ("yesterday" if days == 1 else f"{days} days ago"),
                "phase": row["phase"],
                "entry": row["entry"],
                "level": row["level"],
                "symptoms": [s for s in (row["symptoms"] or "").split(",") if s],
                "rules": [r for r in (row["rules"] or "").split(",") if r],
            }
        )
    return out


# --- the merged context ---------------------------------------------------

def _years_since(iso_date: str, today: date) -> int:
    d = date.fromisoformat(iso_date)
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def _load_records(patient_id: str) -> tuple[dict, dict, dict]:
    with connect() as conn:
        prow = conn.execute("SELECT json_baseline FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
        drow = conn.execute(
            "SELECT json_discharge FROM discharge_records WHERE patient_id=? ORDER BY surgery_date DESC LIMIT 1",
            (patient_id,),
        ).fetchone()
        brow = conn.execute(
            "SELECT json_booking FROM scheduled_procedures WHERE patient_id=? ORDER BY surgery_date DESC LIMIT 1",
            (patient_id,),
        ).fetchone()
    if not prow or not drow or not brow:
        raise RuntimeError("Database not seeded. Run db.seed() first.")
    return json.loads(prow["json_baseline"]), json.loads(drow["json_discharge"]), json.loads(brow["json_booking"])


def _base_context(baseline: dict, today: date, phase: str) -> dict:
    """The parts of the record that are true in every phase."""
    return {
        "patient_id": baseline["patient_id"],
        "phase": phase,
        "name": baseline["name"],
        "age": _years_since(baseline["dob"], today),
        "sex": baseline["sex"],
        "phone": baseline["phone"],
        "emergency_contact": baseline["emergency_contact"],
        "primary_care": baseline["primary_care"],
        "conditions": baseline["conditions"],
        "home_medications": baseline["home_medications"],
        "allergies": baseline["allergies"],
        "today": today.isoformat(),
        "helpline": baseline["nurse_helpline"],
        "history": [],
        "history_symptoms": [],
        # defaults the phase blocks below override where they apply
        "procedure_code": None,
        "on_anticoagulant": False,
        "on_opioid": False,
        "anticoagulant_name": None,
        "on_call": None,
        "scheduler_phone": None,
    }


def get_patient_context(patient_id: str = PATIENT_ID, phase: str = "post_op") -> dict:
    """The record the agent reasons over, for one of the three phases of care.

    `no_procedure` is the baseline alone - nothing has been booked. `pre_op`
    adds the booking and its preparation instructions. `post_op` adds the
    discharge summary. Same patient, three points on the same timeline.
    """
    baseline, discharge, booking = _load_records(patient_id)
    history = patient_history(patient_id, phase)
    history_symptoms = sorted({s for h in history for s in h["symptoms"]})

    if phase == "no_procedure":
        today = demo_today()
        ctx = _base_context(baseline, today, phase)
        ctx["history"], ctx["history_symptoms"] = history, history_symptoms
        ctx.update(
            {
                "procedure": None,
                "situation": "No procedure planned or booked. This is the record as it stands before any treatment.",
            }
        )
        return ctx

    if phase == "pre_op":
        surgery_date = date.fromisoformat(booking["surgery_date"])
        # Pinned: stand this many days before the operation, so the countdown
        # is identical every time the demo is run.
        today = surgery_date - timedelta(days=booking["demo_days_until_surgery"])
        ctx = _base_context(baseline, today, phase)
        ctx["history"], ctx["history_symptoms"] = history, history_symptoms

        upcoming = sorted(
            (a for a in booking["pre_op_appointments"] if date.fromisoformat(a["date"]) >= today),
            key=lambda a: a["date"],
        )
        ctx.update(
            {
                "booking_id": booking["booking_id"],
                "procedure": booking["procedure"],
                "procedure_code": booking["procedure_code"],
                "laterality": booking["laterality"],
                "surgery_date": booking["surgery_date"],
                "arrival_time": booking["arrival_time"],
                "hospital": booking["hospital"],
                "surgeon": booking["surgeon"],
                "scheduler_phone": booking["scheduler"]["phone"],
                "preparation": booking["preparation"],
                "warning_list": booking["warning_list"],
                "diagnosis_codes": booking.get("diagnosis_codes", []),
                "pre_op_appointments": booking["pre_op_appointments"],
                "days_until_surgery": (surgery_date - today).days,
                "next_followup": (
                    dict(upcoming[0], days_away=(date.fromisoformat(upcoming[0]["date"]) - today).days)
                    if upcoming
                    else None
                ),
                "on_call": booking["surgeon"]["on_call_phone"],
            }
        )
        return ctx

    # post_op
    today = demo_today()
    ctx = _base_context(baseline, today, phase)
    ctx["history"], ctx["history_symptoms"] = history, history_symptoms
    meds = discharge["discharge_medications"]
    surgery_date = date.fromisoformat(discharge["surgery_date"])

    # Next appointment. Physical therapy is separated out because it is therapy,
    # not a clinician who would look at a symptom - the sidebar counts down to
    # the next clinical review.
    upcoming = sorted(
        (f for f in discharge["follow_up"] if date.fromisoformat(f["date"]) > today),
        key=lambda f: f["date"],
    )

    def _with_days(f):
        return dict(f, days_away=(date.fromisoformat(f["date"]) - today).days)

    next_followup = _with_days(upcoming[0]) if upcoming else None
    clinical = [f for f in upcoming if "therapy" not in f["type"].lower()]
    next_clinical = _with_days(clinical[0]) if clinical else None

    ctx.update(
        {
            "encounter_id": discharge["encounter_id"],
            "procedure": discharge["procedure"],
            "procedure_code": discharge["procedure_code"],
            "laterality": discharge["laterality"],
            "surgery_date": discharge["surgery_date"],
            "discharge_date": discharge["discharge_date"],
            "surgeon": discharge["surgeon"],
            "discharge_diagnosis": discharge["discharge_diagnosis"],
            "discharge_medications": meds,
            "instructions": discharge["instructions"],
            "warning_list": discharge["warning_list"],
            "diagnosis_codes": discharge.get("diagnosis_codes", []),
            "follow_up": discharge["follow_up"],
            "post_op_day": (today - surgery_date).days,
            "on_anticoagulant": any(m.get("class") == "anticoagulant" for m in meds),
            "on_opioid": any(m.get("class") == "opioid" for m in meds),
            "anticoagulant_name": next((m["name"] for m in meds if m.get("class") == "anticoagulant"), None),
            "next_followup": next_followup,
            "next_clinical_followup": next_clinical,
            "days_to_next_appointment": (next_clinical or next_followup or {}).get("days_away"),
            "on_call": discharge["surgeon"]["on_call_phone"],
            "scheduler_phone": discharge["surgeon"]["office_phone"],
        }
    )
    return ctx


# --- writes ---------------------------------------------------------------

def new_conversation(patient_id: str = PATIENT_ID) -> str:
    conv_id = "C-" + uuid.uuid4().hex[:8]
    with connect() as conn:
        conn.execute("INSERT INTO conversations VALUES (?,?,?)", (conv_id, patient_id, _now()))
    return conv_id


def insert_symptom_report(conv_id: str, report: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO symptom_reports (conv_id, created_at, json_report) VALUES (?,?,?)",
            (conv_id, _now(), json.dumps(report)),
        )
        return cur.lastrowid


def insert_assessment(conv_id: str, assessment: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO assessments (conv_id, created_at, level, matched_rule_ids, confidence, json_full)"
            " VALUES (?,?,?,?,?,?)",
            (
                conv_id,
                _now(),
                assessment["level"],
                ",".join(m["id"] for m in assessment["matched"]),
                assessment["confidence"],
                json.dumps(assessment),
            ),
        )
        return cur.lastrowid


def insert_care_team_message(conv_id: str, level: str, summary: str, sent_to: str, eta_hours: int) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO care_team_messages (conv_id, created_at, level, summary, sent_to, eta_hours)"
            " VALUES (?,?,?,?,?,?)",
            (conv_id, _now(), level, summary, sent_to, eta_hours),
        )
        return cur.lastrowid


def insert_checkin(conv_id: str, hours_from_now: float, question: str) -> tuple[int, str]:
    due = (datetime.now() + timedelta(hours=hours_from_now)).isoformat(timespec="seconds")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO checkins (conv_id, created_at, due_at, question) VALUES (?,?,?,?)",
            (conv_id, _now(), due, question),
        )
        return cur.lastrowid, due


def insert_diary(conv_id: str, entry: str, level: str, patient_id: str = PATIENT_ID) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO symptom_diary (patient_id, conv_id, created_at, entry, level) VALUES (?,?,?,?,?)",
            (patient_id, conv_id, _now(), entry, level),
        )
        return cur.lastrowid


# --- reads ----------------------------------------------------------------

def _rows(table: str, conv_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(f"SELECT * FROM {table} WHERE conv_id=? ORDER BY id", (conv_id,)).fetchall()
    return [dict(r) for r in rows]


def list_assessments_for_conv(conv_id: str) -> list[dict]:
    return _rows("assessments", conv_id)


def list_messages_for_conv(conv_id: str) -> list[dict]:
    return _rows("care_team_messages", conv_id)


def list_checkins_for_conv(conv_id: str) -> list[dict]:
    return _rows("checkins", conv_id)


def list_diary_for_conv(conv_id: str) -> list[dict]:
    return _rows("symptom_diary", conv_id)


def reset_demo() -> None:
    """Clear everything a conversation produced. Keeps the patient and the
    discharge record, so the next demo path starts from the same day 4."""
    init_db()
    with connect() as conn:
        for table in CONVERSATION_TABLES:
            conn.execute(f"DELETE FROM {table}")


if __name__ == "__main__":
    seed()
    for ph in ("no_procedure", "pre_op", "post_op"):
        c = get_patient_context(phase=ph)
        line = f"{ph:<14} today {c['today']}  {c.get('procedure') or 'no procedure planned'}"
        if ph == "pre_op":
            line += f"  -> surgery in {c['days_until_surgery']} days"
        if ph == "post_op":
            line += f"  -> post-op day {c['post_op_day']}"
        print(line)
    print()
    ctx = get_patient_context()
    print(f"{ctx['name']}, {ctx['age']}  |  {ctx['procedure']}  |  today {ctx['today']}")
    print(f"post_op_day: {ctx['post_op_day']}")
    print(f"on_anticoagulant: {ctx['on_anticoagulant']} ({ctx['anticoagulant_name']})   on_opioid: {ctx['on_opioid']}")
    print(f"next appointment: {ctx['next_clinical_followup']['type']} in {ctx['days_to_next_appointment']} days")
    print(f"next of any kind:  {ctx['next_followup']['type']} in {ctx['next_followup']['days_away']} days")
    print(f"helpline {ctx['helpline']}  |  on-call {ctx['on_call']}  |  {len(load_rules())} rules loaded")
