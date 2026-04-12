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
    with open(config.DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def pair_readings(adult_readings, kids_readings):
    """
    Zip adult and kids paragraph lists into paired dicts for side-by-side rendering.
    Returns {key: {"citation": str, "pairs": [{"adult": str, "kids": str}, ...]}}
    """
    kids_readings = kids_readings or {}
    result = {}
    for key in ["first_reading", "second_reading", "gospel"]:
        if key not in adult_readings:
            continue
        adult = adult_readings[key]
        kids = kids_readings.get(key, {})
        adult_paras = adult.get("paragraphs", [])
        kids_paras = kids.get("paragraphs", [])
        length = max(len(adult_paras), len(kids_paras))
        pairs = [
            {
                "adult": adult_paras[i] if i < len(adult_paras) else "",
                "kids":  kids_paras[i]  if i < len(kids_paras)  else "",
            }
            for i in range(length)
        ]
        result[key] = {"citation": adult.get("citation", ""), "pairs": pairs}
    return result


def format_date(sunday_date_str):
    try:
        d = datetime.datetime.strptime(sunday_date_str, "%Y-%m-%d")
        day = d.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return d.strftime("%B ") + str(day) + suffix + d.strftime(", %Y")
    except ValueError:
        return sunday_date_str


def main():
    data = load_data()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    env = Environment(
        loader=FileSystemLoader(os.path.join(script_dir, "templates")),
        autoescape=True,
    )
    template = env.get_template("index.html.j2")

    html = template.render(
        sunday_date=format_date(data.get("sunday_date", "")),
        liturgical_name=data.get("liturgical_name", ""),
        readings_en=pair_readings(data.get("readings_en", {}), data.get("readings_en_kids", {})),
        readings_es=pair_readings(data.get("readings_es", {}), data.get("readings_es_kids", {})),
        notes_en=data.get("notes_en", {}),
        notes_en_kids=data.get("notes_en_kids", {}),
        notes_es=data.get("notes_es", {}),
        notes_es_kids=data.get("notes_es_kids", {}),
        last_updated=data.get("last_updated", ""),
    )

    os.makedirs(config.PUBLIC_DIR, exist_ok=True)
    out_path = os.path.join(config.PUBLIC_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    log.info("Rendered index.html to %s", out_path)

    # Archive a dated copy alongside index.html
    sunday_date_str = data.get("sunday_date", "")
    if sunday_date_str:
        archive_name = f"{sunday_date_str}_mass_readings.html"
        archive_path = os.path.join(config.PUBLIC_DIR, archive_name)
        shutil.copy2(out_path, archive_path)
        log.info("Archived to %s", archive_path)

    favicon_src = os.path.join(script_dir, "favicon.svg")
    favicon_dst = os.path.join(config.PUBLIC_DIR, "favicon.svg")
    if os.path.exists(favicon_src) and os.path.abspath(favicon_src) != os.path.abspath(favicon_dst):
        shutil.copy2(favicon_src, favicon_dst)


if __name__ == "__main__":
    main()
