"""Small server-side SVG charts: no JavaScript library and no CDN needed."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from html import escape

from .analytics import Point


def _scale(values: Sequence[float], lo: float, hi: float, out_lo: float, out_hi: float) -> list[float]:
    span = hi - lo or 1.0
    return [out_lo + (v - lo) / span * (out_hi - out_lo) for v in values]


def sparkline(points: Sequence[Point], width: int = 120, height: int = 32) -> str:
    if len(points) < 2:
        return ""
    prices = [float(p.price) for p in points]
    xs = _scale(range(len(prices)), 0, len(prices) - 1, 1, width - 1)
    ys = _scale(prices, min(prices), max(prices), height - 3, 3)
    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=True))
    trend = "down" if prices[-1] < prices[0] else "up" if prices[-1] > prices[0] else "flat"
    return (
        f'<svg class="spark {trend}" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="Price trend"><polyline points="{coords}"/></svg>'
    )


def line_chart(
    points: Sequence[Point],
    *,
    currency: str | None,
    target: Decimal | None = None,
    width: int = 760,
    height: int = 260,
) -> str:
    """Price history with area fill, target line, axis labels and hover titles."""
    if not points:
        return '<p class="muted">No price history yet.</p>'
    left, right, top, bottom = 56, 12, 14, 28
    prices = [float(p.price) for p in points]
    lo_v = min(prices + ([float(target)] if target is not None else []))
    hi_v = max(prices + ([float(target)] if target is not None else []))
    pad = (hi_v - lo_v) * 0.1 or hi_v * 0.05 or 1
    lo_v, hi_v = lo_v - pad, hi_v + pad

    n = len(points)
    xs = _scale(range(n), 0, max(n - 1, 1), left, width - right)
    ys = _scale(prices, lo_v, hi_v, height - bottom, top)
    cur = escape(currency or "")
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Price history over {n} days">']

    for i in range(5):  # horizontal grid with price labels
        v = lo_v + (hi_v - lo_v) * i / 4
        (y,) = _scale([v], lo_v, hi_v, height - bottom, top)
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{v:,.0f}</text>')

    for i in sorted({0, n // 2, n - 1}):  # dates: first, middle, last
        anchor = "start" if i == 0 else "end" if i == n - 1 else "middle"
        label = points[i].day.strftime("%d %b")
        parts.append(f'<text class="axis" x="{xs[i]:.1f}" y="{height - 8}" text-anchor="{anchor}">{label}</text>')

    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=True))
    area = f"M{xs[0]:.1f},{height - bottom} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=True))
    parts.append(f'<path class="area" d="{area} L{xs[-1]:.1f},{height - bottom} Z"/>')
    parts.append(f'<polyline class="line" points="{coords}"/>')

    if target is not None:
        (ty,) = _scale([float(target)], lo_v, hi_v, height - bottom, top)
        parts.append(f'<line class="target" x1="{left}" x2="{width - right}" y1="{ty:.1f}" y2="{ty:.1f}"/>')
        parts.append(f'<text class="target-label" x="{width - right}" y="{ty - 5:.1f}" text-anchor="end">')
        parts.append(f"target {target:,.2f} {cur}</text>")

    for p, x, y in zip(points, xs, ys, strict=True):
        cls = "dot sold-out" if p.in_stock is False else "dot"
        stock = " · sold out" if p.in_stock is False else ""
        parts.append(
            f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="3">'
            f"<title>{p.day:%d %b %Y}: {p.price:,.2f} {cur}{stock}</title></circle>"
        )
    parts.append("</svg>")
    return "".join(parts)
