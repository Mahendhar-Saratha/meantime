"""Meantime look and feel: tokens, chrome, and the HTML components.

Kept out of app.py so the layout file stays readable. Nothing here knows
anything about rules or urgency - it renders what it is given.
"""

from __future__ import annotations

import html

WORDMARK = "Meantime"
TAGLINE = "A precision alert system for the hours you're on your own"
STRAPLINE = "The model understands language · Rules decide urgency · Humans see every escalation"

# --- palette --------------------------------------------------------------

LEVEL_COLOR = {
    "EMERGENCY": "#b3261e",
    "URGENT": "#c2610c",
    "CONTACT_TEAM": "#9a7b00",
    "MONITOR": "#1f7a3d",
    "UNCERTAIN": "#5f6874",
}
LEVEL_TINT = {
    "EMERGENCY": "#fdecea",
    "URGENT": "#fdf1e7",
    "CONTACT_TEAM": "#fbf6e0",
    "MONITOR": "#eaf5ed",
    "UNCERTAIN": "#f0f1f3",
}
LEVEL_TEXT = {
    "EMERGENCY": "EMERGENCY",
    "URGENT": "URGENT",
    "CONTACT_TEAM": "CONTACT TEAM",
    "MONITOR": "MONITOR",
    "UNCERTAIN": "UNCERTAIN",
}

# Each evidence source gets a monogram badge. Drawn in CSS rather than fetched,
# so the demo never depends on someone else's CDN being up.
SOURCE_BADGE = {
    "MP": ("M+", "#1a4b8c", "MedlinePlus", "NIH / US National Library of Medicine"),
    "NHS": ("NHS", "#005eb8", "NHS", "Dorset County Hospital NHS FT + NHS recovery guidance"),
    "AAOS": ("AO", "#d2601a", "AAOS OrthoInfo", "American Academy of Orthopaedic Surgeons"),
    "DC": ("DS", "#5b6472", "Discharge summary", "This patient's own paperwork"),
    "CRISIS": ("988", "#0f766e", "988 Lifeline", "Suicide & Crisis Lifeline"),
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');

:root {
  --ink:      #141a21;
  --ink-2:    #454f5c;
  --ink-3:    #7b8694;
  --paper:    #f7f6f3;
  --surface:  #ffffff;
  --line:     #e4e1db;
  --line-2:   #efece6;
  --accent:   #1f6f5c;
  --font: 'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* --- strip Streamlit chrome --- */
[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer { display: none !important; }
.stApp { background: var(--paper); font-family: var(--font); }
/* Set the family once and let it inherit. Do NOT blanket-override span/div:
   Streamlit draws its icons as ligature text in the Material Symbols font, so
   overriding those spans turns every chevron into the literal words
   "keyboard_arrow_down" and every avatar into "smart_toy". */
.stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp input, .stApp textarea, .stApp button,
[data-testid="stMarkdownContainer"] { font-family: var(--font); }
[data-testid="stIconMaterial"], .stApp span[class*="material"] {
  font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important; }
.block-container { padding-top: 1.1rem !important; padding-bottom: 6rem; max-width: 1500px; }
[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
hr { border-color: var(--line-2) !important; }

/* --- masthead --- */
.mt-head { display:flex; align-items:flex-start; justify-content:space-between; gap:1.5rem;
           padding:.1rem 0 .9rem; border-bottom:1px solid var(--line); margin-bottom:1.1rem; }
.mt-brand { display:flex; align-items:center; gap:.6rem; }
.mt-mark { color: var(--accent); display:flex; }
.mt-word { font-size:1.65rem; font-weight:700; letter-spacing:-.035em; color:var(--ink); line-height:1; }
.mt-tag { font-size:.84rem; color:var(--ink-2); margin-top:.28rem; letter-spacing:-.005em; }
.mt-strap { font-size:.72rem; color:var(--ink-3); margin-top:.2rem; letter-spacing:.01em; }
.mt-flag { font-size:.66rem; font-weight:600; letter-spacing:.09em; color:#8a6d00;
           background:#fbf6e0; border:1px solid #f0e4b8; border-radius:999px;
           padding:.3rem .7rem; white-space:nowrap; }

/* --- cards --- */
.mt-grid { display:grid; gap:.7rem; }
.mt-card { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:.9rem 1rem; }
.mt-label { font-size:.65rem; font-weight:600; letter-spacing:.1em; color:var(--ink-3);
            text-transform:uppercase; margin-bottom:.45rem; }
.mt-big { font-size:1.85rem; font-weight:600; letter-spacing:-.03em; color:var(--ink); line-height:1.05; }
.mt-sub { font-size:.76rem; color:var(--ink-3); margin-top:.2rem; line-height:1.35; }

/* --- section headings --- */
.mt-h { font-size:.95rem; font-weight:600; color:var(--ink); letter-spacing:-.01em;
        margin:1.4rem 0 .6rem; display:flex; align-items:baseline; gap:.5rem; }
.mt-h em { font-style:normal; font-size:.72rem; font-weight:500; color:var(--ink-3); }

/* --- level pill --- */
.mt-pill { display:inline-block; font-size:.66rem; font-weight:700; letter-spacing:.07em;
           padding:.22rem .5rem; border-radius:5px; white-space:nowrap; }

/* --- the arc --- */
.mt-arc { display:grid; grid-template-columns:repeat(3,1fr); gap:.7rem; }
.mt-step { background:var(--surface); border:1px solid var(--line); border-radius:12px;
           padding:.85rem .95rem; position:relative; }
.mt-step.on { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent); }
.mt-step-n { font-size:.62rem; font-weight:700; letter-spacing:.1em; color:var(--ink-3); }
.mt-step.on .mt-step-n { color:var(--accent); }
.mt-step-t { font-size:.95rem; font-weight:600; color:var(--ink); margin-top:.3rem; letter-spacing:-.015em; }
.mt-step-d { font-size:.74rem; color:var(--ink-3); margin-top:.25rem; line-height:1.4; }
.mt-step-r { font-size:.7rem; color:var(--ink-2); margin-top:.5rem;
             border-top:1px solid var(--line-2); padding-top:.45rem; }

/* --- source badges --- */
.mt-src { display:flex; align-items:center; gap:.6rem; padding:.55rem 0;
          border-bottom:1px solid var(--line-2); }
.mt-src:last-child { border-bottom:none; }
.mt-mono { width:34px; height:34px; border-radius:8px; display:flex; align-items:center;
           justify-content:center; color:#fff; font-size:.66rem; font-weight:700;
           letter-spacing:.02em; flex:0 0 34px; }
.mt-src-n { font-size:.8rem; font-weight:600; color:var(--ink); line-height:1.2; }
.mt-src-d { font-size:.69rem; color:var(--ink-3); line-height:1.3; margin-top:.1rem; }
.mt-src-c { margin-left:auto; font-size:.72rem; color:var(--ink-3); white-space:nowrap; }
.mt-src a { color:var(--accent); text-decoration:none; }
.mt-src a:hover { text-decoration:underline; }

/* --- inline source chip (used next to a rule) --- */
.mt-chip { display:inline-flex; align-items:center; gap:.28rem; font-size:.66rem; font-weight:600;
           color:#fff; border-radius:4px; padding:.1rem .35rem; margin-right:.25rem; }

/* --- rule rows --- */
.mt-rule { display:flex; gap:.65rem; padding:.55rem 0; border-bottom:1px solid var(--line-2); }
.mt-rule:last-child { border-bottom:none; }
.mt-rule-id { font-size:.7rem; font-weight:700; color:var(--ink-3); flex:0 0 30px; padding-top:.12rem; }
.mt-rule-b { flex:1; min-width:0; }
.mt-rule-t { font-size:.79rem; color:var(--ink); line-height:1.35; }
.mt-rule-m { font-size:.68rem; color:var(--ink-3); margin-top:.2rem; word-break:break-word; }

/* --- distribution bar --- */
.mt-bar { display:flex; height:9px; border-radius:5px; overflow:hidden; margin:.15rem 0 .5rem; }
.mt-bar span { display:block; }
.mt-key { display:flex; flex-wrap:wrap; gap:.75rem; font-size:.69rem; color:var(--ink-2); }
.mt-key i { width:8px; height:8px; border-radius:2px; display:inline-block; margin-right:.3rem; }

/* --- activity --- */
.mt-act { display:flex; gap:.65rem; padding:.5rem 0; border-bottom:1px solid var(--line-2); }
.mt-act:last-child { border-bottom:none; }
.mt-act-t { font-size:.69rem; color:var(--ink-3); flex:0 0 38px; padding-top:.1rem; font-variant-numeric:tabular-nums; }
.mt-act-n { font-size:.78rem; font-weight:600; color:var(--ink); }
.mt-act-d { font-size:.71rem; color:var(--ink-3); margin-top:.1rem; line-height:1.35; word-break:break-word; }

/* --- inbox --- */
.mt-msg { background:var(--surface); border:1px solid var(--line); border-left:4px solid var(--ink-3);
          border-radius:10px; padding:.75rem .9rem; margin-bottom:.55rem; }
.mt-msg-h { display:flex; align-items:center; gap:.5rem; margin-bottom:.35rem; flex-wrap:wrap; }
.mt-msg-w { font-size:.72rem; color:var(--ink-3); }
.mt-msg-b { font-size:.78rem; color:var(--ink-2); line-height:1.45; white-space:pre-wrap; }

/* --- empty state --- */
.mt-empty { background:var(--surface); border:1px dashed var(--line); border-radius:12px;
            padding:1.4rem; text-align:center; color:var(--ink-3); font-size:.8rem; }

/* --- chat --- */
[data-testid="stChatMessage"] { background:var(--surface); border:1px solid var(--line);
                                 border-radius:14px; padding:.85rem 1rem; }
[data-testid="stChatInput"] textarea { font-family:var(--font) !important; }

/* --- widgets --- */
[data-testid="stSidebar"] [data-testid="stExpander"] details { border:1px solid var(--line);
    border-radius:10px; background:var(--surface); }
[data-testid="stSidebar"] [data-testid="stExpander"] summary { font-size:.8rem; font-weight:600; }
</style>
"""

MARK_SVG = """
<span class="mt-mark">
<svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">
  <circle cx="16" cy="16" r="12.5" stroke="currentColor" stroke-width="2.6"
          stroke-linecap="round" stroke-dasharray="55 24" transform="rotate(-58 16 16)"/>
  <circle cx="16" cy="16" r="3.6" fill="currentColor"/>
</svg>
</span>
"""


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


# --- components -----------------------------------------------------------

def masthead() -> str:
    return f"""
<div class="mt-head">
  <div>
    <div class="mt-brand">{MARK_SVG}<div class="mt-word">{WORDMARK}</div></div>
    <div class="mt-tag">{TAGLINE}</div>
    <div class="mt-strap">{STRAPLINE}</div>
  </div>
  <div class="mt-flag">SYNTHETIC PATIENT · DEMO ONLY</div>
</div>
"""


def level_pill(level: str) -> str:
    return (
        f'<span class="mt-pill" style="background:{LEVEL_TINT[level]};color:{LEVEL_COLOR[level]}">'
        f"{LEVEL_TEXT[level]}</span>"
    )


def source_chip(code: str) -> str:
    mono, color, name, _ = SOURCE_BADGE.get(code, ("?", "#7b8694", code, ""))
    return f'<span class="mt-chip" style="background:{color}" title="{esc(name)}">{esc(mono)}</span>'


def source_chips(codes: str) -> str:
    return "".join(source_chip(c) for c in codes.split(","))


def stat_card(label: str, big: str, sub: str = "", color: str | None = None) -> str:
    style = f' style="color:{color}"' if color else ""
    return f"""
<div class="mt-card">
  <div class="mt-label">{esc(label)}</div>
  <div class="mt-big"{style}>{big}</div>
  <div class="mt-sub">{sub}</div>
</div>
"""


def stat_row(cards: list[str]) -> str:
    cols = f"repeat({len(cards)}, 1fr)"
    return f'<div class="mt-grid" style="grid-template-columns:{cols}">' + "".join(cards) + "</div>"


def heading(text: str, note: str = "") -> str:
    return f'<div class="mt-h">{esc(text)}<em>{esc(note)}</em></div>'


def arc(current: str, steps: list[dict]) -> str:
    out = []
    for i, step in enumerate(steps, 1):
        on = " on" if step["key"] == current else ""
        out.append(
            f"""<div class="mt-step{on}">
  <div class="mt-step-n">{'● NOW' if on else f'0{i}'}</div>
  <div class="mt-step-t">{esc(step['title'])}</div>
  <div class="mt-step-d">{esc(step['desc'])}</div>
  <div class="mt-step-r">{esc(step['record'])} · <b>{step['rules']}</b> rules in force</div>
</div>"""
        )
    return '<div class="mt-arc">' + "".join(out) + "</div>"


def distribution(counts: dict) -> str:
    total = sum(counts.values()) or 1
    bars, keys = [], []
    for level in ("EMERGENCY", "URGENT", "CONTACT_TEAM", "MONITOR"):
        n = counts.get(level, 0)
        if not n:
            continue
        bars.append(f'<span style="width:{n / total * 100:.1f}%;background:{LEVEL_COLOR[level]}"></span>')
        keys.append(
            f'<span><i style="background:{LEVEL_COLOR[level]}"></i>{LEVEL_TEXT[level]} {n}</span>'
        )
    return f'<div class="mt-bar">{"".join(bars)}</div><div class="mt-key">{"".join(keys)}</div>'


def source_list(entries: list[tuple]) -> str:
    """entries: (code, rule_count, url)"""
    rows = []
    for code, count, url in entries:
        mono, color, name, desc = SOURCE_BADGE.get(code, ("?", "#7b8694", code, ""))
        title = f'<a href="{url}" target="_blank">{esc(name)}</a>' if url else esc(name)
        rows.append(
            f"""<div class="mt-src">
  <div class="mt-mono" style="background:{color}">{esc(mono)}</div>
  <div style="min-width:0">
    <div class="mt-src-n">{title}</div>
    <div class="mt-src-d">{esc(desc)}</div>
  </div>
  <div class="mt-src-c">{count} rule{'s' if count != 1 else ''}</div>
</div>"""
        )
    return f'<div class="mt-card" style="padding:.35rem .9rem">{"".join(rows)}</div>'


def rule_rows(
    rules: list[dict],
    limit: int | None = None,
    highlight: set | None = None,
    ruled_out: set | None = None,
) -> str:
    """`highlight` fired on the last message; `ruled_out` was triggered and then
    excluded by something else the patient said."""
    shown = rules[:limit] if limit else rules
    highlight = highlight or set()
    ruled_out = ruled_out or set()
    rows = []
    for rule in shown:
        triggers = ", ".join(rule["triggers"][:4])
        if len(rule["triggers"]) > 4:
            triggers += f" +{len(rule['triggers']) - 4}"
        on = rule["id"] in highlight
        out = rule["id"] in ruled_out
        row_style = ""
        mark = ""
        if on:
            row_style = (
                ' style="background:#f4f8f6;border-left:3px solid var(--accent);'
                'padding-left:.55rem;margin-left:-.55rem"'
            )
            mark = (
                '<span style="font-size:.58rem;font-weight:700;letter-spacing:.07em;'
                'color:var(--accent);display:block;margin-top:.15rem">FIRED</span>'
            )
        elif out:
            row_style = (
                ' style="border-left:3px solid #c8ccd2;padding-left:.55rem;'
                'margin-left:-.55rem;opacity:.72"'
            )
            mark = (
                '<span style="font-size:.58rem;font-weight:700;letter-spacing:.07em;'
                'color:var(--ink-3);display:block;margin-top:.15rem">RULED OUT</span>'
            )
        rows.append(
            f"""<div class="mt-rule"{row_style}>
  <div class="mt-rule-id">{esc(rule['id'])}{mark}</div>
  <div class="mt-rule-b">
    <div class="mt-rule-t">{level_pill(rule['level'])} {esc(rule['rationale'])}</div>
    <div class="mt-rule-m">{source_chips(rule['source'])}{esc(triggers)}</div>
  </div>
</div>"""
        )
    return f'<div class="mt-card" style="padding:.35rem .9rem">{"".join(rows)}</div>'


def activity(items: list[tuple]) -> str:
    """items: (time, name, detail)"""
    if not items:
        return '<div class="mt-empty">Nothing yet. Start a conversation and every tool call lands here.</div>'
    rows = [
        f"""<div class="mt-act">
  <div class="mt-act-t">{esc(t)}</div>
  <div style="min-width:0"><div class="mt-act-n">{name}</div><div class="mt-act-d">{esc(detail)}</div></div>
</div>"""
        for t, name, detail in items
    ]
    return f'<div class="mt-card" style="padding:.35rem .9rem">{"".join(rows)}</div>'


def inbox(messages: list[dict]) -> str:
    if not messages:
        return (
            '<div class="mt-empty">No escalations yet.<br>'
            '<span style="font-size:.74rem">Every EMERGENCY, URGENT and CONTACT_TEAM result lands here, '
            "addressed to whichever human the phase calls for.</span></div>"
        )
    out = []
    for msg in messages:
        level = msg["level"] if msg["level"] in LEVEL_COLOR else "UNCERTAIN"
        eta = "immediate" if not msg["eta_hours"] else f"within {msg['eta_hours']}h"
        when = str(msg["created_at"]).replace("T", " ")[-8:-3]
        out.append(
            f"""<div class="mt-msg" style="border-left-color:{LEVEL_COLOR[level]}">
  <div class="mt-msg-h">{level_pill(level)}
    <span class="mt-msg-w"><b>{esc(msg['sent_to'])}</b></span>
    <span class="mt-msg-w" style="margin-left:auto">{esc(when)} · {esc(eta)}</span></div>
  <div class="mt-msg-b">{esc(msg['summary'])}</div>
</div>"""
        )
    return "".join(out)


def badge_block(level: str, action: str) -> str:
    """The pinned urgency badge in the sidebar."""
    return f"""
<div style="background:{LEVEL_TINT[level]};border-left:5px solid {LEVEL_COLOR[level]};
            padding:.7rem .8rem;border-radius:8px">
  <div style="color:{LEVEL_COLOR[level]};font-weight:700;letter-spacing:.07em;font-size:.72rem">
    {LEVEL_TEXT[level]}</div>
  <div style="margin-top:.35rem;font-size:.82rem;line-height:1.4;color:#2b333d">{esc(action)}</div>
</div>
"""


# --- live data components -------------------------------------------------

LIVE_STATUS = {
    "live": ("#1f7a3d", "LIVE"),
    "cached": ("#5f6874", "CACHED"),
    "stale": ("#c2610c", "STALE"),
    "failed": ("#b3261e", "UNREACHABLE"),
}


def live_chip(status: str) -> str:
    color, text = LIVE_STATUS.get(status, LIVE_STATUS["cached"])
    dot = f'<span style="width:6px;height:6px;border-radius:50%;background:{color};display:inline-block"></span>'
    return (
        f'<span style="display:inline-flex;align-items:center;gap:.3rem;font-size:.62rem;'
        f'font-weight:700;letter-spacing:.08em;color:{color}">{dot}{text}</span>'
    )


def api_bar(bundle: dict) -> str:
    parts = []
    for key, (name, _) in SOURCE_ENDPOINTS.items():
        status = bundle["endpoint_status"].get(key, "failed")
        color, _text = LIVE_STATUS.get(status, LIVE_STATUS["failed"])
        parts.append(
            f'<span style="display:inline-flex;align-items:center;gap:.35rem;border:1px solid var(--line);'
            f'background:var(--surface);border-radius:999px;padding:.28rem .6rem;font-size:.7rem;color:var(--ink-2)">'
            f'<span style="width:6px;height:6px;border-radius:50%;background:{color}"></span>{esc(name)}</span>'
        )
    return '<div style="display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.7rem">' + "".join(parts) + "</div>"


# name shown on the status chips; mirrors sources.ENDPOINTS
SOURCE_ENDPOINTS = {
    "medlineplus_connect": ("MedlinePlus Connect", ""),
    "medlineplus_search": ("MedlinePlus topics", ""),
    "rxnav": ("RxNav / RxNorm", ""),
    "openfda": ("openFDA labels", ""),
    "clinicaltrials": ("ClinicalTrials.gov", ""),
}


def education_card(entries: list[dict]) -> str:
    if not entries:
        return '<div class="mt-empty">No patient-education links returned.</div>'
    rows = []
    for entry in entries:
        topics = "".join(
            f'<div style="margin-top:.3rem"><a href="{t["url"]}" target="_blank" '
            f'style="color:var(--accent);text-decoration:none;font-size:.79rem;font-weight:600">{esc(t["title"])} ↗</a>'
            f'<div style="font-size:.71rem;color:var(--ink-3);line-height:1.4;margin-top:.1rem">{esc(t["summary"])}</div></div>'
            for t in entry["topics"]
        ) or '<div style="font-size:.72rem;color:var(--ink-3)">no match</div>'
        rows.append(
            f"""<div class="mt-src" style="display:block">
  <div style="display:flex;align-items:center;gap:.45rem">
    <span style="font-family:ui-monospace,monospace;font-size:.7rem;font-weight:700;color:var(--ink);
                 background:#eef1f6;border-radius:4px;padding:.12rem .35rem">ICD-10 {esc(entry['code'])}</span>
    <span style="font-size:.72rem;color:var(--ink-3)">{esc(entry['label'])}</span>
    <span style="margin-left:auto">{live_chip(entry['status'])}</span>
  </div>
  {topics}
</div>"""
        )
    return f'<div class="mt-card" style="padding:.35rem .9rem">{"".join(rows)}</div>'


def drug_cards(drugs: list[dict]) -> str:
    if not drugs:
        return '<div class="mt-empty">No medications to look up in this phase.</div>'
    rows = []
    for drug in drugs:
        rxcui = (
            f'<span style="font-family:ui-monospace,monospace;font-size:.68rem;color:var(--ink-3)">'
            f'RxCUI {esc(drug["rxcui"])}</span>'
            if drug.get("rxcui")
            else ""
        )
        warning = (
            f'<div style="font-size:.72rem;color:var(--ink-2);line-height:1.45;margin-top:.35rem;'
            f'border-left:3px solid #b3261e;padding-left:.55rem">{esc(drug["warning"])}</div>'
            if drug.get("warning")
            else '<div style="font-size:.72rem;color:var(--ink-3);margin-top:.3rem">No label section returned.</div>'
        )
        field = drug.get("warning_field", "").replace("_", " ").upper()
        rows.append(
            f"""<div class="mt-src" style="display:block">
  <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
    <b style="font-size:.82rem">{esc(drug['name'])}</b>{rxcui}
    <span style="font-size:.64rem;font-weight:700;letter-spacing:.07em;color:#b3261e">{esc(field)}</span>
    <span style="margin-left:auto">{live_chip(drug.get('status', 'cached'))}</span>
  </div>
  {warning}
</div>"""
        )
    return f'<div class="mt-card" style="padding:.35rem .9rem">{"".join(rows)}</div>'


def topic_cards(topics: list[dict]) -> str:
    if not topics:
        return '<div class="mt-empty">No health topics returned.</div>'
    rows = []
    for topic in topics:
        rows.append(
            f"""<div class="mt-src" style="display:block">
  <div style="display:flex;align-items:center;gap:.5rem">
    <a href="{topic['url']}" target="_blank" style="color:var(--accent);text-decoration:none;
       font-size:.8rem;font-weight:600">{esc(topic['title'])} ↗</a>
    <span style="margin-left:auto">{live_chip(topic['status'])}</span>
  </div>
  <div style="font-size:.71rem;color:var(--ink-3);line-height:1.45;margin-top:.2rem">{esc(topic['summary'])}</div>
</div>"""
        )
    return f'<div class="mt-card" style="padding:.35rem .9rem">{"".join(rows)}</div>'


def trial_rows(studies: list[dict]) -> str:
    if not studies:
        return '<div class="mt-empty">No recruiting studies returned.</div>'
    rows = []
    for study in studies:
        rows.append(
            f"""<div class="mt-src" style="display:block">
  <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
    <a href="{study['url']}" target="_blank" style="color:var(--accent);text-decoration:none;
       font-family:ui-monospace,monospace;font-size:.7rem;font-weight:700">{esc(study['nct'])} ↗</a>
    <span style="font-size:.64rem;font-weight:700;letter-spacing:.06em;color:#1f7a3d">{esc(study['status'])}</span>
    <span style="font-size:.66rem;color:var(--ink-3)">{esc(study['phase'])}</span>
  </div>
  <div style="font-size:.74rem;color:var(--ink-2);line-height:1.4;margin-top:.15rem">{esc(study['title'])}</div>
</div>"""
        )
    return f'<div class="mt-card" style="padding:.35rem .9rem">{"".join(rows)}</div>'


def split_note() -> str:
    return """
<div class="mt-card" style="border-left:4px solid var(--accent);background:#f4f8f6">
  <div style="font-size:.79rem;color:var(--ink-2);line-height:1.55">
    <b style="color:var(--ink)">Live content, local decision.</b>
    Everything on this panel is fetched from public NIH, FDA and NLM endpoints at page load, keyed on this
    patient's own ICD-10 codes and medications. The urgency verdict is not: no API publishes machine-readable
    post-operative red-flag thresholds, and putting a network call in the safety path would make
    <i>"is this an emergency"</i> depend on someone else's uptime. The rules stay deterministic, offline and
    auditable. The evidence around them is live.
  </div>
</div>
"""


def proof_strip(assessment: dict | None, rule_count: int, source_codes: list[str], live: str = "") -> str:
    """A thin line under the masthead on the chat view.

    The dashboard is the proof, but a judge should not have to go looking for it
    to know this is more than a model in a text box. Before any verdict this
    says what is standing behind the conversation; after one it says which rule
    answered and where it came from.
    """
    chips = "".join(source_chip(c) for c in source_codes)
    if assessment:
        rule = assessment.get("top_rule")
        left = (
            f'{level_pill(assessment["level"])}'
            f'<span style="font-size:.76rem;color:var(--ink-2);margin-left:.45rem">'
            f'{"decided by rule <b>" + esc(rule) + "</b>" if rule else "no rule matched"}</span>'
            f'<span style="margin-left:.5rem">{chips}</span>'
        )
    else:
        left = (
            f'<span style="font-size:.76rem;color:var(--ink-2)"><b>{rule_count}</b> rules in force</span>'
            f'<span style="margin-left:.55rem">{chips}</span>'
        )
    right = (
        f'<span style="font-size:.72rem;color:var(--ink-3)">{esc(live)}</span>' if live else ""
    )
    return (
        '<div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;'
        'background:var(--surface);border:1px solid var(--line);border-radius:10px;'
        'padding:.45rem .75rem;margin-bottom:.8rem">'
        f"{left}<span style='margin-left:auto'>{right}</span></div>"
    )


# --- the live rule filter -------------------------------------------------

def filter_funnel(trace: dict, phase_label: str, level: str) -> str:
    """Show the narrowing that produced this answer.

    The filtering was always real; without this it was invisible, and "the rules
    narrow to what he actually said" was a claim rather than something you watch
    happen on every message.
    """
    if not trace:
        return '<div class="mt-empty">Waiting for the first message.</div>'

    # Before anything is said, the first three narrowings are already known -
    # they come from who the patient is, not from what he typed. Showing them at
    # rest makes it obvious the filter is real and already partly applied,
    # rather than leaving the panel looking like a static catalogue.
    pending = trace.get("pending", False)
    said = ", ".join(trace.get("symptoms") or []) or "nothing that maps to a symptom"
    triggered = trace.get("triggered") or []
    surviving = trace.get("surviving") or []

    def step(n, label, note="", emphasis=False, zero=False, awaiting=False):
        color = "var(--ink)" if not emphasis else LEVEL_COLOR.get(level, "var(--ink)")
        muted = "var(--ink-3)" if (awaiting or (zero and not n)) else color
        shown = "&mdash;" if awaiting else str(n)
        width = 0.0 if awaiting else max(4.0, (n / max(trace.get("library", 1), 1)) * 100)
        bar_color = LEVEL_COLOR.get(level, "#5f6874") if emphasis else "#c8ccd2"
        return f"""<div style="display:flex;align-items:center;gap:.7rem;padding:.3rem 0">
  <div style="font-family:ui-monospace,monospace;font-size:1rem;font-weight:700;color:{muted};
              width:2.4rem;text-align:right;font-variant-numeric:tabular-nums">{shown}</div>
  <div style="flex:0 0 34%;min-width:0">
    <div style="height:7px;border-radius:4px;background:#eceef1;overflow:hidden">
      <div style="height:100%;width:{width:.1f}%;background:{bar_color}"></div></div>
  </div>
  <div style="font-size:.79rem;color:var(--ink-2);min-width:0">{label}
    <span style="color:var(--ink-3)">{note}</span></div>
</div>"""

    rows = [
        step(trace.get("library", 0), "rules in the library"),
        step(trace.get("procedure", 0), "apply to this procedure", "· knee replacement"),
        step(trace.get("phase", 0), "apply at this phase", f"· {esc(phase_label.lower())}"),
        step(
            len(triggered),
            "triggered by what he just said",
            "· recomputed on every message"
            if pending
            else (f"· {esc(said)}" if triggered else "· nothing matched, which is why this is UNCERTAIN"),
            zero=True,
            awaiting=pending,
        ),
        step(
            len(surviving),
            "survive the exclusions",
            "" if pending else (f"· {', '.join(surviving)}" if surviving else ""),
            awaiting=pending,
        ),
    ]
    if pending:
        return (
            f'<div class="mt-card">{"".join(rows)}'
            '<div style="margin-top:.6rem;padding-top:.6rem;border-top:1px solid var(--line-2);'
            'font-size:.78rem;color:var(--ink-3)">The top three are already decided by who this '
            "patient is. The last two are recomputed from scratch on every message he sends.</div></div>"
        )

    dropped = ""
    for item in trace.get("excluded") or []:
        dropped += (
            f'<div style="font-size:.76rem;color:var(--ink-2);margin-top:.35rem;padding-left:.6rem;'
            f'border-left:2px solid #d8dce1">'
            f'<b>{esc(item["id"])}</b> ({esc(item["level"])}) ruled out by '
            f'<code style="font-family:ui-monospace,monospace;color:{LEVEL_COLOR.get(level, "var(--ink)")}">'
            f'{esc(", ".join(item["by"]))}</code><br>'
            f'<span style="color:var(--ink-3)">{esc(item["rationale"][:130])}…</span></div>'
        )

    upgrades = ""
    for item in trace.get("upgraded") or []:
        upgrades += (
            f'<div style="font-size:.76rem;color:var(--ink-2);margin-top:.35rem;padding-left:.6rem;'
            f'border-left:2px solid {LEVEL_COLOR.get(item["to"], "#d8dce1")}">'
            f'<b>{esc(item["id"])}</b> upgraded {esc(item["from"])} → <b>{esc(item["to"])}</b> '
            f'<span style="color:var(--ink-3)">because {esc(", ".join(item["because"]))}</span></div>'
        )

    chosen = trace.get("chosen")
    final = (
        f'<div style="margin-top:.6rem;padding-top:.6rem;border-top:1px solid var(--line-2);'
        f'font-size:.82rem;color:var(--ink-2)">Decided: {level_pill(level)} '
        + (f'via <b>{esc(chosen)}</b>' if chosen else "no rule matched")
        + "</div>"
    )
    return f'<div class="mt-card">{"".join(rows)}{dropped}{upgrades}{final}</div>'
