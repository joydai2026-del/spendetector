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
    """`prior_prices` maps norm_name -> (baseline_unit_price, baseline_date_iso): the OLDEST
    recorded price, so the line reads "up X% since <baseline month>" (the price-creep pitch)."""
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

    # Only items with a numeric total can be the "biggest" (total may be None after a degraded
    # parse); never format None as dollars.
    priced = [i for i in items if i.total is not None]
    if priced:
        biggest = max(priced, key=lambda i: i.total)
        return Insight(f"Biggest item: {biggest.name} at ${biggest.total:.2f}.", "biggest")
    return Insight("Saved.", "biggest")


@dataclass
class ReceiptReport:
    """The per-receipt report: a headline plus the 'what's notable about THIS receipt' lines."""

    headline: str
    lines: list[str]


def compute_receipt_report(
    items: list[Item],
    baselines: dict[str, tuple[float, str]],
) -> ReceiptReport:
    """Everything findable from a single receipt: price moves vs baseline, where the money went,
    the biggest item, and what is new. `baselines` maps norm_name -> (oldest_price, oldest_date)."""
    moves = []  # (pct, item, old_price, old_date)
    for it in items:
        if it.unit_price is None or it.norm_name not in baselines:
            continue
        old, old_date = baselines[it.norm_name]
        if not old:
            continue
        pct = (it.unit_price - old) / old
        if abs(pct) >= PRICE_MOVE_THRESHOLD:
            moves.append((pct, it, old, old_date))
    moves.sort(key=lambda m: abs(m[0]), reverse=True)

    lines: list[str] = []
    for pct, it, old, old_date in moves:
        direction = "up" if pct > 0 else "down"
        lines.append(
            f"{it.norm_name}: {direction} {round(abs(pct) * 100)}% since {_month_name(old_date)} "
            f"(${old:.2f} to ${it.unit_price:.2f})"
        )

    cats: dict[str, float] = {}
    for it in items:
        if it.total is not None:
            cats[it.category] = cats.get(it.category, 0.0) + it.total
    if cats:
        top = sorted(cats.items(), key=lambda kv: kv[1], reverse=True)[:4]
        lines.append("Where it went: " + ", ".join(f"{c} ${v:.2f}" for c, v in top))

    priced = [i for i in items if i.total is not None]
    if priced:
        biggest = max(priced, key=lambda i: i.total)
        lines.append(f"Biggest item: {biggest.name} (${biggest.total:.2f})")

    new_items = [i for i in items if i.norm_name and i.norm_name not in baselines]
    if new_items:
        lines.append(f"{len(new_items)} item(s) new to your history")

    if moves:
        pct, it, old, old_date = moves[0]
        verb = "crept up" if pct > 0 else "dropped"
        headline = (
            f"Your {it.norm_name} {verb} {round(abs(pct) * 100)}% since {_month_name(old_date)}, "
            f"from ${old:.2f} to ${it.unit_price:.2f}."
        )
    elif not baselines:
        headline = "First scan logged. Snap a few more and price changes will show up here."
    else:
        total = sum(i.total or 0 for i in items)
        headline = f"Logged {len(items)} items for ${total:.2f}. No big price jumps this time."

    return ReceiptReport(headline=headline, lines=lines)
