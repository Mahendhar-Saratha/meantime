"""The agent: system prompt, tool loop, and a terminal REPL for testing.

The model converses, extracts a structured symptom report, and calls tools.
It does not decide urgency - engine.py does, behind assess_urgency.

Run `python agent.py [no_procedure|pre_op|post_op]` for a terminal conversation
with the tool calls printed.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from datetime import datetime

import anthropic
from dotenv import load_dotenv

import db
import engine
import tools

load_dotenv()

MODEL = os.environ.get("MODEL", "claude-sonnet-5")
EFFORT = os.environ.get("EFFORT", "medium")
MAX_TOKENS = 2000
MAX_TOOL_ITERATIONS = 6
PHASES = ("no_procedure", "pre_op", "post_op")

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


PHASE_BLOCKS = {
    "no_procedure": """\
WHERE ROBERT IS RIGHT NOW
He has had no procedure. Nothing is booked. He is describing a problem and trying to understand it.

In this phase you have one extra job. After assess_urgency, call explore_possibilities and present what \
comes back as things to raise with a clinician. Rules for that list:
- Never say which one it is, and never say which is most likely. The list is not ordered by likelihood \
and you must not imply that it is.
- For each one give its name, the plain-language description, and the one or two "more likely if" lines \
that actually match what he told you.
- End with the urgency answer and the next step. The urgency answer always wins over the list.
- If it comes back empty, say the list has nothing that matches and point him at his GP. Do not invent \
possibilities of your own.

There is no surgical team in this phase. Escalation means his GP practice, urgent care, or 911.""",
    "pre_op": """\
WHERE ROBERT IS RIGHT NOW
His right total knee replacement is booked and has not happened yet. The record tells you how many days \
away it is, and carries the preparation instructions and the pre-operative warning list.

He is NOT on apixaban or oxycodone yet - those start after surgery. Do not refer to them as though he is \
taking them.

The thing that matters most in this phase: some problems mean the operation should be postponed, and that \
is the surgical team's decision to make, not his and not yours. An infection, a break in the skin on that \
leg, a dental abscess, a missed medication instruction, or eating after the fasting cutoff all mean a \
phone call to surgical scheduling today. Say plainly that postponing is far safer than going ahead, and \
that they would much rather hear it now than on the morning.

Do not call explore_possibilities in this phase.""",
    "post_op": """\
WHERE ROBERT IS RIGHT NOW
He is at home after his right total knee replacement. The record tells you which post-op day he is on. He \
is on apixaban, a blood thinner, and on oxycodone. Refer to these specifics, and to his surgeon's warning \
list, when you explain things.

Do not call explore_possibilities in this phase.""",
}

SYSTEM_PROMPT_TEMPLATE = """\
You are Meantime, a support agent for one patient, Robert Hale. You help him in the gaps between \
appointments, when something worries him and there is no one to ask. You are calm, warm, plain-spoken, \
never alarmist and never dismissive.

{phase_block}

WHAT YOU KNOW
The patient record is provided at the start of the conversation. Use it. Refer to specifics: dates, how \
many days from what, the medicines he is actually on, the warning list he was given.

HOW YOU DECIDE URGENCY - THE ONLY WAY
1. Listen. Restate briefly what he described in your own words so he knows you understood.
2. If a key detail is missing that changes the answer (which leg; calf vs knee; a temperature reading; one \
leg or both; whether bleeding stops with pressure), ask ONE short question. You may ask at most TWO \
clarifying questions in a conversation. Do not ask questions for their own sake.
3. Convert what he said into a structured symptom_report using ONLY the canonical symptom names below. Do \
not invent symptoms he did not describe. Unknown fields are null.
4. Call assess_urgency. You must never tell him how urgent something is, or that something is normal, \
without calling it first. You do not decide urgency; the rules do.
5. Explain the result using the matched rule's rationale and his record. Then give the action for that \
level, exactly:
{level_actions}
6. If assess_urgency returns confidence "low", ask one clarifying question and call it again. If it is \
still low, treat it as UNCERTAIN.
7. Every turn in which Robert says anything about how he feels must include a call to assess_urgency \
before your reply ends - including when nothing he said maps to a canonical symptom name. In that case \
call it with an empty symptoms list and let the rules answer. Vagueness is not a reason to skip the \
check; it is the case the check exists for. You may still ask one short question in the same reply, but \
never end such a turn with no assessment.

RULES YOU NEVER BREAK
- Never diagnose. Say "signs that can go with a blood clot", not "you have a DVT". Even when you are \
listing possibilities, every one of them stays a possibility.
- Never say something is fine, normal, or expected unless a MONITOR rule matched.
- Never downgrade what the rules returned. You may not talk him out of an EMERGENCY or URGENT result, \
even if he says he would rather wait.
- Never give medication dosing advice beyond "take it as prescribed" and "do not double up".
- If he mentions thoughts of harming himself, respond with warmth first, give the 988 Suicide & Crisis \
Lifeline and 911, stay in the conversation, and message the care team.

TONE
Short paragraphs. Eighth-grade reading level. One idea per sentence when giving instructions. Acknowledge \
worry without amplifying it ("it makes sense that this worried you - here is what it means"). If he sounds \
increasingly panicked, name it gently and give one grounding step (a slow breath, sit down, have Linda \
nearby) before continuing. Never use the phrase "just anxiety".

Make your tool calls first, then write your reply once, as a single message. Do not add a second paragraph \
after a tool result that repeats what you already said.

CANONICAL SYMPTOM NAMES
{vocabulary}

QUALIFIERS
{qualifiers}

You are a support tool using synthetic data for a demonstration. Everything you say is reviewed by the \
care team.
"""


def _build_system_prompt(phase: str, ctx: dict) -> str:
    rules_file = db.load_rules_file()
    vocabulary = "\n".join(textwrap.wrap(" ".join(rules_file["vocabulary"]), 100))
    qualifiers = ", ".join(rules_file["qualifiers"])

    # The level actions come from the engine, so the prompt and the badge can
    # never drift apart.
    order = ["EMERGENCY", "URGENT", "CONTACT_TEAM", "MONITOR", "UNCERTAIN"]
    follow_up = {
        "EMERGENCY": "Keep it to three or four sentences. No further questions. Then call message_care_team.",
        "URGENT": "Then call message_care_team with a structured summary.",
        "CONTACT_TEAM": "Call message_care_team. Offer the helpline if he would rather talk to someone now.",
        "MONITOR": (
            "Give the reason it is expected, the self-care from his instructions, then the three-item watch "
            "list from the rule, and say \"come back to me if any of these happen\". Call schedule_checkin "
            "(12 to 24 hours) and log_symptom."
        ),
        "UNCERTAIN": (
            "Say plainly that you cannot tell from here. Do not reassure. Do not speculate. Offer to note "
            "what he told you for the record (log_symptom)."
        ),
    }
    lines = [
        f"   {level:<13}-> {engine.level_action(level, phase, ctx)} {follow_up[level]}" for level in order
    ]

    return SYSTEM_PROMPT_TEMPLATE.format(
        phase_block=PHASE_BLOCKS[phase],
        level_actions="\n".join(lines),
        vocabulary=vocabulary,
        qualifiers=qualifiers,
    )


def start_conversation(phase: str = "post_op") -> tuple[str, list, list]:
    """Open a conversation and pre-load the record so the agent never has to ask.

    Returns (conv_id, history, events).
    """
    db.seed()
    conv_id = db.new_conversation()
    ctx = tools.get_patient_context(phase=phase)
    history = [
        {
            "role": "user",
            "content": (
                "Here is the patient record for this conversation. Do not reply to this message; "
                "wait for Robert to write.\n\n" + json.dumps(ctx, indent=2)
            ),
        }
    ]
    events = [
        {
            "at": datetime.now().strftime("%H:%M"),
            "tool": "get_patient_context",
            "input": {},
            "output": {"loaded": _record_summary(ctx), "phase": phase},
        }
    ]
    return conv_id, history, events


def _record_summary(ctx: dict) -> str:
    if ctx["phase"] == "post_op":
        return f"{ctx['name']}, post-op day {ctx['post_op_day']}, {ctx['procedure']}"
    if ctx["phase"] == "pre_op":
        return f"{ctx['name']}, {ctx['days_until_surgery']} days before {ctx['procedure']}"
    return f"{ctx['name']}, age {ctx['age']}, no procedure planned"


def _text_of(response) -> str:
    parts = [b.text for b in response.content if b.type == "text"]
    return "\n\n".join(p.strip() for p in parts if p.strip())


# Asking the model nicely to always run the rules is not enough - it will
# sometimes stop to ask a clarifying question instead, which leaves the patient
# with no verdict at exactly the moment one matters. So the loop checks, and
# makes it call the tool.
ENFORCE_ASSESSMENT = (
    "[system note, not from Robert] You ended that turn without calling assess_urgency. "
    "Call it now with the symptoms he described, using canonical names, and an empty symptoms "
    "list if nothing maps. Then give him the answer for whatever level comes back. You may keep "
    "your clarifying question, but he does not get left without a verdict."
)


def needs_assessment(events: list) -> bool:
    """True when a turn produced no urgency verdict."""
    return not any(event["tool"] == "assess_urgency" for event in events)


def run_turn(conv_id: str, history: list, user_text: str, phase: str = "post_op") -> tuple[str, list]:
    """One patient turn: run the model until it stops calling tools.

    If it finishes without running the rules, it is sent back to do it.
    """
    history.append({"role": "user", "content": user_text})
    ctx = db.get_patient_context(phase=phase)
    system = _build_system_prompt(phase, ctx)

    said, events = _tool_loop(conv_id, history, system, phase)

    if needs_assessment(events):
        history.append({"role": "user", "content": ENFORCE_ASSESSMENT})
        more_said, more_events = _tool_loop(conv_id, history, system, phase)
        said += more_said
        events += more_events

    return "\n\n".join(said), events


def _tool_loop(conv_id: str, history: list, system: str, phase: str) -> tuple[list, list]:
    events: list[dict] = []
    # The explanation usually arrives in the same assistant message as the tool
    # call that follows it, so collect text from every iteration, not just the
    # last one.
    said: list[str] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client().messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools.TOOL_SCHEMAS,
            output_config={"effort": EFFORT},
            messages=history,
        )
        history.append({"role": "assistant", "content": response.content})

        chunk = _text_of(response)
        if chunk:
            said.append(chunk)

        if response.stop_reason != "tool_use":
            break

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            output = tools.dispatch(block.name, block.input, conv_id, phase)
            events.append(
                {
                    "at": datetime.now().strftime("%H:%M"),
                    "tool": block.name,
                    "input": block.input,
                    "output": output,
                }
            )
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(output, default=str)}
            )
        history.append({"role": "user", "content": results})

    return said, events


def latest_assessment(events: list) -> dict | None:
    """The most recent assess_urgency result in a list of events."""
    for event in reversed(events):
        if event["tool"] == "assess_urgency" and "level" in event.get("output", {}):
            return event["output"]
    return None


def latest_possibilities(events: list) -> list | None:
    """The most recent explore_possibilities result in a list of events."""
    for event in reversed(events):
        if event["tool"] == "explore_possibilities" and "possibilities" in event.get("output", {}):
            return event["output"]["possibilities"]
    return None


# --- terminal REPL --------------------------------------------------------

def _print_events(events: list) -> None:
    for event in events:
        out = event["output"]
        if event["tool"] == "assess_urgency":
            matched = ", ".join(f"{m['id']} [{m['source']}]" for m in out.get("matched", [])) or "-"
            print(f"    [tool] assess_urgency -> {out.get('level')} ({out.get('confidence')})  matched: {matched}")
        elif event["tool"] == "explore_possibilities":
            names = ", ".join(f"{p['id']} {p['name']}" for p in out.get("possibilities", [])) or "none"
            print(f"    [tool] explore_possibilities -> {names}")
        elif event["tool"] == "get_patient_context":
            print(f"    [tool] get_patient_context -> {out.get('loaded', 'record loaded')}")
        else:
            brief = {k: v for k, v in out.items() if k not in ("patient",)}
            print(f"    [tool] {event['tool']} -> {json.dumps(brief, default=str)[:160]}")


def main() -> None:
    try:  # the replies contain em-dashes; Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Put it in .env")

    phase = sys.argv[1] if len(sys.argv) > 1 else "post_op"
    if phase not in PHASES:
        sys.exit(f"Unknown phase {phase!r}. One of: {', '.join(PHASES)}")

    conv_id, history, events = start_conversation(phase)
    ctx = db.get_patient_context(phase=phase)
    print(f"Meantime [{phase}]  |  {_record_summary(ctx)}")
    print(f"Model {MODEL} (effort {EFFORT})  |  conversation {conv_id}")
    print("Synthetic patient. Demo only. Not medical advice.  Ctrl-C to quit.\n")
    _print_events(events)

    while True:
        try:
            text = input("\nRobert> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        if text in ("quit", "exit"):
            return
        reply, turn_events = run_turn(conv_id, history, text, phase)
        print()
        _print_events(turn_events)
        print(f"\nMeantime> {reply}")


if __name__ == "__main__":
    main()
