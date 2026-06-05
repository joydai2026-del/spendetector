"""Shared fakes for worker tests (not collected: no test_ prefix)."""

from spendetector.extract import Item, Receipt


def ok_receipt(*, is_receipt=True, items=None, store="S", date="2026-06-04", total=5.29) -> Receipt:
    if items is None:
        items = [Item("Oat Milk", 1, 5.29, 5.29, "Groceries", 1.0, "oat milk")]
    return Receipt(
        is_receipt=is_receipt, store=store, date=date, items=items, subtotal=total, tax=0.0, total=total
    )


class FakeNotion:
    def __init__(self, failed_items: int = 0):
        self.writes = 0
        self.hashes: set[str] = set()
        self.prior: dict = {}
        self._failed = failed_items

    def find_receipt_by_image_hash(self, image_hash):
        return image_hash in self.hashes

    def fetch_prior_prices(self, items, on_or_before_iso, **kw):
        return self.prior

    def write_receipt(self, receipt, update_id, *, image_hash=None, **kw):
        self.writes += 1
        if image_hash:
            self.hashes.add(image_hash)
        return {"receipt_id": "r", "url": "https://www.notion.so/r", "failed_items": self._failed}

    def append_receipt_report(self, page_id, receipt, report, image_bytes=None, dashboard_url=None, **kw):
        self.reports = getattr(self, "reports", 0) + 1


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


class RaisingExtract:
    def parse_receipt(self, image_bytes, **kw):
        raise RuntimeError("boom")


class FakeImages:
    def generate_report_card(self, receipt, report, **kw):
        return None  # no real image in unit tests


def deps(notion, telegram, receipt):
    return {
        "notion": notion,
        "telegram": telegram,
        "extract": FakeExtract(receipt),
        "images": FakeImages(),
    }


def photo_update(uid=1, chat=99):
    return {"update_id": uid, "message": {"chat": {"id": chat}, "photo": [{"file_id": "f"}]}}
