"""
ARCHIVED — YouTube video scraping code removed from scraper.py.
Kept here as a reference for future YouTube Data API v3 usage.

To use: import and call fetch_videos(liturgical_name, sunday_date).
Requires config.YOUTUBE_API_KEY, config.MAX_VIDEOS_PER_CATEGORY,
config.VIDEOS_TO_FETCH_PER_SEARCH, and config.PREFERRED_CHANNEL_IDS.

The YouTube API key was: AIzaSyApBlgUC_p4AdNhVwfBnoTCfZQ59g7Nxlc
(removed from active config — do not commit live keys to the repo)
"""

import datetime
import logging
import time

import requests

log = logging.getLogger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

CATEGORIES = ("readings", "full_mass", "homily", "music")


def _make_video(item):
    snippet = item.get("snippet", {})
    video_id = item.get("id", {})
    if isinstance(video_id, dict):
        video_id = video_id.get("videoId", "")
    return {
        "id": video_id,
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "found_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def search_youtube(query, api_key, channel_id=None, max_results=5, published_after=None):
    """Search YouTube, optionally restricted to a channel. Returns list of video dicts."""
    params = {
        "key": api_key,
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": max_results,
        "relevanceLanguage": "en",
        "safeSearch": "none",
        "order": "date",
    }
    if channel_id:
        params["channelId"] = channel_id
    if published_after:
        params["publishedAfter"] = published_after  # RFC 3339, e.g. "2026-03-10T00:00:00Z"
    try:
        resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("YouTube API request failed: %s", e)
        return []
    data = resp.json()
    results = [_make_video(item) for item in data.get("items", [])
               if item.get("id", {}).get("videoId")]
    log.info("YouTube search '%s' (channel=%s) returned %d results.",
             query, channel_id or "any", len(results))
    time.sleep(1)
    return results


def fetch_for_category(category, query, api_key, channel_ids,
                       max_per_category=3, videos_to_fetch=5, published_after=None):
    """
    Search preferred channels first (in priority order), then fall back to
    a general search if we still have fewer than max_per_category results.
    Returns a deduplicated list.
    """
    seen_ids = set()
    results = []

    for channel_id in channel_ids:
        if len(results) >= max_per_category:
            break
        videos = search_youtube(query, api_key, channel_id=channel_id,
                                max_results=max_per_category, published_after=published_after)
        for v in videos:
            if v["id"] and v["id"] not in seen_ids:
                seen_ids.add(v["id"])
                results.append(v)

    if len(results) < max_per_category:
        log.info("Only %d from preferred channels for '%s'; running general search.",
                 len(results), category)
        general = search_youtube(query, api_key, max_results=videos_to_fetch,
                                 published_after=published_after)
        for v in general:
            if v["id"] and v["id"] not in seen_ids:
                seen_ids.add(v["id"])
                results.append(v)

    return results


def fetch_videos(liturgical_name, sunday_date, api_key, preferred_channel_ids,
                 max_per_category=3, videos_to_fetch=5):
    """Fetch videos for all categories using preferred channels first."""
    date_label = sunday_date.strftime("%B %-d, %Y")
    short_name = liturgical_name.split(",")[0]

    week_start = sunday_date - datetime.timedelta(days=10)
    published_after = week_start.strftime("%Y-%m-%dT00:00:00Z")

    queries = {
        "readings": "Catholic mass readings {date}".format(date=date_label),
        "full_mass": "{name} {date} Sunday Mass".format(name=short_name, date=date_label),
        "homily":    "{name} {date} homily OR sermon".format(name=short_name, date=date_label),
        "music":     "{name} {date} hymns OR choir OR canticle".format(name=short_name, date=date_label),
    }

    results = {}
    for category, query in queries.items():
        channel_ids = preferred_channel_ids.get(category, [])
        results[category] = fetch_for_category(
            category, query, api_key, channel_ids,
            max_per_category=max_per_category,
            videos_to_fetch=videos_to_fetch,
            published_after=published_after,
        )

    return results


def merge_videos(existing, new_results):
    """
    Merge new video results into existing accumulated lists.
    Deduplicates by video ID.
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
        merged[category] = combined
    return merged


# Example preferred channel IDs (from original config):
PREFERRED_CHANNEL_IDS = {
    "readings": [
        "UCoNabUSDcUb9iuSr256mLMg",  # Catholic Online
        "UCm-J93kq7CRVSDjG-_0d3rg",  # Amen Hallelujah
        "UC2q9U-x8oGqSmsXnzHfriCw",  # Daily Mass Bible Readings
    ],
    "full_mass": [
        "UC14llXN2ICItA-OF5ci0hLA",  # Father Dave
        "UCZpWMxP4e8sQLZjbYQmanIw",  # Sundays with Ascension
        "UCi6JtCVy4XKu4BSG-AE2chg",  # Daily TV Mass
    ],
    "homily": [
        "UCcMjLgeWNwqL2LBGS-iPb1A",  # Bishop Robert Barron
        "UCZpWMxP4e8sQLZjbYQmanIw",  # Sundays with Ascension
    ],
    "music": [
        "UCS4PpsEMJ9F2_AzQVVMFEFg",  # Sunday 7pm Choir
    ],
}
