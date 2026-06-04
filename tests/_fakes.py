"""Shared fakes for worker tests (not collected: no test_ prefix)."""

from spendetector.extract import Item, Receipt


def ok_receipt(*, is_receipt=True, items=None, store="S", date="2026-06-04", total=5.29) -> Receipt:
    if items is None:
        items = [Item("Oat Milk", 1, 5.29, 5.29, "Groceries", 1.0, "oat milk")]
    return Receipt(
        is_receipt=is_receipt, store=store, date=date, items=items, subtotal=total, tax=0.0, total=total
    )


class FakeNotion:
    def __init__(self):
        self.writes = 0
        self.ids: set[int] = set()
        self.prior: dict = {}

    def find_receipt_by_update_id(self, update_id):
        return update_id in self.ids

    def fetch_prior_prices(self, items, before_date_iso, **kw):
        return self.prior

    def write_receipt(self, receipt, update_id, **kw):
        self.writes += 1
        self.ids.add(update_id)
        return {"receipt_id": "r", "url": "https://www.notion.so/r", "failed_items": 0}


class FakeTelegram:
    def __init__(self):
        self.sent: list[str] = []

    def get_file_bytes(self, file_id, **kw):
        return b"image-bytes"

    def send_message(self, chat_id, text, **kw):
        self.sent.append(text)


class FakeExtract:
    def __init__(self, receipt):
        self._receipt = receipt

    def parse_receipt(self, image_bytes, **kw):
        return self._receipt


def deps(notion, telegram, receipt):
    return {"notion": notion, "telegram": telegram, "extract": FakeExtract(receipt)}


def photo_update(uid=1, chat=99):
    return {"update_id": uid, "message": {"chat": {"id": chat}, "photo": [{"file_id": "f"}]}}
