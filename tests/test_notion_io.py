"""Integration test: writes a real row to a real Notion DB. Deselected by default.

Run only with real credentials:
    SPENDETECTOR_RECEIPTS_DB_ID=... SPENDETECTOR_ITEMS_DB_ID=... NOTION_TOKEN=... \
      python -m pytest -m integration tests/test_notion_io.py
"""

import datetime as dt
import os

import pytest

from spendetector import notion_io
from spendetector.extract import Item, Receipt

pytestmark = pytest.mark.integration

_PLACEHOLDER_IDS = {"", "idb", "rdb"}


@pytest.mark.skipif(
    os.environ.get("SPENDETECTOR_ITEMS_DB_ID", "") in _PLACEHOLDER_IDS,
    reason="needs real Notion credentials + database ids",
)
def test_write_receipt_creates_a_row():
    receipt = Receipt(
        is_receipt=True,
        store="QA Test Store",
        date=dt.date.today().isoformat(),
        items=[Item("QA Oat Milk", 1, 5.29, 5.29, "Groceries", 1.0, "qa oat milk")],
        subtotal=5.29,
        tax=0.0,
        total=5.29,
    )
    result = notion_io.write_receipt(receipt, update_id=999999)
    assert result["receipt_id"]
    assert result["failed_items"] == 0
