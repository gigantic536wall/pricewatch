"""Build step on Vercel: apply database migrations; in demo mode, set up the demo data once."""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from pricewatch.config import get_settings  # noqa: E402
from pricewatch.db import engine, session_scope  # noqa: E402
from pricewatch.demo import ensure_demo_products  # noqa: E402
from pricewatch.models import PriceCheck  # noqa: E402
from pricewatch.seed import seed_demo_history  # noqa: E402


def migrate() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")
    print("Migrations applied.")


async def setup_demo() -> None:
    domain = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
    if not get_settings().demo_mode or not domain:
        print("Demo mode off (or no production URL): skipping demo data.")
        return
    async with session_scope() as session:
        added = await ensure_demo_products(session, f"https://{domain}")
        if added or not await session.scalar(select(func.count()).select_from(PriceCheck)):
            created = await seed_demo_history(session, days=90)
            print(f"Demo: {added} products added, {created} past prices created.")
        else:
            print("Demo data already present.")
    await engine.dispose()


if __name__ == "__main__":
    migrate()
    asyncio.run(setup_demo())
