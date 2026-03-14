#!/usr/bin/env python3
"""
Sunday Mass site scraper.
Fetches readings from Catholic.org and videos from YouTube Data API v3,
updates data.json, then calls render.py to regenerate index.html.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from liturgical import get_liturgical_name, next_sunday

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SundayMassSiteBot/1.0; "
        "+https://github.com/example/sunday-mass)"
    )
}


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
    with open(config.DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    log.info("data.json saved.")


# ---------------------------------------------------------------------------
# Catholic.org scraping
# ---------------------------------------------------------------------------

CATHOLIC_ORG_URL = "https://www.catholic.org/bible/daily_reading/?date={date}"

# Maps h3 prefix patterns to our reading keys
READING_PATTERNS = [
    ("first_reading",   re.compile(r"^Reading\s+1", re.IGNORECASE)),
    ("psalm",           re.compile(r"^Responsorial\s+Psalm", re.IGNORECASE)),
    ("second_reading",  re.compile(r"^Reading\s+2", re.IGNORECASE)),
    ("gospel",          re.compile(r"^Gospel", re.IGNORECASE)),
]


def _text_from_paragraphs(tags):
    """Extract clean text from a list of <p> tags, stripping inline links."""
    parts = []
    for p in tags:
        parts.append(p.get_text(" ", strip=True))
    return "\n".join(parts)


def scrape_readings(sunday_date):
    """
    Scrape readings for the given date from Catholic.org.
    Returns a dict with keys: liturgical_name, readings (dict).
    Returns None if scraping fails.
    """
    date_str = sunday_date.strftime("%Y%m%d")
    url = CATHOLIC_ORG_URL.format(date=date_str)
    log.info("Fetching readings from: %s", url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to fetch Catholic.org: %s", e)
        return None

    time.sleep(config.REQUEST_DELAY_SECONDS)

    soup = BeautifulSoup(resp.text, "html.parser")

    # --- Liturgical name ---
    liturgical_name = None

    # Try to find it in the h4 date heading or nearby text
    # On Sunday pages, Catholic.org sometimes includes the Sunday name
    # in the h4 or a subtitle. Try several approaches.
    h4 = soup.find("h4", string=re.compile(r"Daily Reading for", re.IGNORECASE))
    if h4:
        # Check next sibling or parent for a subtitle
        parent = h4.find_parent()
        if parent:
            text = parent.get_text(" ", strip=True)
            # Look for patterns like "Fourth Sunday of Lent"
            match = re.search(
                r"((?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|"
                r"Palm|Easter|Pentecost|Trinity|Advent|Christmas|Epiphany|"
                r"Baptism|Corpus|Holy Family)[^\n<]{5,60})",
                text,
                re.IGNORECASE,
            )
            if match:
                liturgical_name = match.group(1).strip()

    # Also check page title
    if not liturgical_name:
        title_tag = soup.find("title")
        if title_tag:
            match = re.search(
                r"((?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|"
                r"Palm|Easter|Pentecost|Trinity|Advent|Christmas|Epiphany|"
                r"Baptism|Corpus|Holy Family)[^\n<]{5,60})",
                title_tag.get_text(),
                re.IGNORECASE,
            )
            if match:
                liturgical_name = match.group(1).strip()

    # Fallback: compute from our liturgical calendar
    if not liturgical_name:
        liturgical_name = get_liturgical_name(sunday_date)
        if liturgical_name:
            log.info("Used fallback liturgical name: %s", liturgical_name)
        else:
            log.warning("Could not determine liturgical name.")

    # --- Readings ---
    readings_div = soup.find("div", id="drReadings")
    if not readings_div:
        log.error("Could not find #drReadings on Catholic.org page.")
        return None

    readings = {}
    h3_tags = readings_div.find_all("h3")

    for h3 in h3_tags:
        h3_text = h3.get_text(" ", strip=True)
        matched_key = None
        for key, pattern in READING_PATTERNS:
            if pattern.match(h3_text):
                matched_key = key
                break
        if not matched_key:
            continue

        # Extract citation from the <em> inside the h3
        em = h3.find("em")
        citation = em.get_text(strip=True) if em else h3_text

        # Collect <p> tags that follow this h3, until the next h3 or end
        sibling = h3.find_next_sibling()
        paras = []
        while sibling and sibling.name != "h3":
            if sibling.name == "p":
                paras.append(sibling)
            sibling = sibling.find_next_sibling()

        text = _text_from_paragraphs(paras)
        readings[matched_key] = {"citation": citation, "text": text}

    if not readings:
        log.error("No readings found in #drReadings.")
        return None

    log.info("Scraped readings: %s", list(readings.keys()))
    return {
        "liturgical_name": liturgical_name,
        "readings": readings,
    }


# ---------------------------------------------------------------------------
# YouTube API
# ---------------------------------------------------------------------------

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def search_youtube(query, max_results=5):
    """
    Search YouTube and return a list of video dicts:
    {id, title, channel, found_at}
    """
    params = {
        "key": config.YOUTUBE_API_KEY,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": max_results,
        "relevanceLanguage": "en",
        "safeSearch": "none",
    }
    try:
        resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("YouTube API request failed: %s", e)
        return []

    data = resp.json()
    results = []
    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        results.append({
            "id": video_id,
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "found_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        })
    log.info("YouTube search '%s' returned %d results.", query, len(results))
    return results


CATEGORIES = ("readings", "full_mass", "homily", "music")


def _priority(video, preferred_channels):
    """Return sort key: preferred channels sort first by their list position."""
    channel = video.get("channel", "")
    for i, name in enumerate(preferred_channels):
        if name.lower() in channel.lower():
            return i
    return len(preferred_channels)


def sort_by_preferred(videos, category):
    """Sort a video list so preferred channels float to the top."""
    preferred = config.PREFERRED_CHANNELS.get(category, [])
    return sorted(videos, key=lambda v: _priority(v, preferred))


def fetch_videos(liturgical_name, sunday_date):
    """Run one YouTube search per category and return dict keyed by category."""
    date_label = sunday_date.strftime("%B %-d, %Y")
    queries = {
        "readings": "Catholic mass readings {date}".format(date=date_label),
        "full_mass": '"{name}" Mass {year}'.format(
            name=liturgical_name, year=sunday_date.year),
        "homily":    '"{name}" homily OR sermon {year}'.format(
            name=liturgical_name, year=sunday_date.year),
        "music":     '"{name}" hymns OR songs OR canticle'.format(
            name=liturgical_name),
    }
    results = {}
    for category, query in queries.items():
        videos = search_youtube(query, config.VIDEOS_TO_FETCH_PER_SEARCH)
        results[category] = sort_by_preferred(videos, category)
        time.sleep(1)
    return results


def merge_videos(existing, new_results):
    """
    Merge new video results into existing accumulated lists.
    Deduplicates by video ID, then re-sorts by preferred channels.
    Returns updated dict.
    """
    merged = {}
    for category in CATEGORIES:
        existing_list = existing.get(category, [])
        existing_ids = set(v["id"] for v in existing_list)
        combined = list(existing_list)
        for video in new_results.get(category, []):
            if video["id"] not in existing_ids:
                combined.append(video)
                existing_ids.add(video["id"])
        merged[category] = sort_by_preferred(combined, category)
    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=== Sunday Mass scraper starting ===")

    sunday = next_sunday()
    sunday_str = sunday.strftime("%Y-%m-%d")
    log.info("Upcoming Sunday: %s", sunday_str)

    data = load_data()
    existing_sunday = data.get("sunday_date")

    # --- Readings: only re-scrape if Sunday has changed ---
    if existing_sunday != sunday_str:
        log.info("New Sunday detected (%s -> %s). Scraping readings.", existing_sunday, sunday_str)
        result = scrape_readings(sunday)
        if result is None:
            log.error("Scrape failed. Keeping existing data. Aborting run.")
            sys.exit(1)
        data["sunday_date"] = sunday_str
        data["liturgical_name"] = result["liturgical_name"]
        data["readings"] = result["readings"]
        # Reset videos for the new Sunday
        data["videos"] = {cat: [] for cat in CATEGORIES}
    else:
        log.info("Sunday unchanged (%s). Skipping reading scrape.", sunday_str)

    liturgical_name = data.get("liturgical_name", "")

    # --- YouTube: always fetch and merge ---
    if liturgical_name:
        new_videos = fetch_videos(liturgical_name, sunday)
        data["videos"] = merge_videos(data.get("videos", {}), new_videos)
    else:
        log.warning("No liturgical name available; skipping YouTube search.")

    save_data(data)

    # --- Re-render HTML ---
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
