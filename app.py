"""Meantime - Streamlit front end.

Two views over the same session. The Dashboard is the case for the system:
which rules can fire right now, where every one of them came from, and who
has been contacted. The Conversation is the product itself.

Look and feel lives in ui.py; this file is layout.
"""

from __future__ import annotations

import os
from collections import Counter

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import agent  # noqa: E402
import db  # noqa: E402
import engine  # noqa: E402
import sources  # noqa: E402
import ui  # noqa: E402


@st.cache_data(ttl=900, show_spinner=False)
def live_bundle(phase: str, _ctx: dict, nonce: int = 0, force: bool = False) -> dict:
    """Public-API lookups for this patient. Cached so switching views does not
    re-hit NIH every rerun; sources.py also caches to disk for offline runs.
    `force` bypasses both, for the Refresh button."""
    return sources.live_bundle(_ctx, force=force)

st.set_page_config(page_title="Meantime", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")
st.markdown(ui.CSS, unsafe_allow_html=True)

PHASE_LABELS = {
    "no_procedure": "Before any treatment",
    "pre_op": "Waiting for surgery",
    "post_op": "After discharge",
}
PHASE_BY_LABEL = {v: k for k, v in PHASE_LABELS.items()}

PHASE_STEPS = [
    {
        "key": "no_procedure",
        "title": "Before any treatment",
        "desc": "Nothing booked. He has a problem and wants to understand it.",
        "record": "Baseline history",
    },
    {
        "key": "pre_op",
        "title": "Waiting for surgery",
        "desc": "Booked. Some problems mean the operation should be postponed.",
        "record": "Booking + preparation",
    },
    {
        "key": "post_op",
        "title": "After discharge",
        "desc": "Home and recovering, on a blood thinner.",
        "record": "Discharge summary",
    },
]

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
st.session_state.setdefault("view", "Conversation")

RULES_FILE = db.load_rules_file()
ALL_RULES = RULES_FILE["rules"]
SOURCES = dict(RULES_FILE["sources"])
SOURCES.update(db.load_conditions_file()["sources"])

phase = st.session_state.phase
ctx = db.get_patient_context(phase=phase)
assessment = agent.latest_assessment(st.session_state.events)
possibilities = agent.latest_possibilities(st.session_state.events)
active_rules = engine.rules_for_phase(ALL_RULES, phase, ctx["procedure_code"])


def event_rows() -> list[tuple]:
    rows = []
    for event in st.session_state.events:
        out = event.get("output", {})
        name = TOOL_LABEL.get(event["tool"], event["tool"])
        if event["tool"] == "assess_urgency":
            level = out.get("level", "UNCERTAIN")
            name = f"{ui.level_pill(level)} <span style='margin-left:.3rem'>{name}</span>"
            detail = ", ".join(m["id"] for m in out.get("matched", [])) or "no rule matched"
        elif event["tool"] == "explore_possibilities":
            detail = ", ".join(p["name"] for p in out.get("possibilities", [])) or "nothing matched"
        elif event["tool"] == "message_care_team":
            detail = str(out.get("sent_to", ""))
        elif event["tool"] == "schedule_checkin":
            detail = str(out.get("due_at", "")).replace("T", " ")
        elif event["tool"] == "log_symptom":
            detail = str(out.get("entry", ""))[:120]
        else:
            detail = str(out.get("loaded", ""))
        rows.append((event.get("at", ""), name, detail))
    return rows


# --- sidebar --------------------------------------------------------------

with st.sidebar:
    st.markdown(
        f"<div class='mt-brand' style='margin-bottom:.8rem'>{ui.MARK_SVG}"
        f"<div class='mt-word' style='font-size:1.25rem'>{ui.WORDMARK}</div></div>",
        unsafe_allow_html=True,
    )

    chosen = st.radio(
        "Where Robert is",
        list(PHASE_LABELS.values()),
        index=list(PHASE_LABELS).index(phase),
        help="The same patient, three points on the same timeline. Switching resets the conversation.",
    )
    if PHASE_BY_LABEL[chosen] != phase:
        boot(PHASE_BY_LABEL[chosen])
        st.rerun()

    st.divider()

    st.markdown(f"**{ctx['name']}**")
    st.caption(f"{ctx['age']} · {ctx['sex']} · {ctx['patient_id']}")

    if phase == "post_op":
        big, sub = f"Day {ctx['post_op_day']}", "after surgery"
    elif phase == "pre_op":
        big, sub = f"{ctx['days_until_surgery']} days", "until surgery"
    else:
        big, sub = "No procedure", "booked or completed"
    st.markdown(
        f"<div class='mt-big' style='font-size:1.9rem'>{big}</div><div class='mt-sub'>{sub}</div>",
        unsafe_allow_html=True,
    )

    chips = []
    if ctx["on_anticoagulant"]:
        chips.append(f"On {ctx['anticoagulant_name']} · blood thinner")
    if ctx["on_opioid"]:
        chips.append("On oxycodone")
    if phase == "pre_op":
        chips.append(f"Surgery {ctx['surgery_date']} · arrive {ctx['arrival_time']}")
    if phase == "no_procedure":
        chips += [c["name"] for c in ctx["conditions"][:2]]
    st.markdown(
        "<div style='margin-top:.5rem'>"
        + "".join(
            f"<span style='background:#f0efeb;border:1px solid var(--line);border-radius:999px;"
            f"padding:.18rem .55rem;font-size:.72rem;margin:0 .25rem .3rem 0;display:inline-block'>{ui.esc(c)}</span>"
            for c in chips
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    nxt = ctx.get("next_clinical_followup") or ctx.get("next_followup")
    if nxt:
        st.markdown(
            f"<div style='margin-top:.5rem;font-size:.8rem;color:var(--ink-2)'>Next: <b>{ui.esc(nxt['type'])}</b> "
            f"in <b>{nxt['days_away']} days</b><br>"
            f"<span style='color:var(--ink-3);font-size:.72rem'>{nxt['date']} · {ui.esc(nxt['with'])}</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # the badge is pinned: it is the answer, never a click away
    if assessment:
        st.markdown(ui.badge_block(assessment["level"], assessment["level_action"]), unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='background:#f0f1f3;border-left:5px solid #5f6874;padding:.7rem .8rem;"
            "border-radius:8px;color:#5f6874;font-size:.82rem'>No assessment yet</div>",
            unsafe_allow_html=True,
        )

    if assessment:
        n = len(assessment["matched"])
        with st.expander(f"Why this answer · {n} rule{'s' if n != 1 else ''}", expanded=True):
            if not assessment["matched"]:
                st.markdown(
                    "**No rule matched.** That is not the same as *you are fine* — it is why this came "
                    "back UNCERTAIN instead of reassuring."
                )
            for match in assessment["matched"]:
                low = " · low confidence" if match["confidence"] == "low" else ""
                st.markdown(
                    f"<div style='font-size:.8rem;margin-bottom:.15rem'>"
                    f"{ui.source_chips(match['source'])}<b>{match['id']}</b> · {match['level']}{low}</div>"
                    f"<div style='font-size:.79rem;color:var(--ink-2);line-height:1.45'>{ui.esc(match['rationale'])}</div>",
                    unsafe_allow_html=True,
                )
                if match.get("source_url"):
                    st.caption(f"[Read the source]({match['source_url']})")
            if assessment["watch_for"]:
                st.markdown("**Come back if:**")
                for item in assessment["watch_for"]:
                    st.markdown(f"<div style='font-size:.78rem'>· {ui.esc(item)}</div>", unsafe_allow_html=True)

    if possibilities:
        with st.expander(f"Possibilities to ask about · {len(possibilities)}", expanded=True):
            st.caption("Not a diagnosis. Ordered by overlap with what he described, not by likelihood.")
            for candidate in possibilities:
                st.markdown(
                    f"<div style='font-size:.8rem;margin-top:.35rem'>{ui.source_chips(candidate['source'])}"
                    f"<b>{ui.esc(candidate['name'])}</b></div>"
                    f"<div style='font-size:.75rem;color:var(--ink-3);line-height:1.4'>{ui.esc(candidate['plain'])}</div>",
                    unsafe_allow_html=True,
                )

    with st.expander("The record", expanded=False):
        st.markdown("**Conditions**")
        for condition in ctx["conditions"]:
            st.markdown(
                f"<div style='font-size:.78rem'>· {ui.esc(condition['name'])} (since {condition['since']})</div>",
                unsafe_allow_html=True,
            )
        st.markdown("**Regular medications**")
        for med in ctx["home_medications"]:
            st.markdown(
                f"<div style='font-size:.78rem'>· {ui.esc(med['name'])} {ui.esc(med['dose'])}, {ui.esc(med['frequency'])}</div>",
                unsafe_allow_html=True,
            )
        if phase == "post_op":
            st.markdown("**Discharge medications**")
            for med in ctx["discharge_medications"]:
                extra = f" — {med['purpose']}" if med.get("purpose") else ""
                dose = f" {med.get('dose', '')} {med.get('frequency', '')}".rstrip()
                st.markdown(
                    f"<div style='font-size:.78rem'>· {ui.esc(med['name'])}{ui.esc(dose)}{ui.esc(extra)}</div>",
                    unsafe_allow_html=True,
                )
        if phase == "pre_op":
            st.markdown("**Getting ready**")
            for key, value in ctx["preparation"].items():
                st.markdown(
                    f"<div style='font-size:.78rem'><b>{key.title()}:</b> {ui.esc(value)}</div>",
                    unsafe_allow_html=True,
                )
        for allergy in ctx["allergies"]:
            st.warning(f"Allergy: {allergy['substance']} ({allergy['reaction']})", icon="⚠️")
        if ctx.get("warning_list"):
            st.markdown(f"**{'Surgeon' if phase == 'post_op' else 'Pre-operative'} warning list**")
            for line in ctx["warning_list"]:
                st.markdown(
                    f"<div style='font-size:.76rem;color:var(--ink-2)'>· {ui.esc(line)}</div>",
                    unsafe_allow_html=True,
                )
        appointments = ctx.get("follow_up") or ctx.get("pre_op_appointments") or []
        if appointments:
            st.markdown("**Appointments**")
            for appointment in appointments:
                st.markdown(
                    f"<div style='font-size:.78rem'>· {appointment['date']} — {ui.esc(appointment['type'])}, "
                    f"{ui.esc(appointment['with'])}</div>",
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
            st.markdown(f"<div style='font-size:.78rem'>· {ui.esc(line)}</div>", unsafe_allow_html=True)

    st.divider()
    if st.button("Reset conversation", use_container_width=True):
        boot(phase)
        st.rerun()
    st.caption("Synthetic patient. Demo only. Not medical advice.")


# --- masthead and view switch --------------------------------------------

st.markdown(ui.masthead(), unsafe_allow_html=True)

# Keyed, so the choice survives the rerun. segmented_control returns None when
# the selected option is clicked again, which should keep the view, not clear it.
st.session_state.setdefault("view_sel", "Conversation")
chosen_view = st.segmented_control(
    "View", ["Conversation", "Dashboard"], key="view_sel", label_visibility="collapsed"
)
view = chosen_view or st.session_state.view
st.session_state.view = view


# --- dashboard ------------------------------------------------------------

if view == "Dashboard":
    escalations = [
        e for e in st.session_state.events if e["tool"] == "message_care_team" and not e["output"].get("error")
    ]
    checked = [e for e in st.session_state.events if e["tool"] == "assess_urgency"]

    if phase == "post_op":
        where_big, where_sub = f"Day {ctx['post_op_day']}", "after right total knee arthroplasty"
    elif phase == "pre_op":
        where_big, where_sub = f"{ctx['days_until_surgery']} days", f"until surgery on {ctx['surgery_date']}"
    else:
        where_big, where_sub = "No procedure", "baseline history only"

    if assessment:
        verdict_big = ui.level_pill(assessment["level"])
        verdict_sub = assessment["level_action"]
    else:
        verdict_big, verdict_sub = "<span style='color:#7b8694'>—</span>", "Nothing assessed in this session yet"

    st.markdown(
        ui.stat_row(
            [
                ui.stat_card("Where Robert is", where_big, where_sub),
                ui.stat_card("Current verdict", verdict_big, ui.esc(verdict_sub)),
                ui.stat_card(
                    "Escalations to a human",
                    str(len(escalations)),
                    f"from {len(checked)} rule check{'s' if len(checked) != 1 else ''} this session",
                ),
                ui.stat_card(
                    "Rules in force",
                    str(len(active_rules)),
                    f"of {len(ALL_RULES)} in the library, for this phase",
                ),
            ]
        ),
        unsafe_allow_html=True,
    )

    st.markdown(ui.heading("The arc", "one engine, one rule file, three points on the same timeline"), unsafe_allow_html=True)
    steps = [
        dict(step, rules=len(engine.rules_for_phase(ALL_RULES, step["key"], None if step["key"] == "no_procedure" else "tka")))
        for step in PHASE_STEPS
    ]
    st.markdown(ui.arc(phase, steps), unsafe_allow_html=True)

    left, right = st.columns([1.55, 1], gap="medium")

    with left:
        st.markdown(
            ui.heading("Rules that can fire right now", f"{len(active_rules)} for {PHASE_LABELS[phase].lower()}"),
            unsafe_allow_html=True,
        )
        st.markdown(ui.distribution(Counter(r["level"] for r in active_rules)), unsafe_allow_html=True)
        order = {"EMERGENCY": 0, "URGENT": 1, "CONTACT_TEAM": 2, "MONITOR": 3}
        ranked = sorted(active_rules, key=lambda r: (order[r["level"]], r["id"]))
        st.markdown(ui.rule_rows(ranked), unsafe_allow_html=True)

    with right:
        st.markdown(ui.heading("Evidence base", "every rule traces to one of these"), unsafe_allow_html=True)
        counts = Counter()
        for rule in ALL_RULES:
            for code in rule["source"].split(","):
                counts[code] += 1
        st.markdown(
            ui.source_list([(code, counts.get(code, 0), (SOURCES.get(code) or {}).get("url")) for code in ui.SOURCE_BADGE]),
            unsafe_allow_html=True,
        )

        st.markdown(ui.heading("Care team inbox", "what the humans receive"), unsafe_allow_html=True)
        st.markdown(ui.inbox(db.list_messages_for_conv(st.session_state.conv_id)), unsafe_allow_html=True)

        st.markdown(ui.heading("Session activity", "every tool call, in order"), unsafe_allow_html=True)
        st.markdown(ui.activity(event_rows()), unsafe_allow_html=True)

    # --- live public-API panel -------------------------------------------
    head, refresh = st.columns([5, 1])
    with head:
        st.markdown(
            ui.heading("Live from the source", "NIH · FDA · NLM, fetched for this patient at page load"),
            unsafe_allow_html=True,
        )
    with refresh:
        st.write("")
        if st.button("Refresh", use_container_width=True, help="Re-fetch from the public APIs now"):
            st.session_state.live_nonce = st.session_state.get("live_nonce", 0) + 1
            st.session_state.force_live = True
            st.rerun()

    with st.spinner("Querying MedlinePlus, RxNav, openFDA and ClinicalTrials.gov…"):
        try:
            force = st.session_state.pop("force_live", False)
            bundle = live_bundle(phase, ctx, st.session_state.get("live_nonce", 0), force)
        except Exception as exc:
            bundle = None
            st.warning(f"Could not reach the public APIs: {exc}")

    if bundle:
        st.markdown(ui.api_bar(bundle), unsafe_allow_html=True)
        st.caption(
            f"{bundle['live_count']} fetched live · {bundle['cached_count']} from cache · "
            f"{bundle['failed_count']} unreachable · checked {bundle['checked_at']}"
        )
        st.markdown(ui.split_note(), unsafe_allow_html=True)

        col_a, col_b, col_c = st.columns(3, gap="medium")
        with col_a:
            st.markdown(
                ui.heading("Patient education", "MedlinePlus Connect, keyed on his own ICD-10 codes"),
                unsafe_allow_html=True,
            )
            st.markdown(ui.education_card(bundle["education"]), unsafe_allow_html=True)
            st.markdown(ui.heading("Concepts the rules cite", "MedlinePlus health topics"), unsafe_allow_html=True)
            st.markdown(ui.topic_cards(bundle["topics"]), unsafe_allow_html=True)
        with col_b:
            st.markdown(
                ui.heading("Medications", "RxNorm identity + the live FDA label"), unsafe_allow_html=True
            )
            st.markdown(ui.drug_cards(bundle["drugs"]), unsafe_allow_html=True)
        with col_c:
            st.markdown(ui.heading("Studies recruiting now", "ClinicalTrials.gov"), unsafe_allow_html=True)
            st.markdown(ui.trial_rows(bundle["trials"]), unsafe_allow_html=True)


# --- conversation ---------------------------------------------------------

else:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if not st.session_state.messages:
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
