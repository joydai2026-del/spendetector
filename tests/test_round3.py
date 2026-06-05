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


def test_compute_receipt_report_headline_and_lines():
    from spendetector.insight import compute_receipt_report
    items = [
        Item("Oat Milk 64oz", 1, 5.29, 5.29, "Groceries", 1.0, "oat milk"),
        Item("Atlantic Salmon", 1, 14.99, 14.99, "Groceries", 1.0, "salmon"),
        Item("Mystery Snack", 1, 2.00, 2.00, "Snacks", 1.0, "mystery snack"),
    ]
    rep = compute_receipt_report(items, {"oat milk": (4.49, "2026-03-03")})
    assert "oat milk" in rep.headline and "18%" in rep.headline and "March" in rep.headline
    joined = " | ".join(rep.lines)
    assert "Where it went" in joined          # per-receipt category breakdown
    assert "Biggest item" in joined and "Salmon" in joined
    assert "new to your history" in joined    # salmon + snack have no baseline


def test_worker_appends_per_receipt_report_and_links_to_it(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    r = worker.process_update(photo_update(), seen={}, deps=deps(n, t, ok_receipt()))
    assert r["status"] == "ok"
    assert getattr(n, "reports", 0) == 1       # the report was appended to the receipt page
    assert "www.notion.so/r" in t.sent[0]      # the reply links to THIS receipt's page
