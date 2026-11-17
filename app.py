"""Entry point for Vercel's Python runtime (it looks for a FastAPI `app` in app.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pricewatch.web import app  # noqa: E402

__all__ = ["app"]
