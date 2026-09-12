# Meantime

**A precision alert system for the gaps between appointments.**

> 📹 **Demo video:** _add link here_

![Meantime — five urgency levels, every one decided by a curated rule with a citation](docs/banner.svg)

---

## At a glance

### The medical process this handles

**Patient-initiated symptom triage across the peri-operative window for total knee replacement (TKA).**

A patient describes a symptom in their own words, at home, between appointments. The agent assigns one of five urgency levels, tells them what to do, and routes an escalation to the right clinician. It covers three phases of the same patient's care:

| phase | clinical territory it covers |
|---|---|
| **Before any procedure** | Undiagnosed knee complaint — septic joint screening, an unstable or locked knee, and persistent pain that needs a proper assessment. |
| **Waiting for surgery** | Pre-operative readiness: infection screening, skin integrity on the operative limb, dental and urinary sources, medication holds, fasting compliance, glycaemic control. Several of these mean the operation should be postponed. |
| **After discharge** | Post-operative recovery: DVT and pulmonary embolism surveillance, surgical site infection, wound complications, bleeding on anticoagulation, neurovascular compromise, falls, pain control, and separating all of that from expected recovery. |

Plus a general block that applies in every phase — chest pain, breathlessness, stroke signs, anaphylaxis, GI bleeding, and mental-health crisis.

**It does not diagnose, does not give doses, and does not replace clinical judgement.** It decides how urgent something is and who needs to hear about it. Nothing matching is never "you're fine" — it is `UNCERTAIN`, which means a phone number.

### How to run it

```bash
git clone https://github.com/Mahendhar-Saratha/meantime.git && cd meantime
python -m venv .venv && . .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                               # then add your ANTHROPIC_API_KEY
streamlit run app.py
```

Opens at `http://localhost:8501`. The rule engine runs without an API key — `python -m pytest tests -q` needs no network and no credentials. Full setup notes, the other entry points and one Streamlit gotcha are in [Running it](#running-it).

### Stack

| | |
|---|---|
| **Model** | Claude Sonnet 5 (`claude-sonnet-5`) via the Anthropic **Messages API** with tool use — a hand-written tool loop, 8 tools, no agent framework |
| **Language** | Python 3.11+ (built on 3.12) |
| **Storage** | SQLite via the standard library — no ORM |
| **Interface** | Streamlit — chat plus an evidence dashboard |
| **Live data** | `urllib` against five public endpoints: MedlinePlus Connect, the MedlinePlus web service, RxNav/RxNorm, openFDA, ClinicalTrials.gov. No API keys |
| **Tests** | pytest — 35 tests against the real rule file, no mocking |
| **Deliberately absent** | No LangChain, no vector database, no embeddings, no async. The urgency engine (`engine.py`) imports nothing but `re` — that is what makes it auditable |

---

## What we're solving

It's late. Something doesn't feel right. The hospital is behind you, the next appointment is weeks away, and whatever is happening in your body is happening **now**.

You have three options. All three fail you, in different ways.

**Search hands you the worst case, first.** Results are ranked by what's popular, not by what's likely for you. Two scrolls into any post-surgical symptom and you are reading about blood clots, sepsis and internal bleeding. You end up more frightened and no better informed, because none of it knows a single thing about you.

**A general assistant won't commit.** It is fluent, calm, and it ends where you began: *this could be normal, but it could also be serious — please consult your doctor.* It hedges because it genuinely has no basis to decide and no way to be held to an answer. So the triage stays yours to do, at 1am, in pain, alone.

**The emergency room will answer — and charges you a night, a bill, and your dignity for it.** Nobody wants to be the person who came in over a bruise. That fear of over-reacting is strongest in exactly the people who should be going.

So most people take the fourth option, the one nobody lists: **wait, and don't sleep.**

That is the moment this is built for. The question at 11pm is not *what is this symptom* — search already does that, badly. It is **how worried should I be, right now, given everything about me**. Nothing a patient can reach at that hour will answer it, because answering it requires their record, and none of those tools has it.

Getting it wrong costs in both directions. People who need care talk themselves out of it — *"swelling is normal after knee surgery"* is perfectly true, and exactly the wrong answer when the swelling is in the calf and you are on a blood thinner. People who are recovering normally lose a night in an ER over bruising that was expected. The same sentence needs a different answer depending on the procedure, the day, the medications, and what you said last week.

**Meantime answers it.** It has already read the discharge summary. It commits to one of five urgency levels, tells you what to do, and sends the escalation to a named human. When it can't tell, it says so and gives you the nurse line — it never guesses to make you feel better.

## The patient in this build

Robert Hale, 67. Right knee replacement four days ago, home since Thursday, on apixaban — a blood thinner — to stop a clot forming. His wound check is in twelve days. His surgeon gave him a nine-item warning list on discharge, which is in a folder somewhere.

It's 11pm and his calf hurts.

Everything below — every rule, every demo path, every screenshot — runs against his record. He is entirely synthetic, as are his clinicians and every 555-prefixed phone number.

## How it works

| | |
|---|---|
| **1. It already has the record** | Baseline history plus the booking or the discharge summary, merged. `post_op_day`, `on_anticoagulant` and days-to-next-appointment are computed, not typed. |
| **2. Claude reads what he wrote** | And turns it into a structured symptom report using a fixed 94-term clinical vocabulary. Understanding the language is the *only* thing the model does here. |
| **3. A deterministic engine picks the level** | 44 curated rules, each with a rationale, a patient-facing action and a citation. Pure functions, no network, no model — the same input gives the same answer every time. |
| **4. The system acts** | Messages the right human for that phase, schedules a check-in, writes the diary entry. |
| **5. When no rule covers it, it goes and finds out** | Live MedlinePlus and FDA lookups for what he actually said — without ever letting a fetched page change the level. |

**In three sentences:** The model understands language. Rules decide urgency. Humans see every escalation.

## Why this is different

**It knows who is asking.** Not a generic patient — *this* one, on day four, on apixaban, with a surgeon's warning list and three things he already reported this week.

**The urgency decision can be audited.** Every level traces to a numbered line in a JSON file with a source link. A surgeon can read the rule; a patient can read the rule. The model is not permitted to set the level at all, so it cannot talk itself into "probably fine".

**"I don't know" is a supported answer.** Nothing matching is never reassurance — it is `UNCERTAIN`, which means a phone number. Most symptom checkers have no way to say this, so they guess fluently.

**A live lookup can never lower an alert.** Asked about nightly leg cramps, it fetched MedlinePlus, reported that they are common and unrelated to surgery, and *still* held the helpline — because the rules could not sort it out. That single behaviour is the difference between this and a search box.

**It remembers.** "The pain isn't controlled" is a message to the team the first time and a same-day call the second, because something already reported that hasn't settled is not a first report.

**And you can watch it narrow.** The dashboard shows the rule filter re-run on every message: `44` → `31` for this phase → `2` triggered by what he just said → `1` surviving, naming the rule that got ruled out and the word that did it.

A point-by-point comparison against general assistants is in [Why not just ask ChatGPT](#why-not-just-ask-chatgpt) below.

## The interface

Two views over the same session, switched at the top. It **opens on Conversation** deliberately: the dashboard is *about* the product, the chat *is* it, and a dashboard opened cold has no verdict, no escalations and an empty inbox. The chat's empty state does the differentiating work immediately — *"You are day 4 after your right total knee arthroplasty. I have your discharge summary here."*

So that you don't have to choose, a thin strip under the masthead carries the credibility signal into the chat view: how many rules are in force, the evidence sources behind them, and that the content is live. Once a verdict exists it narrows to the rule that actually answered and only that rule's sources — `URGENT · decided by rule K1 · MedlinePlus NHS AAOS` — with one button through to the full dashboard.

**Conversation** is the product: chat, with a sidebar that pins the urgency badge and keeps everything else one click away — why this answer (the rules that fired, with their sources), the possibilities list, the full record, the actions taken.

**Dashboard** is the case for the system. It answers the question a judge, a surgeon or a compliance reviewer actually asks: *what can this thing say, and where did it get it from?*

- **Where Robert is · Current verdict · Escalations to a human · Rules in force** — the session in four numbers.
- **The arc** — the three phases, with how many rules are live in each. The current one is marked.
- **The rule filter** — the narrowing, re-run on every message and shown as it happens: `44` in the library → `44` for this procedure → `31` at this phase → `2` triggered by what he just said → `1` surviving the exclusions → the verdict. When a rule is ruled out, it says which word did it: *M1 (MONITOR) ruled out by `calf_pain`*.
- **Rules that can fire right now** — all 31 for this phase, ranked by severity, each with its rationale, its triggers and a source chip. The ones the last message put in play float to the top, marked **FIRED** or **RULED OUT**. Nothing is hidden behind the model.
- **Evidence base** — every source, with how many rules cite it and a link to the original.
- **Care team inbox** — the actual messages the humans received, with who got them and how fast.
- **Session activity** — every tool call in order.
- **Live from the source** — see below.

---

## When the rules don't cover it

The 44 curated rules are the safety floor, not the ceiling. Robert can say anything, and most of what a worried person says at 11pm isn't in any rule file.

So when `assess_urgency` comes back **UNCERTAIN**, the agent calls `lookup_guidance` — a live MedlinePlus search for whatever he actually raised, plus the FDA label if it's a medicine — and answers from what comes back, tied to his record. It also calls `patient_history` when something is *still* going or *back*, because a symptom already reported and not settled is not a first report.

A real exchange, unedited:

> **Robert:** *my leg keeps cramping at night, it wakes me up*
>
> `assess_urgency` → **UNCERTAIN** · no rule matched
> `lookup_guidance("leg cramps night")` → live MedlinePlus → *Muscle Cramps*
>
> **Meantime:** *"MedlinePlus says nighttime leg cramps are common, sudden muscle spasms… But that's just general background. It doesn't change what I told you: the rules came back unable to sort this out from here, so the helpline call still stands. You're 4 days out and on apixaban, and calf pain is specifically on your surgeon's warning list."*

It fetched the reassuring page and **still refused to reassure**. That is the entire architecture in one answer: a general symptom checker would have stopped at "common and harmless."

Two invariants make this reliable rather than hopeful, both enforced in `agent.py`, not in the prompt:

- `needs_assessment` — a turn that ends without running the rules is sent back to run them.
- `needs_lookup` — a turn that ends UNCERTAIN without looking anything up is sent back to look. The promise is that when the rules don't cover something the system goes and finds out; a prompt rule alone kept breaking that promise in testing.

**And a lookup can never move the level.** Not up, not down. The tool result says so, the prompt says so, and the level on the badge comes only from the engine.

### It watches, not just answers

`data/prior_contacts.json` seeds what Robert told Meantime on previous days. The engine has a `symptom_recurring` condition, and rule K8 uses it:

| | |
|---|---|
| *"the pain isn't controlled"* — first time | **CONTACT_TEAM** — message the team, they'll call in 24–48h |
| *"the pain still isn't controlled, same as I told you yesterday"* | **URGENT** — K8 escalates on recurrence; call the on-call line today |

That's the difference between a symptom checker and an alert system: the second answer is different because of the first one.

---

## Live content, local decision

The rules are hand-curated and deterministic. The evidence around them is not: the dashboard queries five public health APIs at page load, keyed on this patient's own ICD-10 codes and medications. No API keys, no registration.

| endpoint | what it gives us |
|---|---|
| **MedlinePlus Connect** (NIH/NLM) | Feed it `Z96.651` — the code actually on Robert's discharge summary — and it returns the patient-education page an EHR would surface: *Knee Replacement*. `Z79.01` returns *Blood Thinners*. Switch phase and the codes change, so the content changes. |
| **MedlinePlus web service** (NIH/NLM) | Health-topic summaries for the concepts the rules cite — deep vein thrombosis, surgical wound infection. |
| **RxNav / RxNorm** (NIH/NLM) | Real RxCUIs for his medications. Apixaban is `1364430`. |
| **openFDA** (FDA) | The live drug label. Apixaban's **boxed warning** — *"premature discontinuation increases the risk of thrombotic events"* — is the FDA's own text, and it is exactly why rule K11 exists. |
| **ClinicalTrials.gov v2** | Studies recruiting now for knee osteoarthritis. |

**What is deliberately not live: the urgency decision.**

No public API publishes machine-readable post-operative red-flag thresholds keyed by procedure and severity — which is why `red_flags.json` is hand-curated with citations in the first place. And even if one existed, putting a network call in the safety path would mean the answer to *"is this an emergency"* depends on someone else's uptime, and stops being reproducible. The engine stays deterministic, offline and auditable. The evidence around it is live.

Everything is cached to `data/cache/` with a TTL, so the demo runs with the network unplugged and public infrastructure isn't hammered. Each panel is marked **LIVE**, **CACHED**, **STALE** or **UNREACHABLE**, and **Refresh** forces a real network round-trip so you can prove the calls are real.

AAOS OrthoInfo and the NHS publish no open API, so rules citing them link to the page instead. That's an honest limitation, not an oversight.

---

## Are the rules actually dynamic?

Two different things get called that word, and the honest answer is different for each.

**What applies is recomputed on every message.** The rule set narrows five times against what the patient just said, and the dashboard shows it happening. For *"my knee is swollen and my right calf hurts"*:

```
44   rules in the library
44   apply to this procedure        · knee replacement
31   apply at this phase            · after discharge
 2   triggered by what he just said · calf_pain, knee_swelling     K1 · M1
 1   survive the exclusions         · M1 ruled out by calf_pain    K1
→    URGENT via K1
```

Change the phase and it narrows differently — 31 after discharge, 19 waiting for surgery, 12 before any treatment. Say something else and the last two rows change again. None of that is precomputed.

**The library itself is static, and that is deliberate.** All 44 rules are hand-written and reviewed. Nothing in the running system creates, edits or activates a rule, and no rule changes because of what a patient typed.

That is not a missing feature. A system that drafts its own triage thresholds from patient language will drift, and it will drift in one direction — toward reassurance, because reassurance is what people respond well to and nobody complains about being wrongly told they were fine. The failure is silent, and it is the only failure in this domain that actually hurts someone.

**The correct middle is the next thing to build.** When live lookups keep firing for something the rules don't cover, draft a **candidate rule** from the fetched source, mark it `UNREVIEWED`, surface it on the dashboard with its provenance — and never let it fire until a clinician approves it. The library grows out of real patient language; the approval gate is the point, not the obstacle.

So: **the filter is dynamic, the authoring is governed.** Same split as everywhere else here — live content, local decision.

---

## Three phases, one architecture

The same worry arrives at three different points, and the right answer is different at each. Meantime covers all three with one engine and one rule file.

| phase | where Robert is | what changes |
|---|---|---|
| **Before any treatment** | Nothing booked. His knee hurts and he wants to understand it. | No care team exists. Escalation means his GP, urgent care or 911. The agent also returns **possibilities** — curated things to ask a clinician about. |
| **Waiting for surgery** | Right knee replacement booked, 6 days out. | Some problems mean the operation should be **postponed** — an infection, a nick in the skin on that leg, a dental abscess, eating after the fasting cutoff. That's the surgical team's call, and they need to hear it today, not on the morning. |
| **After discharge** | Home on post-op day 4, on apixaban. | Clot, infection and wound rules apply; the surgeon's on-call line is the escalation path. |

The demo point: **the same sentence gets three different, correct answers.**

> *"My knee aches and it's stiff."*
> → before treatment: **CONTACT_TEAM** (N3) — nobody has ever assessed this, see a GP
> → waiting for surgery: **MONITOR** (P10) — the knee gets worse while you wait; that's the arthritis you're having treated
> → after discharge: **MONITOR** (M7) — stiffness is expected as the new joint settles

Nothing in the agent's prompt knows this. It falls out of the `phase` field on each rule.

---

## Architecture

```
┌──────────────┐   chat    ┌──────────────┐  tool calls  ┌────────────────────┐
│  Streamlit   │ ────────▶ │  agent.py    │ ───────────▶ │  tools.py          │
│  app.py      │ ◀──────── │  (Claude,    │ ◀─────────── │  get_patient_ctx   │
│  chat +      │  replies  │   tool loop) │   results    │  assess_urgency ───┼──▶ engine.py + red_flags.json
│  sidebar     │           └──────────────┘              │  explore_possibil. ┼──▶ engine.py + conditions.json
│              │ ◀──────────────── reads ───────────────  │  message_care_team│
└──────┬───────┘                                         │  schedule_checkin  │──▶ SQLite (meantime.db)
       │                                                 │  log_symptom       │
       │  dashboard only, never in the safety path       └────────────────────┘
       └──▶ sources.py ──▶ MedlinePlus Connect · MedlinePlus topics · RxNav
                           openFDA labels · ClinicalTrials.gov   (cached to disk)
```

| stage | who | what |
|---|---|---|
| 0 Intake | `db.py` | `patient_baseline.json` — the record before anything happened |
| 1 Phase record | `db.py` | `scheduled_procedure.json` *or* `discharge_summary.json`, merged onto the baseline |
| 2 Symptom capture | Claude | converse, ask at most 2 clarifying questions, produce a structured `symptom_report` |
| 3 Match | `engine.py` (no LLM) | run the rules for this phase against the report + context |
| 4 Decide | `engine.py` | apply the decision policy below |
| 5 Explain + act | Claude + tools | explain in plain language, grounded in the record; call the action tools |

**The language model never decides urgency.** It extracts symptoms, asks clarifying questions, explains results and calls tools. Every urgency decision comes from a line in `data/red_flags.json` that you can read, with a source link.

**And it is not trusted to remember to ask.** A prompt rule saying "always call `assess_urgency`" failed twice in testing — the model stopped to ask a clarifying question and left the patient with no verdict, once on a hot swollen knee with a fever. So the loop checks: a turn that ends without an assessment is sent back to produce one (`needs_assessment` in [agent.py](agent.py)). Safety invariants belong in code, not in prose.

---

## Why not just ask ChatGPT

| | ChatGPT / a general symptom checker | Meantime |
|---|---|---|
| Knows the patient | Not unless you paste it in | Baseline history plus whichever record applies to the phase. Knows it is post-op **day 4** and that he is on **apixaban** |
| Decides urgency | A paragraph of hedging, different every time | One of five fixed levels, from a rule you can read |
| Shows its reasoning | Opaque | Rule ID, rationale, and a link to MedlinePlus / NHS / AAOS |
| When it doesn't know | Guesses plausibly | `UNCERTAIN` → the nurse helpline. Never "probably fine" |
| Lists possibilities | Generates them, fluently, sometimes wrongly | Looks them up in a curated file, and never says which one it is |
| Does anything about it | Nothing | Messages the right human for that phase, schedules a check-in, writes a diary entry |

---

## Decision policy

1. Any `EMERGENCY` rule match → `EMERGENCY`. Immediately. No more questions.
2. Otherwise the highest-ranked rule that matched with `high` confidence wins.
3. `MONITOR` is only allowed when a MONITOR rule explicitly matched. **Nothing matched ≠ fine.** Nothing matched = `UNCERTAIN` → helpline.
4. If the only matches are `low` confidence (a required qualifier is missing, e.g. "swelling" with no location), the agent may ask **one** clarifying question, re-run the engine, and if still low → `UNCERTAIN`.
5. Patient context modifies rules through `modifiers` in `red_flags.json` (e.g. `on_anticoagulant` upgrades bleeding to an emergency). Modifiers live in data, never in the prompt.
6. `EMERGENCY`, `URGENT` and `CONTACT_TEAM` always also fire `message_care_team`. Humans see every escalation — and *which* human depends on the phase.
7. A `MONITOR` result always includes a three-item watch list from the matched rule, and schedules a check-in.

### The five levels

| level | meaning | what the patient is told |
|---|---|---|
| `EMERGENCY` | life or limb threat | Call 911 now. Don't drive yourself. |
| `URGENT` | needs a clinician today | Post-op: the surgeon's on-call line. Pre-op: surgical scheduling. No procedure: urgent care or the ER. |
| `CONTACT_TEAM` | not dangerous, needs a human | The agent messages the care team, the surgical team, or the GP depending on phase. |
| `MONITOR` | expected | Self-care from the patient's own instructions, plus a 3-item watch list. |
| `UNCERTAIN` | no confident match | "I can't tell from here." Then a phone number. |

**The rule that matters most:** nothing matching is not reassurance. `test_4_nothing_matched_is_uncertain_not_fine` enforces it.

**There is deliberately no `MONITOR` rule for the before-treatment phase.** With no procedure and no clinician's baseline, "this is expected, do nothing" is not something this system is entitled to say. The floor there is "book a GP appointment."

---

## The rules

44 rules in [`data/red_flags.json`](data/red_flags.json):

| block | count | phase | what |
|---|---|---|---|
| G1–G9 | 9 | **any** | Chest pain, breathlessness, stroke signs, anaphylaxis, crisis, GI bleeding. These do not care what stage of treatment you are at. |
| P1–P10 | 10 | pre-op | Infection, skin breaks on the operative leg, dental abscess, UTI, broken fast, missed medication holds, falls, blood sugar — plus what is expected while waiting. |
| K1–K12 | 12 | post-op | DVT, wound infection, bleeding on a blood thinner, vascular/nerve changes, falls, pain control. |
| M1–M10 | 10 | post-op | Expected recovery, each with a three-item watch list. |
| N1–N3 | 3 | before treatment | Hot swollen joint, a knee that won't bear weight, and persistent knee pain that needs a proper assessment. |

Every rule carries a plain-English rationale, a patient-facing action, and a source:

- **MP** — MedlinePlus, *Knee joint replacement – discharge* (NIH/NLM, public domain) — https://medlineplus.gov/ency/patientinstructions/000170.htm
- **NHS** — Dorset County Hospital NHS FT, *Post Knee Replacement Symptom Checker* — https://dchft.nhs.uk/leaflets/post-knee-replacement-symptom-checker/ and NHS, *Recovering from a knee replacement* — https://www.nhs.uk/tests-and-treatments/knee-replacement/recovery/
- **AAOS** — OrthoInfo, *Total Knee Replacement* — https://orthoinfo.aaos.org/en/treatment/total-knee-replacement
- **DC** — the patient's own discharge summary warning list
- **CRISIS** — 988 Suicide & Crisis Lifeline — https://988lifeline.org/

Adding a procedure means adding rules with a new `applies_to` key. Adding a phase means a new `phase` value. No Python changes either way.

## The possibilities list

In the before-treatment phase only, the agent also calls `explore_possibilities`, which looks up [`data/conditions.json`](data/conditions.json) — 8 curated knee conditions, each with what makes it more likely, what makes it less likely, and the usual next step.

Three deliberate constraints, all tested:

1. **It is not generated.** The model does not invent possibilities; it reads them from a file with sources. If nothing matches, it must say so rather than fill the gap.
2. **It carries no probability.** There is no score, confidence or likelihood field — `test_possibilities_never_claims_a_probability` asserts none can appear. The list is ordered only by how much of what the patient described each condition involves, and the UI says so.
3. **The urgency verdict still wins.** A hot swollen knee with a fever returns `URGENT` *and* a possibilities list, and the reply leads with "today, not later."

The `more_likely_if` / `less_likely_if` lines are handed to the patient as the questions a clinician uses to tell these apart. The software never evaluates them, because it can't.

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

`DEMO_TODAY` pins "today" so the demo behaves identically whenever it runs — with the default, Robert is on post-op day 4. The pre-op phase is pinned separately, at 6 days before surgery, by `demo_days_until_surgery` in `data/scheduled_procedure.json`.

```bash
streamlit run app.py                # the UI
python agent.py post_op             # the same agent in the terminal, with tool calls printed
python agent.py pre_op              # or no_procedure
python -m pytest tests -q           # 28 rule-engine tests
python db.py                        # print all three phase contexts
python sources.py                   # hit the five public APIs and print what comes back

**One gotcha while developing:** Streamlit re-runs `app.py` on every save, but it keeps *imported* modules in memory. Edit `engine.py`, `sources.py`, `db.py`, `agent.py` or `ui.py` and you must restart the server, or you will be running the old code against the new file — including signature mismatches that look like impossible errors.
```

---

## The demo paths

Switch phase in the sidebar; each switch resets the conversation.

**After discharge**

| | say this | what happens |
|---|---|---|
| **A — escalates** | *"my right calf is really sore and kind of swollen, is that normal after surgery?"* | Orange: **URGENT**, rule K1. Connects it to the blood thinner, gives the on-call number, messages the care team. |
| **B — reassures** | *"the incision is itchy and there's some bruising down my shin"* | Green: **MONITOR**, rules M2/M4. Self-care, a three-item watch list, a check-in and a diary entry. |
| **C — never guesses** | *"I just feel kind of off today"* | Grey: **UNCERTAIN**. Nothing matched, so it gives the nurse helpline instead of an opinion. |

**Waiting for surgery**

| | say this | what happens |
|---|---|---|
| **D — protects the operation** | *"I've had a sore throat since yesterday and I feel a bit hot. Surgery is next week, should I just push through?"* | Orange: **URGENT**, rule P1. "Postponing is far safer than going ahead" — and the message goes to surgical scheduling, not the on-call surgeon. |
| **E — the small thing that isn't** | *"I nicked my right shin shaving and it's a bit red around it"* | Orange: **URGENT**, rule P2. A break in the skin on the operative leg, on the leg getting a new joint. It also points out the instructions said not to shave it. |

**Before any treatment**

| | say this | what happens |
|---|---|---|
| **F — explains without diagnosing** | *"my right knee has been aching for months, it's stiff when I get up and it's worse going down stairs"* | Yellow: **CONTACT_TEAM**, rule N3, plus four possibilities from the curated list with what makes each more or less likely. Never names one. |
| **G — urgency still wins** | *"my knee is hot and swollen and I've got a fever"* | Orange: **URGENT**, rule N1. Possibilities are still listed, but the answer is "today". |

Path B is the interesting one: "swelling is normal after knee surgery" (rule M1) is exactly right — right up until the swelling is in the *calf*, where M1's `excludes` stops it firing and K1 takes over. That single field is the difference between reassurance and a same-day clot check.

---

## Landscape

| category | examples | what they do well | where they stop |
|---|---|---|---|
| **General symptom checkers** | Ada, Buoy, K Health, WebMD, NHS 111 online | Broad "what might this be" coverage for the public | Know nothing about *this* patient's surgery, meds, or post-op day. Same answer for a 25-year-old and a 67-year-old on a blood thinner four days after a knee replacement. |
| **General AI assistants with health features** | ChatGPT Health, Claude | Can read records; excellent at explaining | Explicitly not for diagnosis or treatment; no commitment to an urgency decision; opaque reasoning, so no hospital can sign off on it; no actions into a care team; nothing stops it talking itself into "probably fine". |
| **Enterprise post-discharge agents** | Hippocratic AI and similar voice-agent vendors | Outbound scheduled calls, medication review, nurse callback; strong patient ratings | Agent-initiated on *its* timetable. The 11pm "my calf hurts" moment is patient-initiated and falls between calls. Closed, and the urgency logic isn't visible to the patient or auditable by an outsider. |
| **Post-surgical remote monitoring** | Force Therapeutics and other RTM/RPM tools | Structured check-ins, exercise adherence, clinic dashboards | Form-driven, not conversational. Built for the clinic's view of a population, not for a worried person describing something unexpected in their own words. |
| **Pre-operative prep tools** | Hospital pre-op portals, paper instruction sheets | Tell the patient what to do before surgery | One-directional. They cannot answer "I've got a sore throat, does that matter?" — which is the question that decides whether an operation should be postponed. |

**The gap:** patient-initiated, at the moment of worry, grounded in the patient's own record for the phase they are actually in, matched against a list with public provenance, with a deterministic urgency decision the patient *and* a surgeon can read, and actions that land in the right human's queue.

**In one line:** everyone else either knows the patient or shows their reasoning. Meantime does both, and never guesses.

**Honestly:** this is not a claim to out-build a funded company in six hours. It is a demonstration of a safety architecture for patient-facing triage — the model understands language, curated rules decide urgency, humans see every escalation — that any of those products could adopt, and most don't expose today.

---

## Safety and limitations

- **The patient is synthetic.** Robert Hale, his clinicians, his phone numbers (all 555-prefixed) and his dates are fictional. No real patient data is in this repository.
- **The rules are not clinically validated.** They are adapted from public patient-education material written for patients, not from a licensed triage protocol. They would need clinical sign-off before any real use.
- **The possibilities list is not a diagnosis** and is not ordered by likelihood. It is a curated set of things to raise with a clinician, and the software is deliberately incapable of choosing between them.
- **This is not medical advice**, and the app says so on every screen.
- **It covers one procedure** (total knee replacement) and has no EHR integration.
- **The failure mode is over-referral**, which is the safe direction: an unmatched symptom becomes a phone call, never reassurance.
- Every escalation reaches a human. `MONITOR` requires an explicit rule. Unknown means a phone number.

---

## What's next

1. **MCP server** — expose the eight tools over the Model Context Protocol so the same agent works from any MCP client.
2. **The check-in actually firing** — a scheduled follow-up turn instead of a row in a table.
3. **A care-team view** — the second half of the loop: what the nurse sees when a message arrives, across all three phases.
4. **A second procedure** — a `hip` block in `red_flags.json`. The phase machinery is already procedure-agnostic.
5. **Real record ingestion** — the baseline-plus-record merge is already the shape an EHR export would take.
