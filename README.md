# Meantime

**The agent for the gap between leaving the hospital and the next appointment.**

> 📹 **Demo video:** _add link here_

Robert had a knee replacement four days ago. His follow-up is in two weeks. It's 11pm and his calf hurts. His options are Google, ChatGPT, or the ER.

Meantime is the agent that lives in that gap. It has already read his discharge summary. It knows he is on a blood thinner. When he describes what he feels, it matches his words against a curated warning list built from MedlinePlus, the NHS, and the American Academy of Orthopaedic Surgeons, tells him exactly how urgent it is and what to do next, and messages his care team. When it can't tell, it doesn't guess. It gives him the nurse line.

**Three sentences:** The model understands language. Rules decide urgency. Humans see every escalation.

![Meantime, Path A](docs/path-a.png)

---

## Architecture

```
┌──────────────┐   chat    ┌──────────────┐  tool calls  ┌───────────────────┐
│  Streamlit   │ ────────▶ │  agent.py    │ ───────────▶ │  tools.py         │
│  app.py      │ ◀──────── │  (Claude,    │ ◀─────────── │  get_patient_ctx  │
│  chat +      │  replies  │   tool loop) │   results    │  assess_urgency ──┼──▶ engine.py + red_flags.json
│  sidebar     │           └──────────────┘              │  message_care_team│
│              │ ◀──────────────── reads ───────────────  │  schedule_checkin│──▶ SQLite (meantime.db)
└──────────────┘                                         │  log_symptom     │
                                                         └───────────────────┘
```

| stage | who | what |
|---|---|---|
| 0 Intake | `db.py` | load `data/patient_baseline.json` — the record before surgery |
| 1 Append discharge | `db.py` | load `data/discharge_summary.json`, merge into one context, compute `post_op_day` |
| 2 Symptom capture | Claude | converse, ask at most 2 clarifying questions, produce a structured `symptom_report` |
| 3 Match | `engine.py` (no LLM) | run `data/red_flags.json` against the report + context |
| 4 Decide | `engine.py` | apply the decision policy below |
| 5 Explain + act | Claude + tools | explain in plain language, grounded in the record; call the action tools |

**The language model never decides urgency.** It extracts symptoms, asks clarifying questions, explains results and calls tools. Every urgency decision comes from a line in `data/red_flags.json` that you can read, with a source link.

---

## Why not just ask ChatGPT

| | ChatGPT / a general symptom checker | Meantime |
|---|---|---|
| Knows the patient | Not unless you paste it in | Baseline history + discharge summary, already loaded. Knows it is post-op **day 4** and that he is on **apixaban** |
| Decides urgency | A paragraph of hedging, different every time | One of five fixed levels, from a rule you can read |
| Shows its reasoning | Opaque | Rule ID, rationale, and a link to MedlinePlus / NHS / AAOS |
| When it doesn't know | Guesses plausibly | `UNCERTAIN` → the nurse helpline. Never "probably fine" |
| Does anything about it | Nothing | Messages the care team, schedules a check-in, writes a diary entry |

---

## Decision policy

1. Any `EMERGENCY` rule match → `EMERGENCY`. Immediately. No more questions.
2. Otherwise the highest-ranked rule that matched with `high` confidence wins.
3. `MONITOR` is only allowed when a MONITOR rule explicitly matched. **Nothing matched ≠ fine.** Nothing matched = `UNCERTAIN` → helpline.
4. If the only matches are `low` confidence (a required qualifier is missing, e.g. "swelling" with no location), the agent may ask **one** clarifying question, re-run the engine, and if still low → `UNCERTAIN`.
5. Patient context modifies rules through `modifiers` in `red_flags.json` (e.g. `on_anticoagulant` upgrades bleeding to an emergency). Modifiers live in data, never in the prompt.
6. `EMERGENCY`, `URGENT` and `CONTACT_TEAM` always also fire `message_care_team`. Humans see every escalation.
7. A `MONITOR` result always includes a three-item watch list from the matched rule, and schedules a check-in.

### The five levels

| level | meaning | what the patient is told |
|---|---|---|
| `EMERGENCY` | life or limb threat | Call 911 now. Don't drive yourself. |
| `URGENT` | needs a clinician today | Call the surgeon's on-call line now, or go to urgent care / the ER today. |
| `CONTACT_TEAM` | not dangerous, needs the team | The agent messages the care team; they call within 24–48h. |
| `MONITOR` | expected recovery | Self-care from the discharge instructions, plus a 3-item watch list. |
| `UNCERTAIN` | no confident match | "I can't tell from here. Please call the nurse helpline." |

**The rule that matters most:** nothing matching is not reassurance. `test_4_nothing_matched_is_uncertain_not_fine` is the test that enforces it.

---

## The rules

31 rules in [`data/red_flags.json`](data/red_flags.json) — 9 general, 12 knee-replacement-specific, 10 "this is expected" rules. Every rule carries a plain-English rationale, a patient-facing action, and a source:

- **MP** — MedlinePlus, *Knee joint replacement – discharge* (NIH/NLM, public domain) — https://medlineplus.gov/ency/patientinstructions/000170.htm
- **NHS** — Dorset County Hospital NHS FT, *Post Knee Replacement Symptom Checker* — https://dchft.nhs.uk/leaflets/post-knee-replacement-symptom-checker/ and NHS, *Recovering from a knee replacement* — https://www.nhs.uk/tests-and-treatments/knee-replacement/recovery/
- **AAOS** — OrthoInfo, *Total Knee Replacement* — https://orthoinfo.aaos.org/en/treatment/total-knee-replacement
- **DC** — the patient's own discharge summary warning list
- **CRISIS** — 988 Suicide & Crisis Lifeline — https://988lifeline.org/

Adding a procedure means adding rules with a new `applies_to` key. No Python changes.

---

## Running it

```bash
python -m venv .venv && . .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your ANTHROPIC_API_KEY
```

`.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
MODEL=claude-sonnet-5
DEMO_TODAY=2026-09-12
```

`DEMO_TODAY` pins "today" so the demo behaves identically whenever it runs — with the default, Robert is on post-op day 4.

```bash
streamlit run app.py       # the UI
python agent.py            # the same agent in the terminal, with tool calls printed
python -m pytest tests -q  # the rule engine tests
python db.py               # print the merged patient context
```

---

## The three demo paths

Reset between each with the sidebar button.

| | say this | what happens |
|---|---|---|
| **A — escalates** | *"my right calf is really sore and kind of swollen, is that normal after surgery?"* | Badge turns orange: **URGENT**, rule K1. The agent connects it to the blood thinner, gives the on-call number, and messages the care team. |
| **B — reassures** | *"the incision is itchy and there's some bruising down my shin"* | Badge turns green: **MONITOR**, rules M2/M4. Self-care, a three-item watch list, a check-in scheduled and a diary entry. |
| **C — never guesses** | *"I just feel kind of off today"* | Badge stays grey: **UNCERTAIN**. Nothing matched, so it gives the nurse helpline instead of an opinion. |

Path B is the interesting one: "swelling is normal after knee surgery" (rule M1) is exactly right — right up until the swelling is in the *calf*, where M1's `excludes` stops it firing and K1 takes over. That single field is the difference between reassurance and a same-day clot check.

---

## Landscape

Judges know this space. Here are the neighbours and the gap.

| category | examples | what they do well | where they stop |
|---|---|---|---|
| **General symptom checkers** | Ada, Buoy, K Health, WebMD, NHS 111 online | Broad "what might this be" coverage for the public | Know nothing about *this* patient's surgery, meds, or post-op day. Same answer for a 25-year-old and a 67-year-old on a blood thinner four days after a knee replacement. |
| **General AI assistants with health features** | ChatGPT Health, Claude | Can read records; excellent at explaining | Explicitly not for diagnosis or treatment; no commitment to an urgency decision; opaque reasoning, so no hospital can sign off on it; no actions into a care team; nothing stops it talking itself into "probably fine". |
| **Enterprise post-discharge agents** | Hippocratic AI and similar voice-agent vendors | Outbound scheduled calls, medication review, nurse callback; strong patient ratings | Agent-initiated on *its* timetable. The 11pm "my calf hurts" moment is patient-initiated and falls between calls. Closed, and the urgency logic isn't visible to the patient or auditable by an outsider. |
| **Post-surgical remote monitoring** | Force Therapeutics and other RTM/RPM tools | Structured check-ins, exercise adherence, clinic dashboards | Form-driven, not conversational. Built for the clinic's view of a population, not for a worried person describing something unexpected in their own words. |

**The gap:** patient-initiated, at the moment of worry, grounded in the patient's own discharge record, matched against a procedure-specific list with public provenance, with a deterministic urgency decision the patient *and* a surgeon can read, and actions that land in the care team's queue.

**In one line:** everyone else either knows the patient or shows their reasoning. Meantime does both, and never guesses.

**Honestly:** this is not a claim to out-build a funded company in six hours. It is a demonstration of a safety architecture for patient-facing triage — the model understands language, curated rules decide urgency, humans see every escalation — that any of those products could adopt, and most don't expose today. The prototype proves the pattern on one procedure with three demo paths.

---

## Safety and limitations

- **The patient is synthetic.** Robert Hale, his clinicians, his phone numbers (all 555-prefixed) and his dates are fictional. No real patient data is in this repository.
- **The rules are not clinically validated.** They are adapted from public patient-education material written for patients, not from a licensed triage protocol. They would need clinical sign-off before any real use.
- **This is not medical advice**, and the app says so on every screen.
- **It covers one procedure** (total knee replacement) and has no EHR integration.
- **The failure mode is over-referral**, which is the safe direction: an unmatched symptom becomes a phone call to a nurse, never reassurance.
- Every escalation is designed to reach a human. `MONITOR` requires an explicit rule. Unknown means helpline.

---

## What's next

1. **MCP server** — expose the five tools over the Model Context Protocol so the same agent works from any MCP client.
2. **The check-in actually firing** — a scheduled follow-up turn instead of a row in a table.
3. **A care-team view** — the second half of the loop: what the nurse sees when a message arrives.
4. **A second procedure** — a `hip` block in `red_flags.json` to prove the engine is procedure-agnostic. No Python changes required.
5. **Real record ingestion** — the baseline-plus-discharge merge is already the shape an EHR export would take.
