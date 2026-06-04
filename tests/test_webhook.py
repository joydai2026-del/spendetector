from spendetector.webhook import verify_secret


def test_matching_secret_passes(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "topsecret")
    assert verify_secret("topsecret") is True


def test_wrong_secret_fails(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "topsecret")
    assert verify_secret("nope") is False
    assert verify_secret(None) is False


def test_absent_secret_fails_closed_by_default(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("SPENDETECTOR_ALLOW_INSECURE", raising=False)
    assert verify_secret(None) is False
    assert verify_secret("anything") is False


def test_allow_insecure_flag_opens_for_local_dev(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("SPENDETECTOR_ALLOW_INSECURE", "1")
    assert verify_secret(None) is True
