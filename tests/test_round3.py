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
