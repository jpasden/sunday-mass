#!/usr/bin/env python3
"""
Reads data.json and renders index.html via Jinja2 template.
"""

import datetime
import json
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jinja2 import Environment, FileSystemLoader

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def load_data():
    if not os.path.exists(config.DATA_FILE):
        log.error("data.json not found at %s", config.DATA_FILE)
        sys.exit(1)
    with open(config.DATA_FILE, "r") as f:
        return json.load(f)


def main():
    data = load_data()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(script_dir, "templates")

    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    template = env.get_template("index.html.j2")

    # Trim displayed videos to MAX_VIDEOS_PER_CATEGORY
    videos = data.get("videos", {})
    displayed_videos = {
        cat: videos.get(cat, [])[:config.MAX_VIDEOS_PER_CATEGORY]
        for cat in ("readings", "full_mass", "homily", "music")
    }

    # Format date as "March 15th, 2026"
    sunday_date_str = data.get("sunday_date", "")
    try:
        d = datetime.datetime.strptime(sunday_date_str, "%Y-%m-%d")
        day = d.day
        suffix = "th" if 11 <= day <= 13 else {1:"st", 2:"nd", 3:"rd"}.get(day % 10, "th")
        sunday_date_display = d.strftime("%B ") + str(day) + suffix + d.strftime(", %Y")
    except ValueError:
        sunday_date_display = sunday_date_str

    html = template.render(
        sunday_date=sunday_date_display,
        liturgical_name=data.get("liturgical_name", ""),
        readings=data.get("readings", {}),
        videos=displayed_videos,
        last_updated=data.get("last_updated", ""),
    )

    os.makedirs(config.PUBLIC_DIR, exist_ok=True)
    out_path = os.path.join(config.PUBLIC_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    log.info("Rendered index.html to %s", out_path)

    # Copy favicon into public dir
    favicon_src = os.path.join(script_dir, "favicon.svg")
    favicon_dst = os.path.join(config.PUBLIC_DIR, "favicon.svg")
    if os.path.exists(favicon_src) and os.path.abspath(favicon_src) != os.path.abspath(favicon_dst):
        shutil.copy2(favicon_src, favicon_dst)


if __name__ == "__main__":
    main()
