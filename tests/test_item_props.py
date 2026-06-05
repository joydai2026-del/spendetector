"""Unit test for the pure item-property builder (no Notion I/O)."""

from spendetector.extract import Item
from spendetector.notion_io import _item_props


def _item(**kw):
    base = dict(name="Oat Milk", qty=1, unit_price=5.29, total=5.29, category="Groceries",
               confidence=1.0, norm_name="oat milk", food_group="Dairy & Eggs", health_tier="green")
    base.update(kw)
    return Item(**base)


def test_item_props_writes_food_group_and_health_tier():
    p = _item_props(_item(), date_iso="2026-06-04", week="2026-W23", month="2026-06",
                    receipt_id="r1", store="Trader Joe's")
    assert p["Food Group"]["select"]["name"] == "Dairy & Eggs"
    assert p["Health Tier"]["select"]["name"] == "green"
    # the existing fields still come through
    assert p["Category"]["select"]["name"] == "Groceries"
    assert p["Norm Name"]["select"]["name"] == "oat milk"
    assert p["Line Total"]["number"] == 5.29
    assert p["Receipt"]["relation"] == [{"id": "r1"}]


def test_item_props_falls_back_when_store_or_norm_missing():
    p = _item_props(_item(norm_name="", food_group="Other", health_tier="yellow"),
                    date_iso="2026-06-04", week="2026-W23", month="2026-06",
                    receipt_id="r2", store=None)
    assert "Store" not in p and "Norm Name" not in p  # omitted, not blank
    assert p["Food Group"]["select"]["name"] == "Other"
    assert p["Health Tier"]["select"]["name"] == "yellow"
