import pytest

from spendetector import notion_worker


class FakeNotion:
    def __init__(self, series):
        self.series = series
        self.written = None

    def find_price_series(self, norm_name):
        assert norm_name == "oat milk"
        return self.series

    def write_watchlist_summary(self, summary):
        self.written = summary
        return {"url": "https://www.notion.so/watch"}


def test_extracts_norm_name_from_direct_payload():
    assert notion_worker.norm_name_from_payload({"norm_name": "Oat Milk"}) == "oat milk"


def test_extracts_norm_name_from_notion_select_payload():
    payload = {"properties": {"Norm Name": {"select": {"name": "Oat Milk"}}}}
    assert notion_worker.norm_name_from_payload(payload) == "oat milk"


def test_builds_and_writes_watch_summary():
    fake = FakeNotion([
        {"date": "2026-03-27", "unit_price": 4.49, "item": "Oat Milk 64oz"},
        {"date": "2026-06-04", "unit_price": 5.65, "item": "Oat Milk"},
    ])
    out = notion_worker.handle_watch_item({"norm_name": "oat milk"}, notion=fake)
    assert out["ok"] is True
    assert out["summary"]["change_pct"] == 0.2584
    assert fake.written["norm_name"] == "oat milk"
    assert out["watchlist_row_url"] == "https://www.notion.so/watch"


def test_requires_two_prices():
    fake = FakeNotion([{"date": "2026-06-04", "unit_price": 5.65, "item": "Oat Milk"}])
    with pytest.raises(ValueError, match="Need at least two prices"):
        notion_worker.handle_watch_item({"norm_name": "oat milk"}, notion=fake)


def test_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("NOTION_WORKER_SECRET", raising=False)
    monkeypatch.delenv("SPENDETECTOR_ALLOW_INSECURE", raising=False)
    assert notion_worker.verify_notion_secret("anything") is False


def test_secret_accepts_configured_value(monkeypatch):
    monkeypatch.setenv("NOTION_WORKER_SECRET", "abc")
    assert notion_worker.verify_notion_secret("abc") is True
    assert notion_worker.verify_notion_secret("wrong") is False
