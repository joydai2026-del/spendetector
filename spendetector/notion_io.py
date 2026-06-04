"""Notion I/O: write receipts + items, look up prior prices, and the idempotency guard.

Two databases. Receipts holds the photo gallery + a clean receipt object. Items is fully
denormalized (Store, Date, Category, plus pre-bucketed Week/Month select strings) so Notion's
native charts read one flat table with no rollups/formulas on any axis.
"""

from __future__ import annotations

import datetime as dt

import httpx

from .config import env
from .extract import Item, Receipt

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
_TIMEOUT = 30.0


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
        r = c.request(method, f"{NOTION_API}{path}", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()
    finally:
        if own:
            c.close()


def _post(path: str, payload: dict, client: httpx.Client | None = None) -> dict:
    return _request("POST", path, payload, client)


def _patch(path: str, payload: dict, client: httpx.Client | None = None) -> dict:
    return _request("PATCH", path, payload, client)


def _select(name: str) -> dict:
    return {"select": {"name": name}}


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


# --- Idempotency guard (defense in depth alongside the worker's modal.Dict seen-set) ---
def find_receipt_by_update_id(update_id: int, *, client: httpx.Client | None = None) -> bool:
    db = env("SPENDETECTOR_RECEIPTS_DB_ID")
    payload = {
        "filter": {"property": "Telegram Update ID", "number": {"equals": update_id}},
        "page_size": 1,
    }
    return bool(_post(f"/databases/{db}/query", payload, client).get("results"))


# --- Prior-price lookup for the insight ---
def find_last_price(
    norm_name: str, before_date_iso: str, *, client: httpx.Client | None = None
) -> tuple[float, str] | None:
    db = env("SPENDETECTOR_ITEMS_DB_ID")
    payload = {
        "filter": {
            "and": [
                {"property": "Norm Name", "select": {"equals": norm_name}},
                {"property": "Unit Price", "number": {"is_not_empty": True}},
                {"property": "Date", "date": {"before": before_date_iso}},
            ]
        },
        "sorts": [{"property": "Date", "direction": "descending"}],
        "page_size": 1,
    }
    results = _post(f"/databases/{db}/query", payload, client).get("results", [])
    if not results:
        return None
    props = results[0]["properties"]
    return props["Unit Price"]["number"], props["Date"]["date"]["start"]


def fetch_prior_prices(
    items: list[Item], before_date_iso: str, *, client: httpx.Client | None = None
) -> dict[str, tuple[float, str]]:
    out: dict[str, tuple[float, str]] = {}
    for nn in {i.norm_name for i in items if i.norm_name}:
        found = find_last_price(nn, before_date_iso, client=client)
        if found:
            out[nn] = found
    return out


# --- The write path ---
def write_receipt(
    receipt: Receipt,
    update_id: int,
    *,
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
