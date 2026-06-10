"""Notion-triggered worker helpers.

This is the bridge for future Notion buttons / database automations. Notion sends a webhook,
Modal verifies a secret, then this module computes a price-watch summary from the Items DB and
optionally writes it to a Watchlist DB.
"""

from __future__ import annotations

import hmac

from . import notion_io
from .config import env_optional


def verify_notion_secret(header_value: str | None) -> bool:
    """Fail closed unless NOTION_WORKER_SECRET matches or insecure local dev is enabled."""
    expected = env_optional("NOTION_WORKER_SECRET")
    if not expected:
        return env_optional("SPENDETECTOR_ALLOW_INSECURE") == "1"
    return hmac.compare_digest(header_value or "", expected)


def norm_name_from_payload(payload: dict) -> str:
    """Accept a tiny direct payload or a Notion-style properties payload."""
    direct = payload.get("norm_name") or payload.get("Norm Name") or payload.get("item")
    if isinstance(direct, str) and direct.strip():
        return direct.strip().lower()

    props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
    prop = props.get("Norm Name") or props.get("Item")
    if isinstance(prop, str) and prop.strip():
        return prop.strip().lower()
    if isinstance(prop, dict):
        select = prop.get("select") or {}
        if isinstance(select, dict) and select.get("name"):
            return str(select["name"]).strip().lower()
        title = prop.get("title") or []
        if title:
            text = "".join(t.get("plain_text", "") for t in title if isinstance(t, dict))
            if text.strip():
                return text.strip().lower()
    raise ValueError("Missing norm_name")


def build_watch_summary(norm_name: str, *, notion=notion_io) -> dict:
    series = notion.find_price_series(norm_name)
    if len(series) < 2:
        raise ValueError(f"Need at least two prices to watch {norm_name!r}")
    first = series[0]
    latest = series[-1]
    baseline = first["unit_price"]
    current = latest["unit_price"]
    change_fraction = round((current - baseline) / baseline, 4) if baseline else 0.0
    change_pct_label = round(change_fraction * 100, 1)
    label = latest.get("item") or norm_name.title()
    direction = "up" if change_fraction > 0 else "down" if change_fraction < 0 else "flat"
    return {
        "label": label,
        "norm_name": norm_name,
        "status": "Watching",
        "first_date": first["date"],
        "latest_date": latest["date"],
        "baseline_price": baseline,
        "latest_price": current,
        "change_pct": change_fraction,
        "notes": (
            f"{norm_name} is {direction} {abs(change_pct_label):g}% "
            f"from ${baseline:.2f} to ${current:.2f}."
        ),
    }


def handle_watch_item(payload: dict, *, notion=notion_io) -> dict:
    norm_name = norm_name_from_payload(payload)
    summary = build_watch_summary(norm_name, notion=notion)
    written = notion.write_watchlist_summary(summary)
    return {"ok": True, "summary": summary, "watchlist_row_url": (written or {}).get("url")}
