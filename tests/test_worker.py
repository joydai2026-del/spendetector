from _fakes import (
    FakeNotion,
    FakeTelegram,
    RaisingExtract,
    deps,
    ok_receipt,
    photo_update,
)

from spendetector import worker


def test_ok_path_writes_once_and_replies(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    r = worker.process_update(photo_update(), seen={}, deps=deps(n, t, ok_receipt()))
    assert r["status"] == "ok"
    assert n.writes == 1
    assert len(t.sent) == 2  # a quick ack, then the reply


def test_owner_gate_rejects_other_chats(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    r = worker.process_update(photo_update(chat=1234), seen={}, deps=deps(n, t, ok_receipt()))
    assert r["status"] == "rejected"
    assert n.writes == 0 and t.sent == []


def test_fail_closed_when_no_owner_configured(monkeypatch):
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_ID", raising=False)
    monkeypatch.delenv("SPENDETECTOR_ALLOW_INSECURE", raising=False)
    n, t = FakeNotion(), FakeTelegram()
    r = worker.process_update(photo_update(), seen={}, deps=deps(n, t, ok_receipt()))
    assert r["status"] == "rejected"
    assert n.writes == 0


def test_non_receipt_replies_without_writing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    receipt = ok_receipt(is_receipt=False, items=[])
    r = worker.process_update(photo_update(), seen={}, deps=deps(n, t, receipt))
    assert r["status"] == "not_receipt"
    assert n.writes == 0 and len(t.sent) == 1


def test_text_message_ignored(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    upd = {"update_id": 5, "message": {"chat": {"id": 99}, "text": "hello"}}
    r = worker.process_update(upd, seen={}, deps=deps(n, t, ok_receipt()))
    assert r["status"] == "ignored"
    assert n.writes == 0


def test_price_move_insight_kind_surfaces(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    n.prior = {"oat milk": (4.49, "2026-03-03")}
    r = worker.process_update(photo_update(), seen={}, deps=deps(n, t, ok_receipt()))
    assert r["insight_kind"] == "price_move"


def test_parse_failure_sends_soft_fail_not_silence(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    d = {"notion": n, "telegram": t, "extract": RaisingExtract()}
    r = worker.process_update(photo_update(), seen={}, deps=d)
    assert r["status"] == "error"
    assert len(t.sent) == 1  # the user got a soft-fail message, not dead air


def test_total_item_write_failure_reports_failure(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(failed_items=1), FakeTelegram()  # the 1-item receipt's only item fails
    r = worker.process_update(photo_update(), seen={}, deps=deps(n, t, ok_receipt()))
    assert r["status"] == "write_failed"
    assert "could not read" in t.sent[0].lower()
