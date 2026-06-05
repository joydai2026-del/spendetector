"""Backfill Food Group + Health Tier onto existing Item rows by classifying their stored names.

Earlier rows were written before these two fields existed. This collects the unique item names
already in Notion and classifies each (food_group + health_tier) in ONE model call, then patches
every row by name. Classifying the names actually stored (rather than matching a fresh
re-extraction) gives full coverage and avoids normalized-name drift. Idempotent: re-running just
re-sets the same values.

    set -a; . ./.env; set +a
    PYTHONPATH=. .venv/bin/python scripts/backfill_food_health.py
"""

from __future__ import annotations

import json
import os

from spendetector.config import (
    FALLBACK_FOOD_GROUP,
    FALLBACK_HEALTH_TIER,
    FOOD_GROUP_ORDER,
    HEALTH_TIERS,
    OPENAI_MODEL,
    env,
)
from spendetector.notion_io import _patch, _post, _select


def _norm(r) -> str | None:
    return (r["properties"].get("Norm Name", {}).get("select") or {}).get("name")


def all_items() -> list:
    db = os.environ["SPENDETECTOR_ITEMS_DB_ID"]
    rows, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = _post(f"/databases/{db}/query", body)
        rows += data.get("results", [])
        if not data.get("has_more"):
            return rows
        cursor = data["next_cursor"]


def classify(names: list[str]) -> dict[str, tuple[str, str]]:
    """One structured-output call: each grocery item name -> (food_group, health_tier)."""
    from openai import OpenAI

    schema = {
        "type": "object", "additionalProperties": False, "required": ["items"],
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "food_group", "health_tier"],
            "properties": {
                "name": {"type": "string"},
                "food_group": {"type": "string", "enum": FOOD_GROUP_ORDER},
                "health_tier": {"type": "string", "enum": HEALTH_TIERS},
            }}}},
    }
    system = (
        "Classify each grocery item name into a food_group and a health_tier. "
        "health_tier: green = whole/nutritious (fresh produce, lean proteins, plain dairy, eggs, "
        "whole grains, nuts), yellow = neutral/processed staples (bread, pantry, oils, butter), "
        "red = treats (sweets, soda, chips, candy, dessert). Non-food items are Household + yellow. "
        "Return exactly one entry per input name, echoing the name verbatim."
    )
    client = OpenAI(api_key=env("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=OPENAI_MODEL, temperature=0,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": "Classify these item names:\n" + "\n".join(names)}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "classes", "strict": True, "schema": schema}},
        max_tokens=4000,
    )
    out = json.loads(resp.choices[0].message.content)
    return {e["name"]: (e["food_group"], e["health_tier"]) for e in out["items"]}


def main() -> None:
    rows = all_items()
    names = sorted({n for n in (_norm(r) for r in rows) if n})
    print(f"{len(rows)} rows, {len(names)} unique item names.")
    cmap = classify(names)
    print(f"Classified {len(cmap)} names in one model call.")

    patched = miss = 0
    for r in rows:
        nn = _norm(r)
        fg, ht = cmap.get(nn, (FALLBACK_FOOD_GROUP, FALLBACK_HEALTH_TIER))
        if nn not in cmap:
            miss += 1
        _patch(f"/pages/{r['id']}",
               {"properties": {"Food Group": _select(fg), "Health Tier": _select(ht)}})
        patched += 1
    print(f"Patched {patched} rows ({miss} fallback to {FALLBACK_FOOD_GROUP}/{FALLBACK_HEALTH_TIER}).")


if __name__ == "__main__":
    main()
