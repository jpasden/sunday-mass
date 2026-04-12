#!/usr/bin/env python3
"""
Sunday Mass site scraper.
Fetches English readings from Catholic.org and Spanish readings from USCCB,
adapts them for a 12-year-old reader using Claude Haiku, generates study notes,
and re-renders index.html.

Pipeline (all steps cached per Sunday — only re-run if sunday_date changes):
  1. Scrape English readings (Catholic.org)
  2. Scrape Spanish readings (USCCB ES)
  3. Haiku: adapt English readings for kids
  4. Haiku: adapt Spanish readings for kids
  5. Haiku: write English adult notes (3 paragraphs)
  6. Haiku: adapt English notes for kids
  7. Haiku: translate English adult notes → Spanish
  8. Haiku: translate English kids notes → Spanish kids
"""

import json
import logging
import os
import re
import sys
import time
import datetime
import subprocess

import requests
from bs4 import BeautifulSoup
import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from liturgical import get_liturgical_name, target_sunday

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SundayMassSiteBot/1.0; "
        "+https://github.com/jpasden/sunday-mass)"
    )
}

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_data():
    if os.path.exists(config.DATA_FILE):
        try:
            with open(config.DATA_FILE, "r") as f:
                return json.load(f)
        except (ValueError, IOError) as e:
            log.warning("Could not load data.json: %s", e)
    return {}


def save_data(data):
    os.makedirs(os.path.dirname(config.DATA_FILE), exist_ok=True)
    data["last_updated"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    with open(config.DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("data.json saved.")


# ---------------------------------------------------------------------------
# English readings — Catholic.org
# ---------------------------------------------------------------------------

CATHOLIC_ORG_URL = "https://www.catholic.org/bible/daily_reading/?select_date={date}"

EN_READING_PATTERNS = [
    ("first_reading",  re.compile(r"^Reading\s+1", re.IGNORECASE)),
    ("second_reading", re.compile(r"^Reading\s+2", re.IGNORECASE)),
    ("gospel",         re.compile(r"^Gospel",       re.IGNORECASE)),
]


def _paragraphs_from_tags(tags):
    """Return list of non-empty paragraph strings from <p> tag objects."""
    return [p.get_text(" ", strip=True) for p in tags if p.get_text(strip=True)]


def scrape_readings_en(sunday_date):
    """
    Scrape first reading, second reading, and gospel from Catholic.org.
    Returns {"liturgical_name": str, "readings": {key: {"citation", "paragraphs"}}}
    or None on failure.
    """
    date_str = sunday_date.strftime("%Y-%m-%d")
    url = CATHOLIC_ORG_URL.format(date=date_str)
    log.info("Fetching English readings: %s", url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to fetch Catholic.org: %s", e)
        return None

    time.sleep(config.REQUEST_DELAY_SECONDS)
    soup = BeautifulSoup(resp.text, "html.parser")
    liturgical_name = get_liturgical_name(sunday_date)

    readings_div = (soup.find("div", id="bibleDailyReading")
                    or soup.find("div", id="drReadings"))
    if not readings_div:
        log.error("Could not find readings container on Catholic.org.")
        return None

    readings = {}
    for h3 in readings_div.find_all("h3"):
        h3_text = h3.get_text(" ", strip=True)
        matched_key = None
        for key, pattern in EN_READING_PATTERNS:
            if pattern.match(h3_text):
                matched_key = key
                break
        if not matched_key:
            continue

        em = h3.find("em")
        citation = em.get_text(strip=True) if em else h3_text

        sibling = h3.find_next_sibling()
        ptags = []
        while sibling and sibling.name != "h3":
            if sibling.name == "p":
                ptags.append(sibling)
            sibling = sibling.find_next_sibling()

        paragraphs = _paragraphs_from_tags(ptags)
        if paragraphs:
            readings[matched_key] = {"citation": citation, "paragraphs": paragraphs}

    if not readings:
        log.error("No English readings found in container.")
        return None

    ordered = {k: readings[k] for k in ["first_reading", "second_reading", "gospel"]
               if k in readings}
    log.info("Scraped English readings: %s", list(ordered.keys()))
    return {"liturgical_name": liturgical_name, "readings": ordered}


# ---------------------------------------------------------------------------
# Spanish readings — USCCB
# ---------------------------------------------------------------------------

USCCB_ES_URL = "https://bible.usccb.org/es/bible/lecturas/{date}.cfm"

ES_READING_PATTERNS = [
    ("first_reading",  re.compile(r"primera\s+lectura",  re.IGNORECASE)),
    ("second_reading", re.compile(r"segunda\s+lectura",  re.IGNORECASE)),
    ("gospel",         re.compile(r"^evangelio",         re.IGNORECASE)),
]


def scrape_readings_es(sunday_date):
    """
    Scrape first reading, second reading, and gospel from USCCB Spanish.
    Page structure: each reading is a div.innerblock containing
      div.content-header (h3.name + div.address) and div.content-body (p tags).
    Returns {key: {"citation", "paragraphs"}} or None on failure.
    """
    date_str = sunday_date.strftime("%m%d%y")  # e.g. 041226
    url = USCCB_ES_URL.format(date=date_str)
    log.info("Fetching Spanish readings: %s", url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to fetch USCCB ES: %s", e)
        return None

    time.sleep(config.REQUEST_DELAY_SECONDS)
    soup = BeautifulSoup(resp.text, "html.parser")

    readings = {}
    for block in soup.find_all("div", class_="innerblock"):
        header = block.find("div", class_="content-header")
        if not header:
            continue
        h3 = header.find("h3", class_="name")
        if not h3:
            continue
        h3_text = h3.get_text(" ", strip=True)

        matched_key = None
        for key, pattern in ES_READING_PATTERNS:
            if pattern.search(h3_text):
                matched_key = key
                break
        if not matched_key:
            continue

        addr = header.find("div", class_="address")
        citation = addr.get_text(strip=True) if addr else ""

        body = block.find("div", class_="content-body")
        paragraphs = []
        if body:
            for p in body.find_all("p"):
                text = p.get_text(" ", strip=True)
                if text:
                    paragraphs.append(text)

        if paragraphs:
            readings[matched_key] = {"citation": citation, "paragraphs": paragraphs}

    if not readings:
        log.error("No Spanish readings found. USCCB page structure may have changed.")
        return None

    ordered = {k: readings[k] for k in ["first_reading", "second_reading", "gospel"]
               if k in readings}
    log.info("Scraped Spanish readings: %s", list(ordered.keys()))
    return ordered


# ---------------------------------------------------------------------------
# Anthropic / Haiku helpers
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set in the environment.")
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _call_haiku(prompt, max_tokens=4096):
    """Call Claude Haiku; return response text or None on failure."""
    try:
        msg = _get_client().messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        log.error("Haiku API call failed: %s", e)
        return None


def _parse_json(text, label):
    """Strip markdown fences and parse JSON; return None on failure."""
    if text is None:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        log.error("JSON parse failed for %s: %s\nResponse was: %.500s", label, e, text)
        return None


# ---------------------------------------------------------------------------
# Kids reading adaptation
# ---------------------------------------------------------------------------

def _readings_to_prompt_text(readings):
    labels = {
        "first_reading":  "FIRST READING",
        "second_reading": "SECOND READING",
        "gospel":         "GOSPEL",
    }
    parts = []
    for key in ["first_reading", "second_reading", "gospel"]:
        if key not in readings:
            continue
        r = readings[key]
        parts.append(f"{labels[key]} ({r['citation']}):")
        for i, para in enumerate(r["paragraphs"], 1):
            parts.append(f"  Paragraph {i}: {para}")
        parts.append("")
    return "\n".join(parts)


def adapt_readings_for_kids(readings, language="English"):
    """
    Rewrite readings for a 12-year-old. Returns a readings dict with the same
    structure but kids-friendly paragraphs; paragraph count matches the adult version.
    """
    log.info("Adapting %s readings for kids...", language)
    readings_text = _readings_to_prompt_text(readings)

    prompt = f"""You are adapting Catholic Mass readings for a 12-year-old.

Here are the three readings in {language}:

{readings_text}
Rewrite each paragraph in clear, simple {language} that a 12-year-old can easily understand. When a biblical or historical term appears that a young reader might not know (e.g., "Pharisees", "leper", "synagogue", "apostle", "covenant"), add a brief parenthetical explanation right after it — for example: Pharisees (a group of strict Jewish religious leaders who followed many detailed rules).

Keep the meaning faithful to the original. Do not add or remove events.

Return ONLY valid JSON — no extra text, no markdown fences:
{{
  "first_reading": ["paragraph 1 text", "paragraph 2 text", ...],
  "second_reading": ["paragraph 1 text", ...],
  "gospel": ["paragraph 1 text", ...]
}}

Each array must have exactly the same number of elements as the corresponding adult reading listed above. Omit any key not present in the input."""

    result = _parse_json(_call_haiku(prompt), f"kids readings ({language})")
    if result is None:
        return None

    kids = {}
    for key in ["first_reading", "second_reading", "gospel"]:
        if key not in readings:
            continue
        kids_paras = result.get(key)
        if not isinstance(kids_paras, list) or not kids_paras:
            log.warning("Kids reading missing or empty for key: %s — falling back to adult.", key)
            kids_paras = readings[key]["paragraphs"]
        kids[key] = {"citation": readings[key]["citation"], "paragraphs": kids_paras}

    return kids


# ---------------------------------------------------------------------------
# Notes generation
# ---------------------------------------------------------------------------

def write_notes_en(liturgical_name, readings):
    """Generate three-paragraph English study notes from the readings."""
    log.info("Writing English adult notes...")
    readings_text = _readings_to_prompt_text(readings)

    prompt = f"""You are a Catholic biblical scholar writing for adult readers.

Today is {liturgical_name}. Here are the three Mass readings:

{readings_text}
Write exactly three paragraphs as a JSON object. Return ONLY valid JSON — no extra text.

Be theologically precise and faithful to what each passage actually says. Do not reverse or soften key theological moments. For example: if Thomas believes because he sees and touches the risen Christ, say so clearly — and note that Jesus then blesses those who believe WITHOUT having seen, which is the situation of all Christians who come after. Do not conflate Thomas's privileged experience with the experience of later believers.

{{
  "historical_context": "One paragraph of relevant historical, archaeological, or anthropological background that helps an adult reader understand these readings more deeply.",
  "connections": "One paragraph explaining why these three readings were placed together in the Sunday lectionary. What is the unifying theological theme or thread connecting them?",
  "meaning_today": "One paragraph explaining why these readings remain meaningful and relevant for Catholic Christians living today."
}}"""

    return _parse_json(_call_haiku(prompt), "English notes")


def vet_notes(liturgical_name, readings, notes):
    """
    Have Claude review the English adult notes for theological accuracy.
    Returns {"notes": {corrected notes}, "corrections": [list of changes made]}
    or None on API failure.
    """
    log.info("Vetting notes for theological accuracy...")
    readings_text = _readings_to_prompt_text(readings)
    notes_json = json.dumps(notes, ensure_ascii=False, indent=2)

    prompt = f"""You are a careful Catholic theologian reviewing study notes for theological accuracy.

Today is {liturgical_name}. Here are the actual Mass readings:

{readings_text}
Here are the study notes to review:
{notes_json}

Check each paragraph carefully for:
- Reversed or inverted meanings (e.g., saying someone believed without seeing when the text says they believed BECAUSE they saw, or vice versa)
- Misattributed statements or quotes assigned to the wrong person or passage
- Claims that contradict what the readings actually say
- Theological errors that conflict with standard Catholic teaching

If a paragraph is accurate, keep it exactly as written. If you find an error, correct it.

Return ONLY valid JSON — no extra text:
{{
  "corrections": ["brief description of each correction made — empty list if none"],
  "notes": {{
    "historical_context": "...",
    "connections": "...",
    "meaning_today": "..."
  }}
}}"""

    result = _parse_json(_call_haiku(prompt), "notes vetting")
    if result is None:
        return None
    if result.get("corrections"):
        log.warning("Vet made %d correction(s): %s",
                    len(result["corrections"]), result["corrections"])
    else:
        log.info("Vet passed with no corrections.")
    return result


def adapt_notes_for_kids(notes):
    """Adapt the three-paragraph notes for a 12-year-old."""
    log.info("Adapting notes for kids...")
    notes_json = json.dumps(notes, ensure_ascii=False, indent=2)

    prompt = f"""Rewrite these three paragraphs for a 12-year-old Catholic reader. Keep the same three JSON keys and the same overall meaning. Use simple, clear language. Add brief parenthetical explanations for any complex terms.

Return ONLY valid JSON with exactly the same structure:
{notes_json}"""

    return _parse_json(_call_haiku(prompt), "kids notes")


def translate_notes(notes, target_language):
    """Translate a notes dict to target_language."""
    log.info("Translating notes to %s...", target_language)
    notes_json = json.dumps(notes, ensure_ascii=False, indent=2)

    prompt = f"""Translate these three paragraphs to {target_language}. Keep the same three JSON keys. Return ONLY valid JSON with exactly the same structure:
{notes_json}"""

    return _parse_json(_call_haiku(prompt), f"notes ({target_language})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=== Sunday Mass scraper starting ===")

    sunday = target_sunday()
    sunday_str = sunday.strftime("%Y-%m-%d")
    log.info("Target Sunday: %s", sunday_str)

    data = load_data()
    existing_sunday = data.get("sunday_date")
    new_sunday = existing_sunday != sunday_str

    if new_sunday:
        log.info("New Sunday (%s → %s). Clearing cached data.", existing_sunday, sunday_str)
        data = {"sunday_date": sunday_str}

    # ── 1. English readings ──────────────────────────────────────────────
    if "readings_en" not in data:
        result = scrape_readings_en(sunday)
        if result is None:
            log.error("English readings scrape failed. Aborting.")
            sys.exit(1)
        data["liturgical_name"] = result["liturgical_name"]
        data["readings_en"] = result["readings"]
        save_data(data)
    else:
        log.info("English readings already cached.")

    # ── 2. Spanish readings ──────────────────────────────────────────────
    if "readings_es" not in data:
        es = scrape_readings_es(sunday)
        if es is None:
            log.warning("Spanish readings scrape failed. Spanish content will be unavailable.")
        else:
            data["readings_es"] = es
            save_data(data)
    else:
        log.info("Spanish readings already cached.")

    liturgical_name = data.get("liturgical_name", "")

    # ── 3. Kids English readings ─────────────────────────────────────────
    if "readings_en_kids" not in data and "readings_en" in data:
        kids_en = adapt_readings_for_kids(data["readings_en"], language="English")
        if kids_en:
            data["readings_en_kids"] = kids_en
            save_data(data)

    # ── 4. Kids Spanish readings ─────────────────────────────────────────
    if "readings_es_kids" not in data and "readings_es" in data:
        kids_es = adapt_readings_for_kids(data["readings_es"], language="Spanish")
        if kids_es:
            data["readings_es_kids"] = kids_es
            save_data(data)

    # ── 5. English adult notes ───────────────────────────────────────────
    if "notes_en" not in data and "readings_en" in data and liturgical_name:
        notes_en = write_notes_en(liturgical_name, data["readings_en"])
        if notes_en:
            data["notes_en"] = notes_en
            save_data(data)

    # ── 5b. Vet English notes for theological accuracy ───────────────────
    if "notes_en" in data and not data.get("notes_vetted"):
        vetted = vet_notes(liturgical_name, data["readings_en"], data["notes_en"])
        if vetted:
            data["notes_en"] = vetted["notes"]
            data["notes_vet_log"] = vetted.get("corrections", [])
            data["notes_vetted"] = True
            save_data(data)
        else:
            log.warning("Vetting API call failed — skipping downstream note steps for safety.")

    # Steps 6–8 only proceed once notes have been vetted
    if not data.get("notes_vetted"):
        log.warning("Notes not yet vetted; skipping kids/Spanish note generation.")
    else:
        # ── 6. English kids notes ─────────────────────────────────────────
        if "notes_en_kids" not in data:
            notes_en_kids = adapt_notes_for_kids(data["notes_en"])
            if notes_en_kids:
                data["notes_en_kids"] = notes_en_kids
                save_data(data)

        # ── 7. Spanish adult notes ────────────────────────────────────────
        if "notes_es" not in data:
            notes_es = translate_notes(data["notes_en"], "Spanish")
            if notes_es:
                data["notes_es"] = notes_es
                save_data(data)

        # ── 8. Spanish kids notes ─────────────────────────────────────────
        if "notes_es_kids" not in data and "notes_en_kids" in data:
            notes_es_kids = translate_notes(data["notes_en_kids"], "Spanish")
            if notes_es_kids:
                data["notes_es_kids"] = notes_es_kids
                save_data(data)

    # ── Render ───────────────────────────────────────────────────────────
    script_dir = os.path.dirname(os.path.abspath(__file__))
    render_script = os.path.join(script_dir, "render.py")
    log.info("Rendering HTML...")
    ret = subprocess.call([sys.executable, render_script])
    if ret != 0:
        log.error("render.py exited with code %d.", ret)
        sys.exit(ret)

    log.info("=== Done ===")


if __name__ == "__main__":
    main()
