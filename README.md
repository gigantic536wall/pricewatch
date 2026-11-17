# PriceWatch: price tracker for online shops

Tracks product prices on online shops, stores the full price history in PostgreSQL and sends an alert when a price drops below your target.

> 🚧 Work in progress: dashboard, alerts and live demo are coming next.

## Highlights

- **Reads prices like a search engine does.** Uses the structured data most shops publish for Google Shopping (JSON-LD and schema.org microdata) and falls back to a CSS selector only when needed. Much more robust than scraping page text.
- **Understands European price formats:** `1.299,00 €`, `€1,299.99`, `1 299,50 zł`, `CHF 49.–`, `CHF 1'249.90`, `2.499 Kč`, `199 kr`.
- **Stock status** from schema.org availability (in stock / sold out).
- **Polite scraping:** respects `robots.txt`, identifies itself with a clear User-Agent, limits requests per host.
- **Clean data model:** every check is stored, a database constraint guarantees each check has either a price or an error.
- **Demo shop included** ("Kaffeewerk"): a small fake shop with daily changing prices in all three markup styles, so the project can be demoed and tested without scraping real websites.

## Tech stack

Python 3.13 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Alembic · httpx · selectolax · pytest · Ruff · uv

## Roadmap

- [x] Price parsing for European formats + tests
- [x] Price extraction: JSON-LD, microdata, CSS selector + tests
- [x] Database schema and migrations
- [x] Demo shop with realistic daily price changes
- [ ] Polite fetcher (robots.txt, rate limits, retries) and scheduled checks
- [ ] Price-drop alerts (webhooks: Discord, Slack, ntfy …)
- [ ] Dashboard with price charts and SQL analytics
- [ ] Docker, CI and live demo

## Run locally

Requirements: [uv](https://docs.astral.sh/uv/), PostgreSQL.

```bash
uv sync
cp .env.example .env        # then set your PostgreSQL password
uv run alembic upgrade head # create tables
uv run pytest               # run the tests
```
