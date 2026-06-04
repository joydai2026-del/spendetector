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


def test_same_photo_resent_as_new_update_is_deduped_by_image_hash(monkeypatch):
    # The user re-sends the SAME photo: Telegram gives it a NEW update_id, but the bytes (and so
    # the sha256) are identical, so the durable Notion guard catches it. (Demo check I4.)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "99")
    n, t = FakeNotion(), FakeTelegram()
    d = deps(n, t, ok_receipt())
    r1 = worker.process_update(photo_update(uid=1), seen=None, deps=d)
    r2 = worker.process_update(photo_update(uid=2), seen=None, deps=d)
    assert r1["status"] == "ok"
    assert r2["status"] == "duplicate"
    assert n.writes == 1
    assert len(t.sent) == 1  # no duplicate reply either
