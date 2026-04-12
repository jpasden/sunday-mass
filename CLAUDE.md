# sunday-mass — Automated Mass Readings Site

Fully automated static site showing the upcoming Sunday's Catholic Mass readings and curated YouTube videos (full masses, homilies, music). Cron job regenerates it; no manual updates once deployed.

**Spec:** `sunday_mass_site_spec.md`
**Deployed to:** `~/apps/sunday-mass/` on OpalStack shared server

## Tech Stack
- Python 3
- requests + BeautifulSoup4 (scrape Catholic.org for readings)
- YouTube Data API v3 (key in `config.py`)
- Jinja2 templates → static `public/index.html`
- `data.json` as persistent cache (videos accumulate, never deleted)
- User-level cron (`crontab -e`, no root)

## Key Behavior
- On Mondays, targets the *previous* Sunday (not next)
- Videos accumulate across cron runs — new ones merged in, none removed
- `scraper.py` handles both readings and YouTube; `render.py` generates HTML

## Git Workflow
At the end of every session, before stopping:
1. Run `git add -A`
2. Run `git commit -m "Session: <brief summary of what changed>"`
3. Run `git push origin main`

Always do this unless I explicitly say "don't push."
