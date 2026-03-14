#!/usr/bin/env python3
"""
Reads data.json and renders index.html via Jinja2 template.
"""

import json
import logging
import os
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
        for cat in ("full_mass", "homily", "music")
    }

    html = template.render(
        sunday_date=data.get("sunday_date", ""),
        liturgical_name=data.get("liturgical_name", ""),
        readings=data.get("readings", {}),
        videos=displayed_videos,
        last_updated=data.get("last_updated", ""),
    )

    os.makedirs(config.PUBLIC_DIR, exist_ok=True)
    out_path = os.path.join(config.PUBLIC_DIR, "index.html")
    with open(out_path, "w") as f:
        f.write(html)

    log.info("Rendered index.html to %s", out_path)


if __name__ == "__main__":
    main()
