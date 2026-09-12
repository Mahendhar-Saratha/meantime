# MEANTIME — Build Plan

**A post-discharge "is this an emergency?" agent for the gap between leaving the hospital and the next appointment.**

This document is the complete specification for a six-hour solo hackathon build. Everything below is a decision already made.

> **Build notes (decisions taken during implementation, recorded here so the code and the spec agree):**
> 1. **`days_to_next_appointment`** — §4.3 says "earliest follow-up after today", which is physical therapy in 2 days, but §14 and the pitch both say "next appointment in 12 days" (the wound check). The context exposes both `next_followup` (earliest, including PT) and `next_clinical_followup` (excludes therapy); `days_to_next_appointment` and the sidebar use the clinical one.
> 2. **Compound modifier conditions** — K5 needs `on_anticoagulant` AND `has_symptom:bleeding_not_stopping`, which the §7.1 condition list doesn't express. A modifier's `"if"` accepts either a string or a list of strings, where a list means AND.
> 3. **Derived qualifiers** — `engine.derive_qualifiers()` turns structured fields the model already filled in (`symptom.location`, `symptom.side`, `vitals.temp_f`) into qualifier strings, so a report with `location: "right calf"` counts as `location:calf` even if the model forgot the qualifier list. Deterministic bookkeeping, not language understanding; test case 5 still returns UNCERTAIN/low because that report has no location or side.
> 4. **Prompt rule 7** — added: every turn in which the patient describes how he feels must include an `assess_urgency` call, including when nothing maps to the vocabulary (empty symptoms list). Without it the model asked a clarifying question and ended the turn with no assessment, so Path C produced no badge.
> 5. **`max_tokens` 2000, not 1200** — thinking tokens count against the budget on Sonnet 5, and a truncated EMERGENCY message is a real failure. `EFFORT` defaults to `medium` for demo latency.
>
> **Extension after the first build (three phases — see the README for the product framing):**
>
> 6. **`phase` on every rule** — `any` / `pre_op` / `post_op` / `no_procedure`, filtered alongside `applies_to`. The G rules are `any`, because chest pain does not care what stage of treatment you are at; their rationales were rewritten to stop assuming surgery had happened. K and M rules stay `post_op`. New blocks: P1–P10 (pre-operative readiness) and N1–N3 (before any treatment). 44 rules total.
> 7. **`LEVEL_ACTIONS` is keyed by phase**, and the prompt's level-action lines are generated from `engine.level_action()`, so the badge and the prompt cannot drift apart. Who you call changes with the phase: on-call surgeon, surgical scheduling, or a GP.
> 8. **`data/scheduled_procedure.json` and `data/conditions.json`** — the pre-op booking record (mirroring the discharge summary's shape) and the curated possibilities list. `get_patient_context(phase=...)` merges the right one onto the baseline. Pre-op "today" is pinned by `demo_days_until_surgery`, so the countdown is identical on every run.
> 9. **The "always assess" invariant moved from the prompt into the loop.** Prompt rule 7 failed twice in live testing — once on a hot swollen knee with a fever, where the model asked a clarifying question and ended the turn with no verdict at all. `run_turn` now checks `needs_assessment(events)` and sends the model back if the rules were never run. A safety invariant enforced only by prose is not enforced.
> 10. **No `MONITOR` rule exists for `no_procedure`**, deliberately. Without a procedure and without a clinician's baseline, "this is expected, do nothing" is not a statement this system is entitled to make. The floor there is "book a GP appointment."

---

## 0. Instructions

- **Stack is fixed:** Python 3.11+, `anthropic` SDK (direct Messages API with tool use), SQLite (stdlib `sqlite3`), Streamlit. No frameworks beyond these. No LangChain, no async, no FastAPI.
- **Build order is fixed** (section 13). Rule engine first, with tests. Agent loop second, in the terminal. Streamlit last.
- **The LLM never decides urgency.** The rule engine (`engine.py`) does. The model extracts symptoms, asks clarifying questions, explains results, and calls tools. If you find yourself putting urgency logic in the prompt, stop and put it in `red_flags.json` instead.
- **"No match" is never "you're fine."** It is `UNCERTAIN` → nurse helpline. This is the product's core safety rule.
- **Keep it small.** Four Python files, two JSON data files, one rules file.
- **Public repo.** `.env` is gitignored before the first commit. Never print the API key. Synthetic data only.
- **All data is synthetic.** Patient, clinicians, phone numbers (555-prefixed), and dates are fictional.

---

## 1. Pitch

Robert had a knee replacement four days ago. His follow-up is in two weeks. It's 11pm and his calf hurts. His options are Google, ChatGPT, or the ER.

Meantime is the agent that lives in that gap. It has already read his discharge summary. It knows he is on a blood thinner. When he describes what he feels, it matches his words against a curated warning list built from MedlinePlus, the NHS, and the American Academy of Orthopaedic Surgeons, tells him exactly how urgent it is and what to do next, and messages his care team. When it can't tell, it doesn't guess. It gives him the nurse line.

**Three sentences for judges:** The model understands language. Rules decide urgency. Humans see every escalation.

---

## 2. Architecture

```
┌──────────────┐   chat    ┌──────────────┐  tool calls  ┌──────────────────┐
│  Streamlit   │ ────────▶ │  agent.py    │ ───────────▶ │  tools.py        │
│  app.py      │ ◀──────── │  (Claude,    │ ◀─────────── │  get_patient_ctx │
│  chat +      │  replies  │   tool loop) │   results    │  assess_urgency ─┼──▶ engine.py + red_flags.json
│  sidebar     │           └──────────────┘              │  message_care_team│
│              │ ◀──────────────── reads ──────────────  │  schedule_checkin│──▶ SQLite (meantime.db)
└──────────────┘                                        │  log_symptom     │
                                                        └──────────────────┘
```

**Pipeline per conversation:**

| stage | who | what |
|---|---|---|
| 0 Intake | `db.py` seed | load `data/patient_baseline.json` into SQLite |
| 1 Append discharge | `db.py` seed | load `data/discharge_summary.json`; merge into one patient context; compute `post_op_day` |
| 2 Symptom capture | Claude | converse, ask ≤ 2 clarifying questions, produce a structured `symptom_report` |
| 3 Match | `engine.py` (no LLM) | run `red_flags.json` against report + context → `{level, matched_rules, confidence}` |
| 4 Decide | `engine.py` policy | apply decision policy (section 6) |
| 5 Explain + act | Claude + tools | plain-language explanation grounded in the record; call action tools |

---

## 3. Repository layout

```
meantime/
├── README.md
├── PLAN.md                  (this file)
├── requirements.txt         anthropic, python-dotenv, streamlit, pytest
├── .env                     ANTHROPIC_API_KEY=...   (gitignored)
├── .gitignore               .env, *.db, __pycache__/, .venv/
├── data/
│   ├── patient_baseline.json
│   ├── discharge_summary.json
│   └── red_flags.json
├── db.py                    schema, seed, small query helpers
├── engine.py                rule engine + decision policy (pure functions, no I/O)
├── tools.py                 tool implementations + TOOL_SCHEMAS list for the API
├── agent.py                 system prompt, tool loop, run_turn()
├── app.py                   Streamlit UI
└── tests/
    └── test_engine.py       the 8 cases in section 8.4
```

---

## 4. Synthetic patient data

`data/patient_baseline.json` is the record before surgery: Robert Hale, born 1959-03-14, hypertension, type 2 diabetes, hyperlipidemia, right knee osteoarthritis; on lisinopril, metformin and atorvastatin; penicillin allergy; nurse helpline 616-555-0142.

`data/discharge_summary.json` is appended after surgery: right total knee arthroplasty (`procedure_code: "tka"`) on 2026-09-08, discharged 2026-09-10, surgeon Dr. Marcus Ellery (on-call 616-555-0199). Discharge medications include **apixaban 2.5 mg twice daily** (`class: "anticoagulant"`) and oxycodone (`class: "opioid"`). Carries the surgeon's 9-item warning list and three follow-up appointments.

### 4.3 Merged patient context (what `get_patient_context` returns)

Built in `db.py` by merging the two records, with computed fields:

- `post_op_day` = `DEMO_TODAY − surgery_date` in days. `DEMO_TODAY` is read from `.env` (default `2026-09-12`, so post_op_day = 4). **Pinned** so the demo behaves identically whenever the video is recorded.
- `on_anticoagulant` = any discharge med with `class == "anticoagulant"` → `true`
- `on_opioid` = `true`
- `procedure_code` = `"tka"`
- `days_to_next_appointment` = days until the next *clinical* follow-up (see build note 1)
- `helpline` = nurse helpline, `on_call` = surgeon on-call phone

---

## 5. Urgency levels (fixed vocabulary)

Use these exact strings everywhere: JSON, engine, prompt, DB, UI.

| level | rank | meaning | patient-facing action | UI colour |
|---|---|---|---|---|
| `EMERGENCY` | 4 | life or limb threat | **Call 911 now.** Don't drive yourself. | red |
| `URGENT` | 3 | needs a clinician today | Call the surgeon's on-call line **now** (616-555-0199) or go to urgent care / ER today. | orange |
| `CONTACT_TEAM` | 2 | not dangerous, needs the team | Agent messages the care team; they'll call within 24–48h. | yellow |
| `MONITOR` | 1 | expected recovery | Self-care from the discharge instructions + a specific 3-item watch-list. | green |
| `UNCERTAIN` | 0 | no confident match | "I can't tell from here. Please call the nurse helpline: 616-555-0142." | grey |

---

## 6. Decision policy

1. Any `EMERGENCY` rule match → `EMERGENCY`. Immediately. No more questions.
2. Otherwise the highest-ranked rule that matched with `high` confidence wins.
3. `MONITOR` is only allowed when a MONITOR rule explicitly matched. **Nothing matched ≠ fine.** Nothing matched = `UNCERTAIN` → helpline.
4. If the only matches are `low` confidence (a required qualifier is missing, e.g. "swelling" with no location), the agent may ask **one** clarifying question, re-run the engine, and if still low → `UNCERTAIN`.
5. Patient context modifies rules through `modifiers` in `red_flags.json` (e.g. on_anticoagulant upgrades bleeding). Modifiers live in data, never in the prompt.
6. `EMERGENCY`, `URGENT`, and `CONTACT_TEAM` always also fire `message_care_team` with the structured report. Humans see every escalation.
7. A MONITOR result always includes a watch-list (from the matched rule's `watch_for`) and schedules a check-in.

---

## 7. `data/red_flags.json` — the distinguished list

Sources:

- **MP** — MedlinePlus, *Knee joint replacement – discharge* (NIH/NLM, public domain): https://medlineplus.gov/ency/patientinstructions/000170.htm
- **NHS** — Dorset County Hospital NHS FT, *Post Knee Replacement Symptom Checker*: https://dchft.nhs.uk/leaflets/post-knee-replacement-symptom-checker/ and NHS, *Recovering from a knee replacement*: https://www.nhs.uk/tests-and-treatments/knee-replacement/recovery/
- **AAOS** — OrthoInfo, *Total Knee Replacement*: https://orthoinfo.aaos.org/en/treatment/total-knee-replacement
- **DC** — the patient's own discharge summary warning list
- **CRISIS** — 988 Suicide & Crisis Lifeline: https://988lifeline.org/

### 7.1 Rule schema

```json
{
  "id": "K1",
  "applies_to": "tka" | "general",
  "level": "EMERGENCY" | "URGENT" | "CONTACT_TEAM" | "MONITOR",
  "triggers": ["canonical_symptom", ...],        // ANY of these present → candidate match
  "requires": ["qualifier", ...],                 // ANY one present → high confidence; none → low (optional)
  "excludes": ["canonical_symptom", ...],         // if ANY present, rule does not apply (optional)
  "modifiers": [ {"if": "<condition>" | ["<cond>", ...], "level": "<LEVEL>"} ],   // optional; a list means AND
  "rationale": "one plain-English sentence the agent may paraphrase",
  "action": "what the patient should do, in patient language",
  "watch_for": ["...", "...", "..."],             // MONITOR rules only: 3 items that would change the answer
  "source": "MP" | "NHS" | "AAOS" | "DC" | "CRISIS" | "MP,NHS",
  "source_url": "https://..." | null
}
```

Modifier conditions the engine supports: `on_anticoagulant`, `on_opioid`, `post_op_day_gt_3`, `post_op_day_le_3`, `has_symptom:<name>`, `severity_severe`, `duration_gt_24h`, `temp_f_ge_101`. An unknown condition raises, so a typo fails loudly instead of silently never firing.

### 7.2 General rules (9)

| id | level | triggers | modifiers |
|---|---|---|---|
| G1 | EMERGENCY | chest_pain, chest_pressure, chest_tightness | — |
| G2 | EMERGENCY | shortness_of_breath, difficulty_breathing | — |
| G3 | EMERGENCY | coughing_blood | — |
| G4 | EMERGENCY | fainting, severe_dizziness, rapid_or_irregular_heartbeat | — |
| G5 | EMERGENCY | face_droop, arm_weakness, speech_difficulty, sudden_confusion, severe_headache | — |
| G6 | EMERGENCY | swelling_face_lips_tongue, throat_tightness | — |
| G7 | EMERGENCY | suicidal_thoughts, self_harm_thoughts | special handling: 988 + 911, stay with the person, message care team |
| G8 | URGENT | vomiting_blood, black_stool | `on_anticoagulant` → EMERGENCY |
| G9 | URGENT | bleeding_not_stopping | `on_anticoagulant` → EMERGENCY |

### 7.3 Knee replacement rules (12, `applies_to: "tka"`)

| id | level | triggers | requires / excludes / modifiers |
|---|---|---|---|
| K1 | URGENT | calf_pain, calf_swelling, calf_warmth, calf_tenderness, leg_swelling_one_sided | requires `location:calf` OR `one_sided` |
| K2 | CONTACT_TEAM | fever, chills | requires `temp_reading_given`; `temp_f_ge_101` → URGENT; `has_symptom:chills` → URGENT |
| K3 | URGENT | wound_drainage_purulent, wound_opening, wound_drainage_increasing | — |
| K4 | URGENT | wound_redness_spreading, red_streaks, wound_hot | — |
| K5 | URGENT | bleeding_soaking_dressing | `on_anticoagulant` + `has_symptom:bleeding_not_stopping` → EMERGENCY |
| K6 | URGENT | foot_cold, foot_pale_or_blue, foot_numb, cannot_move_foot | — |
| K7 | URGENT | fall, cannot_bear_weight, knee_deformity, sudden_severe_knee_pain | — |
| K8 | CONTACT_TEAM | pain_uncontrolled | calf pain is handled by K1, which outranks this |
| K9 | CONTACT_TEAM | constipation | — |
| K10 | CONTACT_TEAM | vomiting, cannot_keep_fluids_down | `duration_gt_24h` → URGENT |
| K11 | CONTACT_TEAM | missed_anticoagulant_dose | — |
| K12 | CONTACT_TEAM | rash, itching_widespread, hives | excludes swelling_face_lips_tongue, throat_tightness, difficulty_breathing |

### 7.4 MONITOR rules (10, expected recovery)

Each carries exactly three `watch_for` items.

| id | triggers | excludes / modifiers |
|---|---|---|
| M1 | knee_swelling, thigh_swelling, shin_swelling, leg_swelling_mild | excludes all five calf / one-sided symptoms |
| M2 | bruising | — |
| M3 | wound_redness_mild | excludes wound_redness_spreading, wound_hot, red_streaks, fever |
| M4 | incision_itching, incision_tightness, numbness_near_scar | — |
| M5 | wound_drainage_clear_small | excludes purulent/increasing; `post_op_day_gt_3` → CONTACT_TEAM |
| M6 | knee_warmth | excludes calf_warmth, fever, wound_redness_spreading |
| M7 | stiffness, clicking, difficulty_bending | — |
| M8 | low_grade_temp | excludes chills, wound_drainage_purulent, wound_redness_spreading |
| M9 | nausea_mild, drowsiness | excludes vomiting, cannot_keep_fluids_down, sudden_confusion |
| M10 | low_mood, anxiety_about_recovery, poor_sleep | excludes suicidal_thoughts, self_harm_thoughts (→ G7) |

**Note:** `excludes` on M1 is what makes "calf" beat "swelling is normal". Test case 1 verifies it.

---

## 8. `engine.py`

### 8.1 Canonical symptom vocabulary

71 names, held in `data/red_flags.json` under `vocabulary` and injected into the system prompt from there, so the rules file is the single source of truth. The model normalises patient language to these names; the engine only compares strings. **No NLP in the engine.**

### 8.2 `symptom_report` shape

```json
{
  "symptoms": [
    {"name": "calf_swelling", "side": "right", "location": "calf", "severity": "moderate", "onset": "today", "trend": "worse"}
  ],
  "qualifiers": ["location:calf", "one_sided"],
  "vitals": {"temp_f": null},
  "duration_hours": 6,
  "missed_meds": false,
  "patient_words": "my right calf is really sore and kind of swollen"
}
```

`severity` ∈ mild | moderate | severe. `trend` ∈ better | same | worse. Unknown fields are `null`, never guessed.

### 8.3 Algorithm

```
LEVEL_RANK = {UNCERTAIN:0, MONITOR:1, CONTACT_TEAM:2, URGENT:3, EMERGENCY:4}

def assess(report, ctx, rules) -> Assessment:
    names = {s.name for s in report.symptoms}
    quals = set(report.qualifiers) | derive_qualifiers(report)
    matches = []
    for r in rules:
        if r.applies_to not in ("general", ctx.procedure_code): continue
        if not (set(r.triggers) & names): continue
        if r.excludes and (set(r.excludes) & names): continue
        confidence = "high"
        if r.requires and not any(q in quals for q in r.requires): confidence = "low"
        level = r.level
        for m in r.modifiers:
            if all(condition(c, ctx, report) for c in listify(m["if"])): level = m["level"]
        matches.append(Match(rule=r, level=level, confidence=confidence))

    if not matches:  return Assessment("UNCERTAIN", [], "none")
    high = [m for m in matches if m.confidence == "high"]
    if not high:     return Assessment("UNCERTAIN", matches, "low")   # agent may ask ONE question
    return Assessment(top_level, sorted(high, by rank desc), "high")
```

`Assessment` returns: `level`, `level_action`, `matched` (id, level, confidence, rationale, action, watch_for, source, source_url for each), `top_rule`, `confidence`, `watch_for`, `helpline`, `on_call`, and `actions_required` (`message_care_team` for rank ≥ 2, `schedule_checkin` for MONITOR).

### 8.4 Test cases

| # | report symptoms (+ctx) | expected level | expected top rule |
|---|---|---|---|
| 1 | `calf_swelling`, `calf_pain`, quals `location:calf`, `one_sided` | URGENT | K1 (M1 must NOT fire — excludes) |
| 2 | `chest_tightness`, `shortness_of_breath` | EMERGENCY | G1 |
| 3 | `incision_itching`, `bruising` | MONITOR | M4 or M2, with watch_for |
| 4 | `[]` (patient said "I feel kind of off") | UNCERTAIN, confidence none | — |
| 5 | `leg_swelling_one_sided` with no qualifiers | UNCERTAIN, confidence low | K1 low → clarify |
| 6 | `bleeding_soaking_dressing`, `bleeding_not_stopping`, ctx on_anticoagulant | EMERGENCY | K5/G9 via modifier |
| 7 | `fever` temp_f 101.8, qual `temp_reading_given`, `wound_redness_spreading` | URGENT | K2 (via temp modifier) + K4 |
| 8 | `wound_drainage_clear_small`, ctx post_op_day 4 | CONTACT_TEAM | M5 via post_op_day_gt_3 |

Plus guards: derived qualifiers rescue a report with no explicit qualifier list; EMERGENCY outranks a MONITOR match in the same report; the same drainage on day 2 stays MONITOR; every modifier condition in the rules file is implemented; every MONITOR rule carries three watch items; every escalation above MONITOR fires `message_care_team`.

---

## 9. `db.py` — SQLite

File `meantime.db`, created on startup if missing, seeded from the two JSON files.

```sql
patients            (patient_id PK, name, dob, sex, json_baseline TEXT)
discharge_records   (encounter_id PK, patient_id, procedure_code, surgery_date, json_discharge TEXT)
conversations       (conv_id PK, patient_id, started_at)
symptom_reports     (id PK, conv_id, created_at, json_report TEXT)
assessments         (id PK, conv_id, created_at, level, matched_rule_ids TEXT, confidence, json_full TEXT)
care_team_messages  (id PK, conv_id, created_at, level, summary TEXT, sent_to, eta_hours, status DEFAULT 'sent')
checkins            (id PK, conv_id, created_at, due_at, question TEXT, status DEFAULT 'scheduled')
symptom_diary       (id PK, patient_id, conv_id, created_at, entry TEXT, level)
```

Helpers: `init_db()`, `seed()`, `get_patient_context(patient_id)`, `insert_*`, `list_*_for_conv(conv_id)`, `reset_demo()` (deletes conversation-scoped rows so each demo path starts clean; keeps patients and discharge).

---

## 10. `tools.py`

| tool | input | output | side effect |
|---|---|---|---|
| `get_patient_context` | `{}` | merged context (section 4.3) | none |
| `assess_urgency` | `{symptom_report}` | `Assessment` as dict | insert into `symptom_reports` and `assessments` |
| `message_care_team` | `{level, summary, symptoms:[...]}` | `{message_id, sent_to, eta_hours}` | insert into `care_team_messages` (eta: URGENT/EMERGENCY → 0, CONTACT_TEAM → 24) |
| `schedule_checkin` | `{hours_from_now, question}` | `{checkin_id, due_at}` | insert into `checkins` |
| `log_symptom` | `{entry, level}` | `{diary_id}` | insert into `symptom_diary` |

`assess_urgency`'s description is the load-bearing one: *"You MUST call this before telling the patient how urgent anything is. Never state urgency without it."*

---

## 11. `agent.py`

### 11.1 Loop

A manual tool loop over `client.messages.create`, max 6 iterations, breaking when `stop_reason != "tool_use"`. Text is collected from **every** iteration, not just the last — the explanation usually arrives in the same assistant message as the tool call that follows it.

- `MODEL = "claude-sonnet-5"` (read from `.env` as `MODEL`). Sonnet 5 is fast, cheap and strong at tool use, and demo latency matters.
- `events` is what the sidebar renders. Kept in `st.session_state`.
- On the first turn the app pre-calls `get_patient_context` and injects it as the first user message, so the model never has to ask for the record.

### 11.2 System prompt

Held verbatim in `agent.py` as `SYSTEM_PROMPT_TEMPLATE`, with the canonical symptom vocabulary and qualifier list interpolated from `data/red_flags.json`. Its core: listen, ask at most two clarifying questions, convert to a structured report using only canonical names, **call `assess_urgency` before saying anything about urgency**, explain using the matched rule's rationale and the patient's own record, then take the action for that level. Never diagnose. Never say something is normal unless a MONITOR rule matched. Never downgrade what the rules returned.

---

## 12. `app.py` — Streamlit UI

Two columns: chat (main) and sidebar.

**Sidebar:** patient card (name, age, procedure, **post-op day N** in large type, blood-thinner chip, next appointment and days away) · the urgency badge with its action line, coloured per section 5 · the matched rules with rationale and source links (the provenance moment) · the list of actions taken with timestamps · a **Reset demo** button · the disclaimer.

**Main:** disclaimer banner, chat history, `st.chat_input`, and a "Checking against the warning list…" spinner.

---

## 13. Build order

1. Repo, `.gitignore` + `.env` before the first commit, `requirements.txt`, the three data files.
2. `engine.py` + `tests/test_engine.py` — all 8 cases pass before anything else is written.
3. `db.py` — printing the context shows `post_op_day: 4`, `on_anticoagulant: true`.
4. `tools.py`, `agent.py`, terminal REPL — Paths A, B, C work in the terminal with tool events printed.
5. `app.py` — all three paths work in the browser; the badge changes colour; the actions list fills.
6. README, disclaimer, copy polish.
7. Record the video. Push. Submit.

**Cut list if behind:** drop `log_symptom` and the diary; drop the reset button (restart Streamlit instead); keep the badge and the care-team message no matter what.

---

## 14. Demo script (≤ 3 minutes)

Pin `DEMO_TODAY=2026-09-12` (post-op day 4). Reset between paths.

**0:00–0:20 — Problem.** "Robert had a knee replacement four days ago. His follow-up is in two weeks. It's 11pm and something feels wrong. His options are Google, ChatGPT, or the ER."

**0:20–0:40 — Context.** Point at the sidebar: post-op day 4, apixaban, next appointment in 12 days. "The agent has already read his discharge summary. ChatGPT hasn't."

**0:40–1:30 — Path A (escalates).** Type: *"my right calf is really sore and kind of swollen, is that normal after surgery?"* Badge turns orange: URGENT. The agent explains the blood-thinner connection, tells him to call the on-call line now; the sidebar shows the care-team message and the MedlinePlus source link.

**1:30–2:15 — Path B (reassures).** Reset. Type: *"the incision is itchy and there's some bruising down my shin."* Badge turns green: MONITOR. Expected on day 4, the three-item watch list, a check-in scheduled and a diary entry.

**2:15–2:40 — Path C (never guesses).** Reset. Type: *"I just feel kind of off today."* Badge grey: UNCERTAIN. The helpline number instead of an opinion. Say out loud: "Nothing matched, so it doesn't guess. That's the rule."

**2:40–3:00 — Architecture.** "The model understands language. Rules decide urgency — every rule links to MedlinePlus, the NHS, or the AAOS. Humans see every escalation. Synthetic data."

---

## 15. README contents

Pitch · screenshot of Path A · architecture diagram and the three-sentence summary · "why not just ask ChatGPT" table · the decision policy verbatim · sources with links · run instructions · landscape and differentiation · safety and limitations · what's next. Video link near the top.

---

## 16. Stretch goals (only after the video is recorded)

1. **FastMCP wrapper** (~20 lines): expose the five tools as an MCP server so the same agent works from any MCP client.
2. **Simulated check-in turn**: a "Fast-forward 12 hours" button that fires the scheduled check-in question into the chat.
3. **Care-team view**: a second Streamlit page listing `care_team_messages` as a nurse would see them.
4. **Second procedure**: add a `hip` block to `red_flags.json` to prove the engine is procedure-agnostic.
5. ClinicalTrials.gov: a post-recovery "studies you might qualify for" note. Lowest priority.

---

## 17. Judge Q&A cheat sheet

- **"Why not let the model decide?"** Because I can show you the rule. Every urgency decision traces to a line in `red_flags.json` with a source link. The model can't talk itself into "probably fine."
- **"What about liability?"** Every escalation reaches a human. MONITOR requires an explicit rule. Unknown means helpline. The failure mode is over-referral, which is the safe direction.
- **"Does it scale beyond knees?"** Rules are keyed by procedure. Add a hip block and the same engine runs. The baseline-plus-discharge merge is procedure-agnostic.
- **"Is this real data?"** No. Fully synthetic patient. Rules adapted from public patient-education guidance and would need clinical sign-off before real use.
- **"Why an agent and not a chatbot?"** It reads a record, runs a rules tool, and takes actions — messages the team, schedules follow-ups, keeps a diary. The conversation is the interface; the actions are the product.

---

## 18. Landscape

| category | examples | what they do well | where they stop |
|---|---|---|---|
| **General symptom checkers** | Ada, Buoy, K Health, WebMD, NHS 111 online | Broad coverage of "what might this be" for the general public | Know nothing about *this* patient's surgery, meds, or post-op day. Same answer for a 25-year-old and a 67-year-old on a blood thinner four days after a knee replacement. |
| **General AI assistants with health features** | ChatGPT Health, Claude | Can read records; excellent at explaining | Explicitly "not intended for diagnosis or treatment"; no commitment to an urgency decision; reasoning is opaque, so no hospital can sign off on it; no actions into a care team; nothing stops it from talking itself into "probably fine." |
| **Enterprise post-discharge agents** | Hippocratic AI, similar voice-agent vendors | Outbound scheduled calls after discharge; medication review; nurse callback option; strong patient ratings | Agent-initiated and scheduled — it calls *you*, on its timetable. The 11pm "my calf hurts" moment is patient-initiated and falls between calls. Hospital-procured, closed, and urgency logic isn't visible to the patient or auditable by an outsider. |
| **Post-surgical remote monitoring platforms** | Force Therapeutics, other RTM/RPM tools for joint replacement | Structured check-in surveys, exercise adherence, dashboards for the clinic | Form-driven, not conversational. Designed for the clinic's view of the population, not for a worried person describing something unexpected in their own words. |

**The gap Meantime sits in:** patient-initiated, at the moment of worry, grounded in the patient's own discharge record, matched against a procedure-specific list with public provenance, with a deterministic urgency decision the patient (and a surgeon) can read, and actions that land in the care team's queue.

**The differentiation in one line:** *Everyone else either knows the patient or shows their reasoning. Meantime does both, and never guesses.*

**The honest framing:** Meantime is not a claim to out-build a funded company in six hours. It is a demonstration of a safety architecture for patient-facing triage — the model understands language, curated rules decide urgency, humans see every escalation — that any of those products could adopt, and that most of them don't expose today. The prototype proves the pattern on one procedure with three demo paths.

**What Meantime does not do:** it is not clinically validated; the rules are adapted from patient-education material, not a licensed triage protocol; it covers one procedure; it has no real EHR integration. All of that is "what's next," and all of it is compatible with the architecture.

---

## 19. Submission checklist

- [ ] `.env` gitignored; `git log -p | grep sk-ant` returns nothing
- [ ] `pytest` green
- [ ] Screenshot saved at `docs/path-a.png` (referenced by the README)
- [ ] Three paths recorded in one ≤ 3-minute video
- [ ] README has video link, pitch, diagram, sources, run steps, disclaimer
- [ ] Repo public
- [ ] Submitted before 3:00
