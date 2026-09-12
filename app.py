"""Meantime - Streamlit front end.

Chat on the left, the reason for the answer on the right: which rule fired,
where it came from, and what the agent did about it.
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

TOOL_LABEL = {
    "get_patient_context": "Patient record loaded",
    "assess_urgency": "Rules checked",
    "message_care_team": "Care team messaged",
    "schedule_checkin": "Check-in scheduled",
    "log_symptom": "Diary entry logged",
}


# --- session --------------------------------------------------------------

def boot(fresh: bool = False) -> None:
    if fresh:
        db.reset_demo()
    conv_id, history, events = agent.start_conversation()
    st.session_state.conv_id = conv_id
    st.session_state.history = history
    st.session_state.events = events
    st.session_state.messages = []


if "conv_id" not in st.session_state:
    boot()

RULES_FILE = db.load_rules_file()
SOURCES = RULES_FILE["sources"]
ctx = db.get_patient_context()


def latest_assessment():
    return agent.latest_assessment(st.session_state.events)


# --- sidebar --------------------------------------------------------------

with st.sidebar:
    st.markdown(f"### {ctx['name']}")
    st.caption(f"{ctx['age']} · {ctx['sex']} · {ctx['patient_id']}")
    st.markdown(f"**{ctx['procedure']}**")
    st.caption(f"Surgery {ctx['surgery_date']} · discharged {ctx['discharge_date']}")

    st.markdown(
        f"<div style='font-size:2.6rem;line-height:1;font-weight:700;margin:.35rem 0 .1rem'>Day {ctx['post_op_day']}</div>"
        "<div style='color:#5f6368;font-size:.8rem;margin-bottom:.6rem'>after surgery</div>",
        unsafe_allow_html=True,
    )

    chips = [
        f"On {ctx['anticoagulant_name']} (blood thinner)" if ctx["on_anticoagulant"] else None,
        "On oxycodone" if ctx["on_opioid"] else None,
    ]
    for chip in [c for c in chips if c]:
        st.markdown(
            f"<span style='background:#eef1f6;border-radius:12px;padding:.18rem .55rem;"
            f"font-size:.78rem;margin-right:.25rem'>{chip}</span>",
            unsafe_allow_html=True,
        )

    nxt = ctx["next_clinical_followup"]
    if nxt:
        st.markdown(
            f"<div style='margin-top:.7rem;font-size:.85rem'>Next appointment: <b>{nxt['type']}</b> "
            f"in <b>{nxt['days_away']} days</b><br>"
            f"<span style='color:#5f6368;font-size:.78rem'>{nxt['date']} · {nxt['with']}</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # --- urgency badge
    assessment = latest_assessment()
    level = assessment["level"] if assessment else None
    if level:
        fg, bg, label = LEVEL_STYLE[level]
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

    # --- matched rules and provenance
    if assessment and assessment["matched"]:
        st.markdown("###### Why")
        for match in assessment["matched"]:
            st.markdown(
                f"<div style='font-size:.82rem;margin-bottom:.5rem'>"
                f"<b>{match['id']}</b> · {match['level']}"
                f"{' · low confidence' if match['confidence'] == 'low' else ''}<br>"
                f"<span style='color:#3c4043'>{match['rationale']}</span></div>",
                unsafe_allow_html=True,
            )
            links = []
            for code in match["source"].split(","):
                src = SOURCES.get(code, {})
                name = src.get("name", code).split(" - ")[0]
                url = src.get("url")
                links.append(f"[{name}]({url})" if url else name)
            st.caption("Source: " + " · ".join(links))
    elif assessment and assessment["level"] == "UNCERTAIN":
        st.caption("No rule matched. That is not the same as 'you are fine'.")

    # --- actions
    st.markdown("###### Actions taken")
    for event in st.session_state.events:
        out = event.get("output", {})
        label = TOOL_LABEL.get(event["tool"], event["tool"])
        detail = ""
        if event["tool"] == "assess_urgency":
            detail = f"{out.get('level')} · {', '.join(m['id'] for m in out.get('matched', [])) or 'no match'}"
        elif event["tool"] == "message_care_team":
            detail = f"{out.get('sent_to', '')}"
        elif event["tool"] == "schedule_checkin":
            detail = str(out.get("due_at", "")).replace("T", " ")
        elif event["tool"] == "log_symptom":
            detail = str(out.get("entry", ""))[:70]
        elif event["tool"] == "get_patient_context":
            detail = str(out.get("loaded", ""))
        st.markdown(
            f"<div style='font-size:.78rem;margin-bottom:.35rem'>"
            f"<span style='color:#5f6368'>{event.get('at', '')}</span> · <b>{label}</b><br>"
            f"<span style='color:#5f6368'>{detail}</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()
    if st.button("Reset demo", use_container_width=True):
        boot(fresh=True)
        st.rerun()
    st.caption("Synthetic patient. Demo only. Not medical advice.")


# --- main column ----------------------------------------------------------

st.markdown("## Meantime")
st.caption(
    "The gap between leaving the hospital and the next appointment. "
    "The model understands language · rules decide urgency · humans see every escalation."
)
st.info(
    "Synthetic patient, synthetic clinicians, fictional phone numbers. Demo only - not medical advice.",
    icon="⚠️",
)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown(
            f"Hi Robert. You are **day {ctx['post_op_day']}** after your {ctx['procedure'].lower()}. "
            "I have your discharge summary here. Tell me what is going on and I will tell you how urgent it is."
        )

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
                reply, events = agent.run_turn(st.session_state.conv_id, st.session_state.history, prompt)
            except Exception as exc:
                reply, events = f"Something went wrong reaching the model: `{exc}`", []
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.session_state.events.extend(events)
    st.rerun()
