from spendetector.webhook import verify_secret


def test_matching_secret_passes(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "topsecret")
    assert verify_secret("topsecret") is True


def test_wrong_secret_fails(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "topsecret")
    assert verify_secret("nope") is False
    assert verify_secret(None) is False


def test_absent_secret_allows_dev(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    assert verify_secret(None) is True
