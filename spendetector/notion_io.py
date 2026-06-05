"""Notion I/O: write receipts + items, look up prior prices, and the idempotency guard.

Two databases. Receipts holds the photo gallery + a clean receipt object. Items is fully
denormalized (Store, Date, Category, plus pre-bucketed Week/Month select strings) so Notion's
native charts read one flat table with no rollups/formulas on any axis.
"""

from __future__ import annotations

import datetime as dt
import time

import httpx

from .config import env
from .extract import Receipt

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
_TIMEOUT = 30.0
_MAX_RETRIES = 2
_MAX_BACKOFF = 5.0


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {env('NOTION_TOKEN')}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, payload: dict, client: httpx.Client | None) -> dict:
    own = client is None
    c = client or httpx.Client(timeout=_TIMEOUT)
    try:
        for attempt in range(_MAX_RETRIES + 1):
            r = c.request(method, f"{NOTION_API}{path}", headers=_headers(), json=payload)
            if r.status_code == 429 and attempt < _MAX_RETRIES:
                time.sleep(min(float(r.headers.get("Retry-After", 1)), _MAX_BACKOFF))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()  # retries exhausted on a 429
        return r.json()
    finally:
        if own:
            c.close()


def _post(path: str, payload: dict, client: httpx.Client | None = None) -> dict:
    return _request("POST", path, payload, client)


def _patch(path: str, payload: dict, client: httpx.Client | None = None) -> dict:
    return _request("PATCH", path, payload, client)


def _select(name: str) -> dict:
    # Notion select option names cannot contain commas; sanitize, collapse spaces, cap length.
    clean = " ".join(name.replace(",", " ").split())[:100] or "Unknown"
    return {"select": {"name": clean}}


def _rich_text(value: str) -> dict:
    return {"rich_text": [{"text": {"content": value[:2000]}}]}


def _set_number(props: dict, key: str, value: float | None) -> None:
    if value is not None:
        props[key] = {"number": value}


# --- Date bucketing (pre-computed at write time; charts group on a plain select) ---
def bucket_week(date_iso: str) -> str:
    iso = dt.date.fromisoformat(date_iso).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def bucket_month(date_iso: str) -> str:
    d = dt.date.fromisoformat(date_iso)
    return f"{d.year}-{d.month:02d}"


# --- Idempotency guard (dedup the SAME photo, which Telegram redelivers with a new update_id) ---
def find_receipt_by_image_hash(image_hash: str, *, client: httpx.Client | None = None) -> bool:
    db = env("SPENDETECTOR_RECEIPTS_DB_ID")
    payload = {
        "filter": {
            "and": [
                {"property": "Image Hash", "rich_text": {"equals": image_hash}},
                # ignore a fully-failed prior attempt so a resend is allowed to retry
                {"property": "Status", "select": {"does_not_equal": "failed"}},
            ]
        },
        "page_size": 1,
    }
    return bool(_post(f"/databases/{db}/query", payload, client).get("results"))


# --- Baseline-price lookup for the insight ---
def find_baseline_price(
    norm_name: str, on_or_before_iso: str, *, client: httpx.Client | None = None
) -> tuple[float, str] | None:
    """The OLDEST recorded price for this item: the baseline for the 'up X% since March' creep
    story (which is the product's whole pitch). Compares against when you started tracking, not
    last week, so the number is the real long-run change, not weekly noise."""
    db = env("SPENDETECTOR_ITEMS_DB_ID")
    payload = {
        "filter": {
            "and": [
                {"property": "Norm Name", "select": {"equals": norm_name}},
                {"property": "Unit Price", "number": {"is_not_empty": True}},
                # on_or_before is safe: this receipt's own rows are not written yet, so they
                # cannot be returned.
                {"property": "Date", "date": {"on_or_before": on_or_before_iso}},
            ]
        },
        "sorts": [{"property": "Date", "direction": "ascending"}],  # oldest first = the baseline
        "page_size": 1,
    }
    try:
        results = _post(f"/databases/{db}/query", payload, client).get("results", [])
    except httpx.HTTPStatusError as exc:
        # Notion returns 400 when the Norm Name select option does not exist yet (a brand-new
        # item never bought before). That simply means there is no prior baseline -> None.
        if exc.response.status_code == 400:
            return None
        raise
    if not results:
        return None
    props = results[0]["properties"]
    return props["Unit Price"]["number"], props["Date"]["date"]["start"]


def fetch_prior_prices(
    items: list, on_or_before_iso: str, *, client: httpx.Client | None = None
) -> dict[str, tuple[float, str]]:
    """norm_name -> (baseline_price, baseline_date) for each item that has prior history."""
    out: dict[str, tuple[float, str]] = {}
    for nn in {i.norm_name for i in items if i.norm_name}:
        found = find_baseline_price(nn, on_or_before_iso, client=client)
        if found:
            out[nn] = found
    return out


# --- The write path ---
def write_receipt(
    receipt: Receipt,
    update_id: int,
    *,
    image_hash: str | None = None,
    photo_url: str | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """Create the Receipt page, then one Item row per line item. Returns ids + url + status."""
    receipts_db = env("SPENDETECTOR_RECEIPTS_DB_ID")
    items_db = env("SPENDETECTOR_ITEMS_DB_ID")
    date_iso = receipt.date or dt.date.today().isoformat()
    title = f"{receipt.store or 'Receipt'} - {date_iso}"

    rprops: dict = {
        "Title": {"title": [{"text": {"content": title}}]},
        "Date": {"date": {"start": date_iso}},
        "Item Count": {"number": len(receipt.items)},
        "Telegram Update ID": {"number": update_id},
        "Status": _select("complete"),
    }
    if image_hash:
        rprops["Image Hash"] = _rich_text(image_hash)
    if receipt.store:
        rprops["Store"] = _select(receipt.store)
    _set_number(rprops, "Subtotal", receipt.subtotal)
    _set_number(rprops, "Tax", receipt.tax)
    _set_number(rprops, "Total", receipt.total)
    if photo_url:
        rprops["Receipt Photo"] = {
            "files": [{"type": "external", "name": "receipt", "external": {"url": photo_url}}]
        }

    receipt_page = _post(
        "/pages", {"parent": {"database_id": receipts_db}, "properties": rprops}, client
    )
    receipt_id = receipt_page["id"]

    week, month = bucket_week(date_iso), bucket_month(date_iso)
    failed = 0
    for it in receipt.items:
        iprops: dict = {
            "Item": {"title": [{"text": {"content": it.name}}]},
            "Category": _select(it.category),
            "Date": {"date": {"start": date_iso}},
            "Week": _select(week),
            "Month": _select(month),
            "Receipt": {"relation": [{"id": receipt_id}]},
        }
        if it.norm_name:
            iprops["Norm Name"] = _select(it.norm_name)
        if receipt.store:
            iprops["Store"] = _select(receipt.store)
        _set_number(iprops, "Qty", it.qty)
        _set_number(iprops, "Unit Price", it.unit_price)
        _set_number(iprops, "Line Total", it.total)
        try:
            _post("/pages", {"parent": {"database_id": items_db}, "properties": iprops}, client)
        except httpx.HTTPError:
            failed += 1

    if failed:
        status = "partial" if failed < len(receipt.items) else "failed"
        _patch(f"/pages/{receipt_id}", {"properties": {"Status": _select(status)}}, client)

    return {"receipt_id": receipt_id, "url": receipt_page.get("url"), "failed_items": failed}
