"""Live lookups against public health data APIs.

What is live and what is not, and why:

The urgency decision is NOT live. No public API publishes machine-readable
post-operative red-flag thresholds keyed by procedure and severity, and even if
one did, putting a network call in the safety path would mean the answer to
"is this an emergency" depends on someone else's uptime. `engine.py` stays
deterministic and offline. That is the point of it.

What IS live is the evidence layer around that decision - the patient-education
content, the drug labels, the trials - fetched from:

  MedlinePlus Connect     NIH/NLM. Give it the patient's real ICD-10 codes,
                          get back the patient-education pages an EHR would
                          surface. https://connect.medlineplus.gov/
  MedlinePlus web service NIH/NLM health-topic search.
  RxNav / RxNorm          NIH/NLM drug vocabulary. Real RxCUIs.
  openFDA                 FDA drug labels - the actual boxed warnings.
  ClinicalTrials.gov v2   Recruiting studies.

All five are public, free, and need no API key. AAOS OrthoInfo and the NHS
website publish no open API, so rules citing them link to the page instead.

Everything is cached to data/cache with a TTL, so a demo still runs with the
network unplugged and we are not hammering public infrastructure.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT, "data", "cache")
USER_AGENT = "meantime-demo/1.0 (hackathon prototype; contact via repository)"
TIMEOUT = 10
DEFAULT_TTL = 24 * 3600

ENDPOINTS = {
    "medlineplus_connect": ("MedlinePlus Connect", "https://connect.medlineplus.gov/service"),
    "medlineplus_search": ("MedlinePlus health topics", "https://wsearch.nlm.nih.gov/ws/query"),
    "rxnav": ("RxNav / RxNorm", "https://rxnav.nlm.nih.gov/REST/"),
    "openfda": ("openFDA drug labels", "https://api.fda.gov/drug/label.json"),
    "clinicaltrials": ("ClinicalTrials.gov", "https://clinicaltrials.gov/api/v2/studies"),
}

# Filled in as calls happen, so the dashboard can show what actually went out.
CALL_LOG: list[dict] = []

# Set for the duration of a forced refresh, so the demo can show a real network
# round-trip on demand instead of a cache hit.
_FORCE = False


# --- caching --------------------------------------------------------------

def _cache_path(url: str) -> str:
    return os.path.join(CACHE_DIR, hashlib.sha1(url.encode()).hexdigest()[:20] + ".json")


def _fetch(url: str, ttl: int = DEFAULT_TTL) -> tuple[str | None, str]:
    """Return (body, status) where status is live | cached | stale | failed."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(url)
    cached = None
    if os.path.exists(path) and not _FORCE:
        try:
            with open(path, encoding="utf-8") as fh:
                cached = json.load(fh)
            if time.time() - cached["fetched_at"] < ttl:
                _log(url, "cached", cached["fetched_at"])
                return cached["body"], "cached"
        except Exception:
            cached = None

    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read().decode("utf-8", "replace")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"url": url, "fetched_at": time.time(), "body": body}, fh)
        _log(url, "live", time.time())
        return body, "live"
    except Exception as exc:
        if cached:  # network is down but we have something from last time
            _log(url, "stale", cached["fetched_at"], str(exc))
            return cached["body"], "stale"
        _log(url, "failed", None, str(exc))
        return None, "failed"


def _log(url: str, status: str, fetched_at: float | None, error: str = "") -> None:
    CALL_LOG.append({"url": url, "status": status, "fetched_at": fetched_at, "error": error})


def _json(url: str, ttl: int = DEFAULT_TTL):
    body, status = _fetch(url, ttl)
    if body is None:
        return None, status
    try:
        return json.loads(body), status
    except json.JSONDecodeError:
        return None, "failed"


# --- MedlinePlus Connect --------------------------------------------------

ICD10_OID = "2.16.840.1.113883.6.90"


def patient_education(code: str, label: str = "") -> dict | None:
    """The patient-education pages MedlinePlus Connect returns for an ICD-10 code.

    This is the same call a certified EHR makes to put an "learn about this
    diagnosis" link in front of a patient.
    """
    url = ENDPOINTS["medlineplus_connect"][1] + "?" + urllib.parse.urlencode(
        {
            "mainSearchCriteria.v.cs": ICD10_OID,
            "mainSearchCriteria.v.c": code,
            "knowledgeResponseType": "application/json",
        }
    )
    data, status = _json(url)
    if not data:
        return None
    entries = (data.get("feed") or {}).get("entry") or []
    out = []
    for entry in entries[:3]:
        links = entry.get("link") or []
        href = next((l.get("href") for l in links if l.get("href")), None)
        out.append(
            {
                "title": (entry.get("title") or {}).get("_value", ""),
                "summary": _strip((entry.get("summary") or {}).get("_value", "")),
                "url": href,
            }
        )
    return {"code": code, "label": label, "status": status, "topics": out}


def _strip(text: str, limit: int = 260) -> str:
    """MedlinePlus summaries come back with markup in them."""
    out, keep = [], True
    for ch in text:
        if ch == "<":
            keep = False
        elif ch == ">":
            keep = True
        elif keep:
            out.append(ch)
    clean = " ".join("".join(out).split())
    return clean[:limit] + ("…" if len(clean) > limit else "")


def health_topic(term: str) -> dict | None:
    """MedlinePlus health-topic search - used to back the concepts rules cite."""
    url = ENDPOINTS["medlineplus_search"][1] + "?" + urllib.parse.urlencode(
        {"db": "healthTopics", "term": term, "retmax": 1}
    )
    body, status = _fetch(url)
    if not body:
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    doc = root.find(".//document")
    if doc is None:
        return None
    fields = {c.get("name"): "".join(c.itertext()) for c in doc.findall("content")}
    return {
        "term": term,
        "status": status,
        "title": _strip(fields.get("title", term), 120),
        "summary": _strip(fields.get("FullSummary", ""), 300),
        "url": doc.get("url"),
    }


# --- drugs ----------------------------------------------------------------

def drug_profile(name: str) -> dict:
    """RxNorm identity plus the real FDA label warning for one medication."""
    profile = {"name": name, "rxcui": None, "warning": None, "brand": None, "status": "failed"}

    data, status = _json(f"https://rxnav.nlm.nih.gov/REST/rxcui.json?name={urllib.parse.quote(name)}")
    profile["status"] = status
    if data:
        ids = (data.get("idGroup") or {}).get("rxnormId") or []
        profile["rxcui"] = ids[0] if ids else None

    label, label_status = _json(
        ENDPOINTS["openfda"][1]
        + "?"
        + urllib.parse.urlencode({"search": f"openfda.generic_name:{name}", "limit": 1})
    )
    if label and label.get("results"):
        result = label["results"][0]
        openfda = result.get("openfda") or {}
        brands = openfda.get("brand_name") or []
        profile["brand"] = brands[0] if brands else None
        for field in ("boxed_warning", "warnings_and_cautions", "warnings"):
            if result.get(field):
                profile["warning"] = _strip(result[field][0], 320)
                profile["warning_field"] = field
                break
        profile["status"] = label_status if profile["status"] == "failed" else profile["status"]
    return profile


# --- trials ---------------------------------------------------------------

def trials(condition: str, limit: int = 3) -> list[dict]:
    url = ENDPOINTS["clinicaltrials"][1] + "?" + urllib.parse.urlencode(
        {
            "query.cond": condition,
            "filter.overallStatus": "RECRUITING",
            "pageSize": limit,
            "fields": "NCTId,BriefTitle,OverallStatus,Phase,LocationCountry",
        }
    )
    data, _ = _json(url, ttl=7 * 24 * 3600)
    if not data:
        return []
    out = []
    for study in data.get("studies", [])[:limit]:
        protocol = study.get("protocolSection") or {}
        ident = protocol.get("identificationModule") or {}
        status_mod = protocol.get("statusModule") or {}
        design = protocol.get("designModule") or {}
        nct = ident.get("nctId")
        out.append(
            {
                "nct": nct,
                "title": _strip(ident.get("briefTitle", ""), 110),
                "status": (status_mod.get("overallStatus") or "").replace("_", " ").title(),
                "phase": ", ".join(design.get("phases") or []) or "N/A",
                "url": f"https://clinicaltrials.gov/study/{nct}" if nct else None,
            }
        )
    return out


# --- citation checking ----------------------------------------------------

def check_url(url: str, ttl: int = 7 * 24 * 3600) -> dict:
    """Confirm a rule's citation still resolves. Cached hard - these are stable
    pages and we are not going to re-check them on every rerun."""
    if not url:
        return {"url": url, "ok": None, "status": "no url"}
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path("HEAD " + url)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                cached = json.load(fh)
            if time.time() - cached["fetched_at"] < ttl:
                return cached["result"]
        except Exception:
            pass
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            result = {"url": url, "ok": response.status < 400, "status": str(response.status)}
    except Exception as exc:
        result = {"url": url, "ok": False, "status": type(exc).__name__}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"fetched_at": time.time(), "result": result}, fh)
    return result


# --- the bundle the dashboard asks for -----------------------------------

def live_bundle(ctx: dict, force: bool = False) -> dict:
    """Everything the dashboard shows, fetched for this patient in this phase.

    `force` skips the disk cache so the demo can prove the calls are real.
    """
    global _FORCE
    _FORCE = force
    try:
        return _live_bundle(ctx)
    finally:
        _FORCE = False


def _live_bundle(ctx: dict) -> dict:
    CALL_LOG.clear()

    codes = ctx.get("diagnosis_codes") or [
        {"code": c["icd10"], "label": c["name"]} for c in ctx.get("conditions", []) if c.get("icd10")
    ]
    education = [e for e in (patient_education(c["code"], c.get("label", "")) for c in codes[:3]) if e]

    medications = [m["name"] for m in ctx.get("discharge_medications", []) if m.get("class")]
    if not medications:
        medications = [m["name"] for m in ctx.get("home_medications", [])][:2]
    drugs = [drug_profile(name) for name in medications[:3]]

    topics = [t for t in (health_topic(term) for term in ("deep vein thrombosis", "surgical wound infection")) if t]
    studies = trials("knee osteoarthritis")

    # Which endpoint each call went to, and the best status any call to it got.
    rank = {"live": 3, "cached": 2, "stale": 1, "failed": 0}
    endpoint_status: dict[str, str] = {}
    for call in CALL_LOG:
        for key, (_name, base) in ENDPOINTS.items():
            if call["url"].startswith(base):
                current = endpoint_status.get(key)
                if current is None or rank[call["status"]] > rank[current]:
                    endpoint_status[key] = call["status"]
                break

    statuses = [c["status"] for c in CALL_LOG]
    return {
        "endpoint_status": endpoint_status,
        "education": education,
        "drugs": drugs,
        "topics": topics,
        "trials": studies,
        "calls": list(CALL_LOG),
        "live_count": statuses.count("live"),
        "cached_count": statuses.count("cached") + statuses.count("stale"),
        "failed_count": statuses.count("failed"),
        "checked_at": time.strftime("%H:%M:%S"),
    }


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    edu = patient_education("Z96.651", "Presence of right artificial knee joint")
    print("MedlinePlus Connect Z96.651 ->", edu["status"])
    for topic in edu["topics"]:
        print("   ", topic["title"], "|", topic["url"])
    for drug in ("apixaban", "oxycodone"):
        p = drug_profile(drug)
        print(f"{drug}: rxcui={p['rxcui']} brand={p['brand']} warning={(p['warning'] or '')[:90]!r}")
    topic = health_topic("deep vein thrombosis")
    print("topic:", topic["title"], "|", topic["url"])
    for study in trials("knee osteoarthritis"):
        print("trial:", study["nct"], study["status"], "|", study["title"][:70])
