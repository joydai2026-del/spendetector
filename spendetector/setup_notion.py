"""One-time setup: create the Receipts + Items databases inside the shared Spendetector page.

Run after creating the Notion integration and sharing the page with it:

    SPENDETECTOR_PARENT_PAGE_ID=<page-id> NOTION_TOKEN=<token> python -m spendetector.setup_notion

It prints the two database ids to paste into .env. The dashboard charts are then built once in
the Notion UI (the Notion API cannot create chart blocks).
"""

from __future__ import annotations

from .config import CATEGORIES, env
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
