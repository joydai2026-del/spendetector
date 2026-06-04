"""Compute the single insight line the bot replies with.

Pure and deterministic: it takes the parsed items plus a prior-price lookup and returns one
line. The worker fetches prior prices (from Notion) and composes the full reply around this.

Ladder (first that fires wins):
  1. price_move  - the biggest repeat item that moved >= 10% vs its last price (the demo wow)
  2. biggest     - history exists but nothing moved much -> name the biggest line item
  3. cold_start  - no history at all -> an honest "I am learning your prices" line, never a
                   fabricated delta
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .config import PRICE_MOVE_THRESHOLD
from .extract import Item


@dataclass
class Insight:
    text: str
    kind: str  # "price_move" | "biggest" | "cold_start"


def _month_name(date_iso: str | None) -> str:
    try:
        return dt.date.fromisoformat(date_iso).strftime("%B")
    except (ValueError, TypeError):
        return "earlier"


def compute_insight(
    items: list[Item],
    prior_prices: dict[str, tuple[float, str]],
) -> Insight:
    """`prior_prices` maps norm_name -> (prior_unit_price, prior_date_iso) for seen items."""
    best = None  # ((abs_pct, line_total), pct, item, prior_price, prior_date)
    for it in items:
        if it.unit_price is None or it.norm_name not in prior_prices:
            continue
        prior_price, prior_date = prior_prices[it.norm_name]
        if not prior_price:
            continue
        pct = (it.unit_price - prior_price) / prior_price
        if abs(pct) < PRICE_MOVE_THRESHOLD:
            continue
        key = (abs(pct), it.total or 0)
        if best is None or key > best[0]:
            best = (key, pct, it, prior_price, prior_date)

    if best:
        _, pct, it, prior_price, prior_date = best
        direction = "crept up" if pct > 0 else "dropped"
        return Insight(
            f"Heads up: your {it.norm_name} {direction} {round(abs(pct) * 100)}% since "
            f"{_month_name(prior_date)}, from ${prior_price:.2f} to ${it.unit_price:.2f}.",
            "price_move",
        )

    if not prior_prices:
        return Insight(
            "Saved. This is your first scan, so I am learning your prices now. "
            "Snap a few more and I will start spotting when things quietly go up.",
            "cold_start",
        )

    biggest = max(items, key=lambda i: i.total or 0, default=None)
    if biggest is not None:
        return Insight(f"Biggest item: {biggest.name} at ${biggest.total:.2f}.", "biggest")
    return Insight("Saved.", "biggest")
