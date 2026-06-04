import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def raw_whole_foods() -> dict:
    return json.loads((FIXTURES / "whole_foods_receipt.json").read_text())


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    """Minimal env so modules that read config import cleanly in unit tests."""
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SPENDETECTOR_RECEIPTS_DB_ID", "rdb")
    monkeypatch.setenv("SPENDETECTOR_ITEMS_DB_ID", "idb")
    monkeypatch.setenv("NOTION_DASHBOARD_URL", "https://www.notion.so/spendetector")
