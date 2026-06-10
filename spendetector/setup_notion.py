"""One-time setup: create the Receipts + Items databases inside the shared Spendetector page.

Run after creating the Notion integration and sharing the page with it:

    SPENDETECTOR_PARENT_PAGE_ID=<page-id> NOTION_TOKEN=<token> .venv/bin/python -m spendetector.setup_notion

It prints the two database ids to paste into .env. Dashboard chart views are created once through
Notion tooling and then configured by scripts/configure_charts.py. Page layout remains a Notion
presentation task: arrange the views into a readable demo dashboard.
"""

from __future__ import annotations

from .config import CATEGORIES, FOOD_GROUP_ORDER, HEALTH_TIERS, env
from .notion_io import _post

RECEIPTS_PROPERTIES = {
    "Title": {"title": {}},
    "Store": {"select": {}},
    "Date": {"date": {}},
    "Subtotal": {"number": {}},
    "Tax": {"number": {}},
    "Total": {"number": {}},
    "Item Count": {"number": {}},
    "Receipt Photo": {"files": {}},
    "Telegram Update ID": {"number": {}},
    "Image Hash": {"rich_text": {}},  # sha256 of the photo, for same-photo idempotency
    "Status": {
        "select": {
            "options": [{"name": "complete"}, {"name": "partial"}, {"name": "failed"}]
        }
    },
}

ITEMS_PROPERTIES = {
    "Item": {"title": {}},
    "Norm Name": {"select": {}},
    "Category": {"select": {"options": [{"name": c} for c in CATEGORIES]}},
    "Food Group": {"select": {"options": [{"name": g} for g in FOOD_GROUP_ORDER]}},
    "Health Tier": {"select": {"options": [{"name": t} for t in HEALTH_TIERS]}},
    "Qty": {"number": {}},
    "Unit Price": {"number": {}},
    "Line Total": {"number": {}},
    "Store": {"select": {}},
    "Date": {"date": {}},
    "Week": {"select": {}},
    "Month": {"select": {}},
}


def _create_database(parent_page_id: str, title: str, properties: dict) -> dict:
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    }
    return _post("/databases", payload)


def main() -> None:
    parent = env("SPENDETECTOR_PARENT_PAGE_ID")
    receipts = _create_database(parent, "Spendetector Receipts", RECEIPTS_PROPERTIES)
    items_props = dict(ITEMS_PROPERTIES)
    items_props["Receipt"] = {
        "relation": {"database_id": receipts["id"], "single_property": {}}
    }
    items = _create_database(parent, "Spendetector Items", items_props)

    print("Created databases. Paste these into .env:\n")
    print(f"SPENDETECTOR_RECEIPTS_DB_ID={receipts['id']}")
    print(f"SPENDETECTOR_ITEMS_DB_ID={items['id']}")


if __name__ == "__main__":
    main()
