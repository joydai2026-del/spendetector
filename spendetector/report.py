"""The per-receipt report: a fun, engaging breakdown of one receipt.

Research-grounded (Nutri-Score / Kroger OptUp green-yellow-red health tiering; item-level +
humorous insights per the receipt-app research). Leads with insights, scores the basket's
health, names a playful "vibe", watches for shrinkflation, projects a riser forward, and groups
items by food type. The worker pairs this with an AI-generated image of the haul.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .config import FOOD_GROUP_ORDER, PRICE_MOVE_THRESHOLD
from .extract import Receipt

_GRADE_THRESHOLDS = [(0.70, "A"), (0.55, "B"), (0.40, "C"), (0.20, "D")]
_VIBES = {
    "Produce": ("Veggie Forward", "\U0001f966"),
    "Meat & Seafood": ("Protein Beast", "\U0001f4aa"),
    "Dairy & Eggs": ("Dairy Devotee", "\U0001f9c0"),
    "Bakery & Grains": ("Carb Curious", "\U0001f35e"),
    "Pantry": ("Home Cook", "\U0001f373"),
    "Snacks & Sweets": ("Treat Yourself", "\U0001f36a"),
    "Beverages": ("Sip Happens", "\U0001f964"),
    "Frozen": ("Freezer Stocker", "\U0001f9ca"),
}


@dataclass
class ReceiptReport:
    headline: str
    insights: list[str]
    groups: list  # list[tuple[str, list[Item]]], ordered by FOOD_GROUP_ORDER
    grade: str = "C"
    group_percents: list = None  # [(group_name, pct_of_spend)], biggest first
    alert: str = ""  # short top price alert for the image, e.g. "eggs up 50% since March"


def _month(date_iso: str | None) -> str:
    try:
        return dt.date.fromisoformat(date_iso).strftime("%B")
    except (ValueError, TypeError):
        return "earlier"


def _grade(green_fraction: float) -> str:
    for threshold, grade in _GRADE_THRESHOLDS:
        if green_fraction >= threshold:
            return grade
    return "D"


def _months_between(start_iso: str, end_iso: str | None) -> float:
    try:
        a = dt.date.fromisoformat(start_iso)
        b = dt.date.fromisoformat(end_iso) if end_iso else dt.date.today()
        return max((b - a).days / 30.0, 0.5)
    except (ValueError, TypeError):
        return 1.0


def build_receipt_report(receipt: Receipt, baselines: dict[str, tuple[float, str]]) -> ReceiptReport:
    items = receipt.items
    total = sum(i.total or 0 for i in items)

    # --- health tiers (green = whole/nutritious, red = treat) ---
    tiers = {"green": 0, "yellow": 0, "red": 0}
    for it in items:
        tiers[it.health_tier if it.health_tier in tiers else "yellow"] += 1
    grade = _grade(tiers["green"] / max(len(items), 1))

    # --- food-group grouping + spend ---
    spend_by_group: dict[str, float] = {}
    items_by_group: dict[str, list] = {}
    for it in items:
        g = it.food_group if it.food_group in FOOD_GROUP_ORDER else "Other"
        spend_by_group[g] = spend_by_group.get(g, 0.0) + (it.total or 0)
        items_by_group.setdefault(g, []).append(it)
    groups = [(g, items_by_group[g]) for g in FOOD_GROUP_ORDER if g in items_by_group]

    # --- price moves vs baseline ---
    moves = []
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
    ups = [m for m in moves if m[0] > 0]

    insights: list[str] = []

    treats = f", {tiers['red']} treats." if tiers["red"] else "."
    insights.append(
        f"\U0001f957 Health score {grade}: {tiers['green']} of {len(items)} picks are whole foods{treats}"
    )

    spendable = {g: v for g, v in spend_by_group.items() if g not in ("Household", "Other") and v > 0}
    if spendable:
        top = max(spendable, key=spendable.get)
        if top in _VIBES:
            name, emoji = _VIBES[top]
            insights.append(f"{emoji} Today's vibe: {name} ({top} led at ${spend_by_group[top]:.2f}).")

    for pct, it, old, old_date in moves[:4]:
        arrow = "\U0001f53a" if pct > 0 else "\U0001f53b"
        word = "up" if pct > 0 else "down"
        insights.append(
            f"{arrow} {it.norm_name} {word} {round(abs(pct) * 100)}% since {_month(old_date)} "
            f"(${old:.2f} to ${it.unit_price:.2f})."
        )

    if ups and receipt.date:
        pct, it, old, old_date = ups[0]
        rate = (it.unit_price - old) / _months_between(old_date, receipt.date)  # $/month
        try:
            months_to_dec = max(12 - dt.date.fromisoformat(receipt.date).month, 1)
        except (ValueError, TypeError):
            months_to_dec = 6
        projected = it.unit_price + rate * months_to_dec
        if projected > it.unit_price * 1.05:
            insights.append(f"\U0001f52e At this pace, {it.norm_name} could near ${projected:.2f} by December.")

    top_groups = sorted(spend_by_group.items(), key=lambda kv: kv[1], reverse=True)[:3]
    if top_groups:
        insights.append("\U0001f9fa Where it went: " + ", ".join(f"{g} ${v:.2f}" for g, v in top_groups))

    priced = [i for i in items if i.total is not None]
    with_unit = [i for i in items if i.unit_price is not None]
    if priced and with_unit:
        splurge = max(priced, key=lambda i: i.total)
        value = min(with_unit, key=lambda i: i.unit_price)
        insights.append(
            f"\U0001f3c6 Best value: {value.name} (${value.unit_price:.2f}). "
            f"\U0001f4b8 Splurge: {splurge.name} (${splurge.total:.2f})."
        )

    store = receipt.store or "the store"
    insights.append(
        f"\U0001f3e6 Your bank will just say “{store} ${total:.2f}.” "
        f"Now you know it was {len(items)} items across {len(groups)} food groups."
    )

    new = list(dict.fromkeys(i.norm_name for i in items if i.norm_name and i.norm_name not in baselines))
    if new:
        insights.append(f"\U0001f195 First time buying: {', '.join(new)[:120]}.")

    if ups:
        pct, it, old, old_date = ups[0]
        headline = (
            f"\U0001f62e Your {it.norm_name} jumped {round(pct * 100)}% since {_month(old_date)}, "
            f"and this haul scores {grade} for health."
        )
    elif not baselines:
        headline = f"First scan logged, health score {grade}. Snap a few more to unlock price tracking."
    else:
        headline = f"Logged {len(items)} items for ${total:.2f}. Health score {grade}, no big price jumps."

    group_percents = sorted(
        ((g, (v / total * 100) if total else 0.0) for g, v in spend_by_group.items()),
        key=lambda x: -x[1],
    )
    alert = ""
    if ups:
        pct, it, old, old_date = ups[0]
        alert = f"{it.norm_name} up {round(pct * 100)}% since {_month(old_date)}"

    return ReceiptReport(headline=headline, insights=insights, groups=groups,
                         grade=grade, group_percents=group_percents, alert=alert)
