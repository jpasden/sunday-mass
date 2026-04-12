import os

_here = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.environ.get("SUNDAY_MASS_APP_DIR")

if _app_dir:
    # OpalStack deployment: everything lives in the same app directory
    APP_DIR = _app_dir
    PUBLIC_DIR = _app_dir
else:
    # Local development: data in repo root, HTML rendered to public/
    APP_DIR = _here
    PUBLIC_DIR = os.path.join(_here, "public")

DATA_FILE = os.path.join(APP_DIR, "data.json")
LOG_FILE = os.path.join(APP_DIR, "logs", "cron.log")

# Anthropic API — set ANTHROPIC_API_KEY in your environment (crontab on OpalStack)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

# Scraping
REQUEST_DELAY_SECONDS = 1.5
