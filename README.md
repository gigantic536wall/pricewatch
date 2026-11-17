# PriceWatch: price tracker for online shops

Tracks product prices on online shops, stores the full price history in PostgreSQL and sends an alert when a price drops below your target.

> 🚧 Work in progress: webhook alerts, dashboard and live demo are coming next.

## Highlights

- **Reads prices like a search engine does.** Uses the structured data most shops publish for Google Shopping (JSON-LD and schema.org microdata) and falls back to a CSS selector only when needed. Much more robust than scraping page text.
- **Understands European price formats:** `1.299,00 €`, `€1,299.99`, `1 299,50 zł`, `CHF 49.–`, `CHF 1'249.90`, `2.499 Kč`, `199 kr`.
- **Stock status** from schema.org availability (in stock / sold out).
- **Polite scraping:** respects `robots.txt` and its `Crawl-delay`, identifies itself with a clear User-Agent, waits between requests to the same shop, loads several shops in parallel.
- **Resilient:** retries timeouts, `429` and `5xx` with exponential backoff and honours `Retry-After`; never retries `404`.
- **Smart alerts:** fires once when a price crosses your target (not on every run), on big drops (≥ 10 %) and when a product is back in stock.
- **Clean data model:** every check is stored, a database constraint guarantees each check has either a price or an error.
- **Demo shop included** ("Kaffeewerk"): a small fake shop with daily changing prices in all three markup styles, so the project can be demoed and tested without scraping real websites.

## Tech stack

Python 3.13 · asyncio · FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Alembic · httpx · selectolax · Typer · pytest · respx · Ruff · uv

## Roadmap

- [x] Price parsing for European formats + tests
- [x] Price extraction: JSON-LD, microdata, CSS selector + tests
- [x] Database schema and migrations
- [x] Demo shop with realistic daily price changes
- [x] Polite fetcher: robots.txt, per-host delay, concurrency limit, retries + tests
- [x] Tracker with price events and a CLI
- [x] Integration tests against PostgreSQL and the in-process demo shop
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

Try it with the bundled demo shop:

```bash
uv run pricewatch demo-shop             # terminal 1: shop on http://127.0.0.1:8001/shop/
uv run pricewatch add-demo              # terminal 2: track its 6 products
uv run pricewatch check                 # fetch prices once
uv run pricewatch list                  # latest prices and targets
```

Track any product page:

```bash
uv run pricewatch add "https://shop.example/p/123" --target 199
uv run pricewatch add "https://other.example/item" --selector ".price" --currency EUR
```

Integration tests use a separate database set in `PRICEWATCH_TEST_DATABASE_URL` (see `.env.example`); without it they are skipped.
