from spendetector.config import CATEGORIES
from spendetector.extract import RECEIPT_SCHEMA, SYSTEM_PROMPT, to_receipt


def test_to_receipt_shape(raw_whole_foods):
    r = to_receipt(raw_whole_foods)
    assert r.is_receipt is True
    assert r.store == "Whole Foods Market"
    assert len(r.items) == 6
    assert all(it.category in CATEGORIES for it in r.items)
    assert all(it.norm_name for it in r.items)


def test_oat_milk_normalized(raw_whole_foods):
    r = to_receipt(raw_whole_foods)
    oat = next(it for it in r.items if "oat" in it.name.lower())
    assert oat.norm_name == "oat milk"


def test_unit_price_filled_from_total(raw_whole_foods):
    r = to_receipt(raw_whole_foods)
    choc = next(it for it in r.items if "chocolate" in it.name.lower())
    # 8.97 / 3 = 2.99 (was null in the raw model output)
    assert choc.unit_price == 2.99


def test_unknown_category_coerced_to_other():
    data = {
        "is_receipt": True,
        "store": "X",
        "date": "2026-06-01",
        "items": [
            {"name": "Mystery", "qty": 1, "unit_price": 1.0, "total": 1.0, "category": "Gizmos", "confidence": 1.0}
        ],
        "subtotal": 1.0,
        "tax": 0.0,
        "total": 1.0,
    }
    r = to_receipt(data)
    assert r.items[0].category == "Other"


def test_schema_and_prompt_never_carry_card_digits():
    schema_text = str(RECEIPT_SCHEMA).lower()
    for forbidden in ("card", "last4", "last_4", "account", "pan"):
        assert forbidden not in schema_text
    assert "never output any card" in SYSTEM_PROMPT.lower()


def test_non_receipt_passthrough():
    r = to_receipt({"is_receipt": False, "store": None, "date": None, "items": [],
                    "subtotal": None, "tax": None, "total": None})
    assert r.is_receipt is False
    assert r.items == []
