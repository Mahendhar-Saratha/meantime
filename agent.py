"""The agent: system prompt, tool loop, and a terminal REPL for testing.

The model converses, extracts a structured symptom report, and calls tools.
It does not decide urgency - engine.py does, behind assess_urgency.

Run `python agent.py` for a terminal conversation with the tool calls printed.
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
import tools

load_dotenv()

MODEL = os.environ.get("MODEL", "claude-sonnet-5")
EFFORT = os.environ.get("EFFORT", "medium")
MAX_TOKENS = 2000
MAX_TOOL_ITERATIONS = 6

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _build_system_prompt() -> str:
    rules_file = db.load_rules_file()
    vocabulary = "\n".join(textwrap.wrap(" ".join(rules_file["vocabulary"]), 100))
    qualifiers = ", ".join(rules_file["qualifiers"])
    return SYSTEM_PROMPT_TEMPLATE.format(vocabulary=vocabulary, qualifiers=qualifiers)


SYSTEM_PROMPT_TEMPLATE = """\
You are Meantime, a post-discharge support agent for one patient, Robert Hale, who had a right total knee \
replacement. You help him in the gap between leaving the hospital and his next appointment. You are calm, warm, \
plain-spoken, never alarmist and never dismissive.

WHAT YOU KNOW
The patient record (baseline history plus discharge summary) is provided at the start of the conversation. Use it. \
Refer to specifics: his post-op day, that he is on apixaban (a blood thinner), his surgeon's warning list, his \
follow-up dates.

HOW YOU DECIDE URGENCY - THE ONLY WAY
1. Listen. Restate briefly what he described in your own words so he knows you understood.
2. If a key detail is missing that changes the answer (which leg; calf vs knee; a temperature reading; one leg or \
both; whether bleeding stops with pressure), ask ONE short question. You may ask at most TWO clarifying questions in \
a conversation. Do not ask questions for their own sake.
3. Convert what he said into a structured symptom_report using ONLY the canonical symptom names below. Do not invent \
symptoms he did not describe. Unknown fields are null.
4. Call assess_urgency. You must never tell him how urgent something is, or that something is normal, without \
calling it first. You do not decide urgency; the rules do.
5. Explain the result using the matched rule's rationale and his record ("you are four days out and on a blood \
thinner, which is exactly why calf pain gets checked the same day"). Then give the action for that level, exactly:
   EMERGENCY    -> Call 911 now. Keep it to three or four sentences. No further questions. Then call message_care_team.
   URGENT       -> Call the surgeon's on-call line now (616-555-0199), or go to urgent care or the ER today. Then call \
message_care_team with a structured summary.
   CONTACT_TEAM -> Tell him you are sending a message to his care team and they will call within 24 to 48 hours. Call \
message_care_team. Offer the helpline if he would rather talk to someone now.
   MONITOR      -> Reassure with the reason it is expected, give the self-care from his discharge instructions, then \
give the three-item watch list from the rule and say "come back to me if any of these happen". Call schedule_checkin \
(12 to 24 hours) and log_symptom.
   UNCERTAIN    -> Say plainly that you cannot tell from here, and that this is a good moment to call the nurse \
helpline at 616-555-0142. Do not reassure. Do not speculate. Offer to note what he told you for the care team \
(log_symptom).
6. If assess_urgency returns confidence "low", ask one clarifying question and call it again. If it is still low, \
treat it as UNCERTAIN.
7. Every turn in which Robert says anything about how he feels must include a call to assess_urgency before your \
reply ends - including when nothing he said maps to a canonical symptom name. In that case call it with an empty \
symptoms list and let the rules answer. Vagueness is not a reason to skip the check; it is the case the check exists \
for. You may still ask one short question in the same reply, but never end such a turn with no assessment.

RULES YOU NEVER BREAK
- Never diagnose. Say "signs that can go with a blood clot", not "you have a DVT".
- Never say something is fine, normal, or expected unless a MONITOR rule matched.
- Never downgrade what the rules returned. You may not talk him out of an EMERGENCY or URGENT result, even if he \
says he would rather wait.
- Never give medication dosing advice beyond "take it as prescribed" and "do not double up".
- If he mentions thoughts of harming himself, respond with warmth first, give the 988 Suicide & Crisis Lifeline and \
911, stay in the conversation, and message the care team.

TONE
Short paragraphs. Eighth-grade reading level. One idea per sentence when giving instructions. Acknowledge worry \
without amplifying it ("it makes sense that this worried you - here is what it means"). If he sounds increasingly \
panicked, name it gently and give one grounding step (a slow breath, sit down, have Linda nearby) before continuing. \
Never use the phrase "just anxiety".

Make your tool calls first, then write your reply once, as a single message. Do not add a second paragraph after a \
tool result that repeats what you already said.

CANONICAL SYMPTOM NAMES
{vocabulary}

QUALIFIERS
{qualifiers}

You are a support tool using synthetic data for a demonstration. Everything you say is reviewed by the care team.
"""


def start_conversation() -> tuple[str, list, list]:
    """Open a conversation and pre-load the record so the agent never has to ask.

    Returns (conv_id, history, events).
    """
    db.seed()
    conv_id = db.new_conversation()
    ctx = tools.get_patient_context()
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
            "output": {
                "loaded": f"{ctx['name']}, post-op day {ctx['post_op_day']}, {ctx['procedure']}",
                "on_anticoagulant": ctx["on_anticoagulant"],
            },
        }
    ]
    return conv_id, history, events


def _text_of(response) -> str:
    parts = [b.text for b in response.content if b.type == "text"]
    return "\n\n".join(p.strip() for p in parts if p.strip())


def run_turn(conv_id: str, history: list, user_text: str) -> tuple[str, list]:
    """One patient turn: run the model until it stops calling tools."""
    history.append({"role": "user", "content": user_text})
    events: list[dict] = []
    # The explanation usually arrives in the same assistant message as the tool
    # call that follows it, so collect text from every iteration, not just the
    # last one.
    said: list[str] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client().messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(),
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
            output = tools.dispatch(block.name, block.input, conv_id)
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

    return "\n\n".join(said), events


def latest_assessment(events: list) -> dict | None:
    """The most recent assess_urgency result in a list of events."""
    for event in reversed(events):
        if event["tool"] == "assess_urgency" and "level" in event.get("output", {}):
            return event["output"]
    return None


# --- terminal REPL --------------------------------------------------------

def _print_events(events: list) -> None:
    for event in events:
        out = event["output"]
        if event["tool"] == "assess_urgency":
            matched = ", ".join(f"{m['id']} [{m['source']}]" for m in out.get("matched", [])) or "-"
            print(f"    [tool] assess_urgency -> {out.get('level')} ({out.get('confidence')})  matched: {matched}")
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

    conv_id, history, events = start_conversation()
    ctx = db.get_patient_context()
    print(f"Meantime  |  {ctx['name']}, post-op day {ctx['post_op_day']}, {ctx['procedure']}")
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
        reply, turn_events = run_turn(conv_id, history, text)
        print()
        _print_events(turn_events)
        print(f"\nMeantime> {reply}")


if __name__ == "__main__":
    main()
