"""Round-3 tests: crash on None total, NaN/Infinity rejection, total-failure retry safety."""

from _fakes import FakeNotion, FakeTelegram, deps, ok_receipt, photo_update

from spendetector import worker
from spendetector.extract import Item, to_receipt
from spendetector.insight import compute_insight


def test_biggest_with_none_total_does_not_crash():
    # A degraded parse can leave total=None; the biggest fallback must not format None as dollars.
    items = [Item("Mystery", 1, None, None, "Other", 1.0, "mystery")]
    ins = compute_insight(items, {"mystery": (1.0, "2026-01-01")})
    assert ins.kind == "biggest"
    assert "$" not in ins.text


def test_nan_and_infinity_rejected():
    for bad in ("NaN", "Infinity", "-Infinity"):
        r = to_receipt({"is_receipt": True, "store": "X", "date": "2026-06-01",
                        "items": [{"name": "Z", "qty": 1, "unit_price": bad, "total": bad,
                                   "category": "Other", "confidence": 1.0}],
                        "subtotal": bad, "tax": None, "total": bad})
        assert r.items[0].total is None
        assert r.items[0].unit_price is None
        assert r.total is None


def test_total_write_failure_does_not_mark_seen(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(failed_items=1), FakeTelegram()  # the 1-item receipt's only item fails
    seen: dict = {}
    worker.process_update(photo_update(uid=1), seen=seen, deps=deps(n, t, ok_receipt()))
    assert 1 not in seen  # not marked, so a Modal retry or resend can re-attempt


def test_build_receipt_report_sections_and_grouping():
    from spendetector.extract import Receipt
    from spendetector.report import build_receipt_report
    items = [
        Item("Oat Milk 64oz", 1, 5.29, 5.29, "Groceries", 1.0, "oat milk", "Dairy & Eggs", "green"),
        Item("Atlantic Salmon", 1, 14.99, 14.99, "Groceries", 1.0, "salmon", "Meat & Seafood", "green"),
        Item("Potato Chips", 1, 3.99, 3.99, "Snacks", 1.0, "potato chips", "Snacks & Sweets", "red"),
    ]
    receipt = Receipt(is_receipt=True, store="Whole Foods", date="2026-06-04", items=items,
                      subtotal=24.27, tax=0.0, total=24.27)
    rep = build_receipt_report(receipt, {"oat milk": (4.49, "2026-03-03")})
    joined = " | ".join(rep.insights)
    assert "Health score" in joined
    assert "oat milk" in joined                 # the price-move line
    assert "Where it went" in joined
    assert "bank will just say" in joined
    names = [g for g, _ in rep.groups]
    assert "Meat & Seafood" in names and "Dairy & Eggs" in names and "Snacks & Sweets" in names


def test_worker_appends_per_receipt_report_and_links_to_it(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    r = worker.process_update(photo_update(), seen={}, deps=deps(n, t, ok_receipt()))
    assert r["status"] == "ok"
    assert getattr(n, "reports", 0) == 1               # report appended to the receipt page
    assert any("www.notion.so/r" in m for m in t.sent)  # a reply links to THIS receipt's page


def test_suggest_recipes_parses_model_output():
    import json

    from spendetector.recipes import suggest_recipes

    payload = json.dumps({"recipes": [
        {"name": "Veggie Scramble", "minutes": 15, "uses": ["Eggs", "Spinach"], "steps": "Scramble together."},
        {"name": "Chicken Bowl", "minutes": 25, "uses": ["Chicken", "Rice"], "steps": "Cook and serve."},
    ]})

    class _Msg:
        content = payload

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kw):
            return _Resp()

    class _Client:
        chat = type("C", (), {"completions": _Completions()})()

    items = [Item("Eggs", 1, 3.0, 3.0, "Groceries", 1.0, "eggs", "Dairy & Eggs", "green")]
    recs = suggest_recipes(items, client=_Client())
    assert len(recs) == 2
    assert recs[0].name == "Veggie Scramble" and recs[0].minutes == 15
    assert "Eggs" in recs[0].uses
