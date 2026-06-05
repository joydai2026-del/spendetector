"""Round-2 hardening tests: defensive extraction, Notion payload safety, reply extras."""

import httpx

from spendetector import notion_io, reply
from spendetector.extract import Item, Receipt, to_receipt
from spendetector.insight import Insight


def _item(**kw):
    base = {
        "name": "Z",
        "qty": 1,
        "unit_price": 1.0,
        "total": 1.0,
        "category": "Other",
        "confidence": 1.0,
    }
    base.update(kw)
    return base


def _data(items, **kw):
    base = {"is_receipt": True, "store": "X", "date": "2026-06-01",
            "subtotal": None, "tax": None, "total": None}
    base.update(kw)
    base["items"] = items
    return base


# --- Defensive extraction (adversarial / partial model output must not crash) ---
def test_bad_date_is_dropped_so_buckets_never_crash():
    assert to_receipt(_data([], date="June 3rd")).date is None


def test_missing_item_name_defaults():
    raw = _item()
    del raw["name"]
    assert to_receipt(_data([raw])).items[0].name == "Item"


def test_non_numeric_fields_coerced():
    it = to_receipt(_data([_item(qty="two", unit_price="abc", total="5.00", confidence="hi")])).items[0]
    assert it.qty == 1.0            # "two" -> None -> default 1.0
    assert it.total == 5.0          # "5.00" -> 5.0
    assert it.unit_price == 5.0     # derived from total / qty
    assert it.confidence == 1.0     # "hi" -> None -> default 1.0


def test_card_digits_scrubbed_from_item_names_and_store():
    r = to_receipt(_data(
        [_item(name="VISA ****1234"), _item(name="ACCT 4111 1111 1111 1111")],
        store="Shop 4111 1111 1111 1111",
    ))
    assert "1234" not in r.items[0].name
    assert "4111" not in r.items[1].name
    assert "4111" not in (r.store or "")


def test_short_numbers_are_not_scrubbed():
    # Only 12-19 digit runs are PAN-like; a legit 4-digit token in a name must survive.
    r = to_receipt(_data([_item(name="Room 2024 Candle")]))
    assert "2024" in r.items[0].name


# --- Notion payload safety ---
def test_select_strips_commas():
    assert notion_io._select("Trader Joe's, Inc")["select"]["name"] == "Trader Joe's Inc"


def test_baseline_price_query_is_oldest_first_and_on_or_before(monkeypatch):
    captured = {}

    def fake_post(path, payload, client=None):
        captured["payload"] = payload
        return {"results": []}

    monkeypatch.setattr(notion_io, "_post", fake_post)
    notion_io.find_baseline_price("oat milk", "2026-06-04")
    assert "on_or_before" in str(captured["payload"]["filter"]["and"])
    # ascending sort = oldest price first = the baseline for the "since March" story
    assert captured["payload"]["sorts"][0]["direction"] == "ascending"


def test_baseline_price_returns_none_on_missing_select_option(monkeypatch):
    # A brand-new item's Norm Name is not yet a select option, so Notion 400s the filter.
    # That must be treated as "no prior baseline", never crash the worker.
    req = httpx.Request("POST", "https://api.notion.com/v1/x")
    resp = httpx.Response(400, request=req, json={"message": "option not found"})

    def boom(path, payload, client=None):
        raise httpx.HTTPStatusError("400", request=req, response=resp)

    monkeypatch.setattr(notion_io, "_post", boom)
    assert notion_io.find_baseline_price("never bought this before", "2026-06-04") is None


# --- Reply extras ---
def _receipt(n=2):
    items = [Item(f"I{i}", 1, 1.0, 1.0, "Groceries", 1.0, f"i{i}") for i in range(n)]
    return Receipt(
        is_receipt=True, store="Shop", date="2026-06-04", items=items, subtotal=2.0, tax=0.0, total=2.0
    )


def test_low_confidence_note_appended():
    text = reply.compose_reply(_receipt(), Insight("All good.", "biggest"), low_conf=2)
    assert "2 items were unclear" in text


def test_reply_links_to_the_receipt_url_when_given():
    text = reply.compose_reply(_receipt(), Insight("Heads up.", "price_move"),
                               receipt_url="https://www.notion.so/r9")
    assert "www.notion.so/r9" in text


def test_error_reply_has_no_em_dash():
    assert "—" not in reply.error_reply()
