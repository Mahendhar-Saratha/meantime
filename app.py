"""Meantime - Streamlit front end.

Chat on the left, the reason for the answer on the right: which rule fired,
where it came from, and what the agent did about it.

The sidebar is collapsible section by section. The urgency badge is the one
thing that is always pinned - it is the answer, and it should never be a click
away.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import agent  # noqa: E402
import db  # noqa: E402

st.set_page_config(page_title="Meantime", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")

LEVEL_STYLE = {
    "EMERGENCY": ("#b3261e", "#fdeceb", "EMERGENCY"),
    "URGENT": ("#c2610c", "#fdf1e6", "URGENT"),
    "CONTACT_TEAM": ("#8a6d00", "#fdf8e3", "CONTACT CARE TEAM"),
    "MONITOR": ("#1f7a3d", "#ebf6ee", "MONITOR"),
    "UNCERTAIN": ("#5f6368", "#f1f2f3", "UNCERTAIN"),
}

PHASE_LABELS = {
    "no_procedure": "Before any treatment",
    "pre_op": "Waiting for surgery",
    "post_op": "After discharge",
}
PHASE_BY_LABEL = {v: k for k, v in PHASE_LABELS.items()}

PHASE_BLURB = {
    "no_procedure": "Nothing booked. He has a problem and wants to understand it.",
    "pre_op": "Operation booked. Some problems mean it should be postponed.",
    "post_op": "Home after surgery, with the discharge summary loaded.",
}

TOOL_LABEL = {
    "get_patient_context": "Patient record loaded",
    "assess_urgency": "Rules checked",
    "explore_possibilities": "Possibilities looked up",
    "message_care_team": "Care team messaged",
    "schedule_checkin": "Check-in scheduled",
    "log_symptom": "Diary entry logged",
}


# --- session --------------------------------------------------------------

def boot(phase: str = "post_op", fresh: bool = True) -> None:
    if fresh:
        db.reset_demo()
    conv_id, history, events = agent.start_conversation(phase)
    st.session_state.phase = phase
    st.session_state.conv_id = conv_id
    st.session_state.history = history
    st.session_state.events = events
    st.session_state.messages = []


if "conv_id" not in st.session_state:
    boot()

RULES_FILE = db.load_rules_file()
SOURCES = dict(RULES_FILE["sources"])
SOURCES.update(db.load_conditions_file()["sources"])

phase = st.session_state.phase
ctx = db.get_patient_context(phase=phase)
assessment = agent.latest_assessment(st.session_state.events)
possibilities = agent.latest_possibilities(st.session_state.events)


def source_links(codes: str) -> str:
    out = []
    for code in codes.split(","):
        src = SOURCES.get(code, {})
        name = src.get("name", code).split(" - ")[0].split(" (")[0]
        url = src.get("url")
        out.append(f"[{name}]({url})" if url else name)
    return " · ".join(out)


def chip(text: str) -> str:
    return (
        f"<span style='background:#eef1f6;border-radius:12px;padding:.18rem .55rem;"
        f"font-size:.78rem;margin-right:.25rem;display:inline-block;margin-bottom:.2rem'>{text}</span>"
    )


# --- sidebar --------------------------------------------------------------

with st.sidebar:
    chosen = st.radio(
        "Where Robert is",
        list(PHASE_LABELS.values()),
        index=list(PHASE_LABELS).index(phase),
        help="The same patient, three points on the same timeline. Switching resets the conversation.",
    )
    if PHASE_BY_LABEL[chosen] != phase:
        boot(PHASE_BY_LABEL[chosen])
        st.rerun()
    st.caption(PHASE_BLURB[phase])

    st.divider()

    # --- always-visible header
    st.markdown(f"**{ctx['name']}**")
    st.caption(f"{ctx['age']} · {ctx['sex']} · {ctx['patient_id']}")

    if phase == "post_op":
        big, sub = f"Day {ctx['post_op_day']}", "after surgery"
    elif phase == "pre_op":
        big, sub = f"{ctx['days_until_surgery']} days", "until surgery"
    else:
        big, sub = "No procedure", "booked or completed"
    st.markdown(
        f"<div style='font-size:2.2rem;line-height:1;font-weight:700;margin:.3rem 0 .05rem'>{big}</div>"
        f"<div style='color:#5f6368;font-size:.8rem;margin-bottom:.5rem'>{sub}</div>",
        unsafe_allow_html=True,
    )

    chips = []
    if ctx["on_anticoagulant"]:
        chips.append(f"On {ctx['anticoagulant_name']} (blood thinner)")
    if ctx["on_opioid"]:
        chips.append("On oxycodone")
    if phase == "pre_op":
        chips.append(f"Surgery {ctx['surgery_date']}, arrive {ctx['arrival_time']}")
    if phase == "no_procedure":
        chips += [c["name"] for c in ctx["conditions"][:2]]
    st.markdown("".join(chip(c) for c in chips), unsafe_allow_html=True)

    nxt = ctx.get("next_clinical_followup") or ctx.get("next_followup")
    if nxt:
        st.markdown(
            f"<div style='margin-top:.6rem;font-size:.82rem'>Next: <b>{nxt['type']}</b> "
            f"in <b>{nxt['days_away']} days</b><br>"
            f"<span style='color:#5f6368;font-size:.76rem'>{nxt['date']} · {nxt['with']}</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # --- the badge: pinned, never collapsible
    if assessment:
        fg, bg, label = LEVEL_STYLE[assessment["level"]]
        st.markdown(
            f"<div style='background:{bg};border-left:6px solid {fg};padding:.7rem .8rem;border-radius:6px'>"
            f"<div style='color:{fg};font-weight:800;letter-spacing:.06em;font-size:.9rem'>{label}</div>"
            f"<div style='margin-top:.35rem;font-size:.85rem;line-height:1.35'>{assessment['level_action']}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        fg, bg, _ = LEVEL_STYLE["UNCERTAIN"]
        st.markdown(
            f"<div style='background:{bg};border-left:6px solid {fg};padding:.7rem .8rem;border-radius:6px;"
            f"color:{fg};font-size:.85rem'>No assessment yet</div>",
            unsafe_allow_html=True,
        )

    # --- why
    if assessment:
        n = len(assessment["matched"])
        with st.expander(f"Why this answer ({n} rule{'s' if n != 1 else ''})", expanded=True):
            if not assessment["matched"]:
                st.markdown(
                    "**No rule matched.** That is not the same as 'you are fine' - it is why this "
                    "came back UNCERTAIN instead of reassuring."
                )
            for match in assessment["matched"]:
                low = " · low confidence" if match["confidence"] == "low" else ""
                st.markdown(
                    f"<div style='font-size:.82rem'><b>{match['id']}</b> · {match['level']}{low}<br>"
                    f"<span style='color:#3c4043'>{match['rationale']}</span></div>",
                    unsafe_allow_html=True,
                )
                st.caption("Source: " + source_links(match["source"]))
            if assessment["watch_for"]:
                st.markdown("**Watch for**")
                for item in assessment["watch_for"]:
                    st.markdown(f"<div style='font-size:.8rem'>· {item}</div>", unsafe_allow_html=True)

    # --- possibilities (before any treatment only)
    if possibilities:
        with st.expander(f"Possibilities to ask about ({len(possibilities)})", expanded=True):
            st.caption("Not a diagnosis. Ordered by how much of what he described each one involves, not by likelihood.")
            for candidate in possibilities:
                st.markdown(
                    f"<div style='font-size:.82rem;margin-top:.4rem'><b>{candidate['name']}</b><br>"
                    f"<span style='color:#3c4043'>{candidate['plain']}</span></div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"Matches: {', '.join(candidate['matched_symptoms'])} · " + source_links(candidate["source"])
                )

    # --- the record
    with st.expander("The record", expanded=False):
        st.markdown("**Conditions**")
        for condition in ctx["conditions"]:
            st.markdown(f"<div style='font-size:.8rem'>· {condition['name']} (since {condition['since']})</div>", unsafe_allow_html=True)

        st.markdown("**Regular medications**")
        for med in ctx["home_medications"]:
            st.markdown(f"<div style='font-size:.8rem'>· {med['name']} {med['dose']}, {med['frequency']}</div>", unsafe_allow_html=True)

        if phase == "post_op":
            st.markdown("**Discharge medications**")
            for med in ctx["discharge_medications"]:
                extra = f" — {med['purpose']}" if med.get("purpose") else ""
                dose = f" {med.get('dose', '')} {med.get('frequency', '')}".rstrip()
                st.markdown(f"<div style='font-size:.8rem'>· {med['name']}{dose}{extra}</div>", unsafe_allow_html=True)

        if phase == "pre_op":
            st.markdown("**Getting ready**")
            for key, value in ctx["preparation"].items():
                st.markdown(f"<div style='font-size:.8rem'><b>{key.title()}:</b> {value}</div>", unsafe_allow_html=True)

        for allergy in ctx["allergies"]:
            st.warning(f"Allergy: {allergy['substance']} ({allergy['reaction']})", icon="⚠️")

        if ctx.get("warning_list"):
            heading = "Surgeon's warning list" if phase == "post_op" else "Pre-operative warning list"
            st.markdown(f"**{heading}**")
            for line in ctx["warning_list"]:
                st.markdown(f"<div style='font-size:.78rem;color:#3c4043'>· {line}</div>", unsafe_allow_html=True)

        appointments = ctx.get("follow_up") or ctx.get("pre_op_appointments") or []
        if appointments:
            st.markdown("**Appointments**")
            for appointment in appointments:
                st.markdown(
                    f"<div style='font-size:.8rem'>· {appointment['date']} — {appointment['type']}, {appointment['with']}</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("**Contacts**")
        gp = ctx["primary_care"]
        lines = [f"Nurse helpline {ctx['helpline']}", f"{gp['clinician']}, {gp['practice']} {gp['phone']}"]
        if ctx.get("on_call"):
            lines.append(f"{ctx['surgeon']['name']} on-call {ctx['on_call']}")
        if phase == "pre_op":
            lines.append(f"Surgical scheduling {ctx['scheduler_phone']}")
        emergency = ctx["emergency_contact"]
        lines.append(f"{emergency['name']} ({emergency['relation']}) {emergency['phone']}")
        for line in lines:
            st.markdown(f"<div style='font-size:.8rem'>· {line}</div>", unsafe_allow_html=True)

    # --- actions
    with st.expander(f"Actions taken ({len(st.session_state.events)})", expanded=True):
        for event in st.session_state.events:
            out = event.get("output", {})
            label = TOOL_LABEL.get(event["tool"], event["tool"])
            if event["tool"] == "assess_urgency":
                detail = f"{out.get('level')} · {', '.join(m['id'] for m in out.get('matched', [])) or 'no match'}"
            elif event["tool"] == "explore_possibilities":
                detail = ", ".join(p["name"] for p in out.get("possibilities", [])) or "nothing matched"
            elif event["tool"] == "message_care_team":
                detail = str(out.get("sent_to", ""))
            elif event["tool"] == "schedule_checkin":
                detail = str(out.get("due_at", "")).replace("T", " ")
            elif event["tool"] == "log_symptom":
                detail = str(out.get("entry", ""))[:70]
            else:
                detail = str(out.get("loaded", ""))
            st.markdown(
                f"<div style='font-size:.78rem;margin-bottom:.35rem'>"
                f"<span style='color:#5f6368'>{event.get('at', '')}</span> · <b>{label}</b><br>"
                f"<span style='color:#5f6368'>{detail}</span></div>",
                unsafe_allow_html=True,
            )

    st.divider()
    if st.button("Reset conversation", use_container_width=True):
        boot(phase)
        st.rerun()
    st.caption("Synthetic patient. Demo only. Not medical advice.")


# --- main column ----------------------------------------------------------

st.markdown("## Meantime")
st.caption(
    "The gaps between appointments. "
    "The model understands language · rules decide urgency · humans see every escalation."
)
st.info("Synthetic patient, synthetic clinicians, fictional phone numbers. Demo only - not medical advice.", icon="⚠️")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if not st.session_state.messages:
    # Built one branch at a time: the fields each phase refers to only exist in
    # that phase.
    if phase == "post_op":
        opener = (
            f"Hi Robert. You are **day {ctx['post_op_day']}** after your {str(ctx['procedure']).lower()}. "
            "I have your discharge summary here. Tell me what is going on and I will tell you how urgent it is."
        )
    elif phase == "pre_op":
        opener = (
            f"Hi Robert. Your {str(ctx['procedure']).lower()} is **in {ctx['days_until_surgery']} days**. "
            "I have your booking and the preparation instructions here. If anything has come up, tell me — there "
            "are things the team needs to know before the day rather than on it."
        )
    else:
        opener = (
            "Hi Robert. Nothing is booked, and I have your medical history here. Tell me what is going on. "
            "I will tell you how urgent it is, and what it could be worth asking a doctor about."
        )
    with st.chat_message("assistant"):
        st.markdown(opener)

prompt = st.chat_input("Tell me what's going on…")

if prompt:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("ANTHROPIC_API_KEY is not set. Put it in .env and restart.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Checking against the warning list…"):
            try:
                reply, events = agent.run_turn(
                    st.session_state.conv_id, st.session_state.history, prompt, st.session_state.phase
                )
            except Exception as exc:
                reply, events = f"Something went wrong reaching the model: `{exc}`", []
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.session_state.events.extend(events)
    st.rerun()
