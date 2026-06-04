from _fakes import FakeNotion, FakeTelegram, deps, ok_receipt, photo_update

from spendetector import worker


def test_same_update_id_writes_once_via_seen_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    seen: dict = {}
    d = deps(n, t, ok_receipt())
    r1 = worker.process_update(photo_update(uid=1), seen=seen, deps=d)
    r2 = worker.process_update(photo_update(uid=1), seen=seen, deps=d)
    assert r1["status"] == "ok"
    assert r2["status"] == "duplicate"
    assert n.writes == 1
    assert len(t.sent) == 1


def test_db_guard_catches_redelivery_without_seen_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    n.ids.add(7)  # a prior run already created this receipt
    r = worker.process_update(photo_update(uid=7), seen=None, deps=deps(n, t, ok_receipt()))
    assert r["status"] == "duplicate"
    assert n.writes == 0
