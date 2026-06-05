"""Configure the Spendetector dashboard chart aggregations via the Notion public API.

Why this exists: the Notion MCP / view DSL can CREATE chart views (type, grouping, filter) but
cannot set the value-axis aggregation, so charts default to COUNTING rows. The public
`PATCH /v1/views/{id}` CAN set it (configuration.y_axis = {aggregator, property_id}). This sets
each chart to the right Sum / Average. Idempotent: safe to re-run.

    set -a; . ./.env; set +a
    .venv/bin/python scripts/configure_charts.py
"""

from __future__ import annotations

import json
import os
from urllib.parse import unquote

import httpx

H = {
    "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
    "Notion-Version": "2025-09-03",
    "Content-Type": "application/json",
}
API = "https://api.notion.com/v1"

# Desired value-axis per chart (by chart name). Everything else (x-axis, filter) is left as is.
WANT = {
    "Spend by Category": ("sum", "Line Total"),
    "Spend by Food Group": ("sum", "Line Total"),
    "Spend by Week": ("sum", "Line Total"),
    "Oat Milk price over time": ("average", "Unit Price"),
    # "Health mix" intentionally omitted: a COUNT of green/yellow/red items is the right metric.
}


def main() -> None:
    db = httpx.get(f"{API}/databases/{os.environ['SPENDETECTOR_ITEMS_DB_ID']}", headers=H, timeout=30).json()
    ds_id = db["data_sources"][0]["id"]
    ds = httpx.get(f"{API}/data_sources/{ds_id}", headers=H, timeout=30).json()
    # property ids come URL-encoded from the data source but views use the decoded form
    prop_id = {name: unquote(p["id"]) for name, p in ds["properties"].items()}

    listing = httpx.get(f"{API}/views?data_source_id={ds_id}", headers=H, timeout=30).json()
    view_ids = [v["id"] for v in listing.get("results", [])]
    if not view_ids:
        print("Could not list views:", json.dumps(listing)[:300])
        return

    for vid in view_ids:
        v = httpx.get(f"{API}/views/{vid}", headers=H, timeout=30).json()
        name = v.get("name")
        if v.get("type") != "chart" or name not in WANT:
            continue
        agg, prop_name = WANT[name]
        cfg = v["configuration"]
        cfg["y_axis"] = {"aggregator": agg, "property_id": prop_id[prop_name]}
        r = httpx.patch(f"{API}/views/{vid}", headers=H, json={"configuration": cfg}, timeout=30).json()
        if r.get("object") == "view":
            print(f"OK {name}: y={json.dumps(r['configuration']['y_axis'])}")
        else:
            print(f"ERR {name}: {r.get('code')} {r.get('message')}")


if __name__ == "__main__":
    main()
