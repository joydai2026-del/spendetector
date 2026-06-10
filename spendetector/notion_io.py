"""Notion I/O: write receipts + items, look up prior prices, and the idempotency guard.

Two databases. Receipts holds the photo gallery + a clean receipt object. Items is fully
denormalized (Store, Date, Category, plus pre-bucketed Week/Month select strings) so Notion's
native charts read one flat table with no rollups/formulas on any axis.
"""

from __future__ import annotations

import datetime as dt
import time

import httpx

from .config import env, env_optional
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


def find_price_series(norm_name: str, *, client: httpx.Client | None = None) -> list[dict]:
    """Return all dated unit prices for a normalized item, oldest first."""
    db = env("SPENDETECTOR_ITEMS_DB_ID")
    payload = {
        "filter": {
            "and": [
                {"property": "Norm Name", "select": {"equals": norm_name}},
                {"property": "Unit Price", "number": {"is_not_empty": True}},
            ]
        },
        "sorts": [{"property": "Date", "direction": "ascending"}],
        "page_size": 100,
    }
    rows = _post(f"/databases/{db}/query", payload, client).get("results", [])
    out = []
    for row in rows:
        props = row.get("properties", {})
        price = props.get("Unit Price", {}).get("number")
        date = (props.get("Date", {}).get("date") or {}).get("start")
        item = "".join(t.get("plain_text", "") for t in props.get("Item", {}).get("title", []))
        if price is not None and date:
            out.append({"date": date, "unit_price": price, "item": item, "url": row.get("url")})
    return out


def write_watchlist_summary(summary: dict, *, client: httpx.Client | None = None) -> dict | None:
    """Write one Watchlist row if SPENDETECTOR_WATCHLIST_DB_ID is configured."""
    db = env_optional("SPENDETECTOR_WATCHLIST_DB_ID")
    if not db:
        return None
    props = {
        "Item": {"title": [{"text": {"content": summary["label"][:2000]}}]},
        "Norm Name": _select(summary["norm_name"]),
        "Status": _select(summary.get("status", "Watching")),
        "First Seen": {"date": {"start": summary["first_date"]}},
        "Latest Seen": {"date": {"start": summary["latest_date"]}},
        "Notes": _rich_text(summary.get("notes", "")),
    }
    _set_number(props, "Baseline Price", summary.get("baseline_price"))
    _set_number(props, "Latest Price", summary.get("latest_price"))
    _set_number(props, "Change %", summary.get("change_pct"))
    return _post("/pages", {"parent": {"database_id": db}, "properties": props}, client)


def _item_props(
    it,
    *,
    date_iso: str,
    week: str,
    month: str,
    receipt_id: str,
    store: str | None,
) -> dict:
    """Build the Notion properties for one line item. Pure (no I/O) so it unit-tests.

    Food Group + Health Tier are written as plain selects so Notion's native charts can read
    them on an axis (a rollup/formula on an axis is not allowed); they power the food-group
    spending breakdown and the green/yellow/red health bar on the dashboard.
    """
    iprops: dict = {
        "Item": {"title": [{"text": {"content": it.name}}]},
        "Category": _select(it.category),
        "Food Group": _select(it.food_group),
        "Health Tier": _select(it.health_tier),
        "Date": {"date": {"start": date_iso}},
        "Week": _select(week),
        "Month": _select(month),
        "Receipt": {"relation": [{"id": receipt_id}]},
    }
    if it.norm_name:
        iprops["Norm Name"] = _select(it.norm_name)
    if store:
        iprops["Store"] = _select(store)
    _set_number(iprops, "Qty", it.qty)
    _set_number(iprops, "Unit Price", it.unit_price)
    _set_number(iprops, "Line Total", it.total)
    return iprops


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
        iprops = _item_props(
            it, date_iso=date_iso, week=week, month=month,
            receipt_id=receipt_id, store=receipt.store,
        )
        try:
            _post("/pages", {"parent": {"database_id": items_db}, "properties": iprops}, client)
        except httpx.HTTPError:
            failed += 1

    if failed:
        status = "partial" if failed < len(receipt.items) else "failed"
        _patch(f"/pages/{receipt_id}", {"properties": {"Status": _select(status)}}, client)

    return {"receipt_id": receipt_id, "url": receipt_page.get("url"), "failed_items": failed}


# --- Per-receipt report: the page body the bot links to (items + insights) ---
def _rich(content: str, url: str | None = None) -> list:
    text = {"type": "text", "text": {"content": content[:1900]}}
    if url:
        text["text"]["link"] = {"url": url}
    return [text]


def _blk(block_type: str, content: str, **props) -> dict:
    body = {"rich_text": _rich(content)}
    body.update(props)
    return {"object": "block", "type": block_type, block_type: body}


def _qty_str(qty: float) -> str:
    return str(int(qty)) if float(qty).is_integer() else f"{qty:g}"


def upload_image(image_bytes: bytes, filename: str = "haul.png", *,
                 client: httpx.Client | None = None) -> str | None:
    """Upload image bytes to Notion's file store; returns a file_upload id for an image block."""
    try:
        created = _post("/file_uploads", {"filename": filename, "content_type": "image/png"}, client)
        fid = created["id"]
        own = client is None
        c = client or httpx.Client(timeout=60.0)
        try:
            r = c.post(
                f"{NOTION_API}/file_uploads/{fid}/send",
                headers={"Authorization": f"Bearer {env('NOTION_TOKEN')}", "Notion-Version": NOTION_VERSION},
                files={"file": (filename, image_bytes, "image/png")},
            )
            r.raise_for_status()
        finally:
            if own:
                c.close()
        return fid
    except Exception as exc:  # best-effort; the report still works without the image
        print(f"notion image upload failed: {type(exc).__name__}: {exc}")
        return None


def append_receipt_report(
    page_id: str,
    receipt: Receipt,
    report,
    image_bytes: bytes | None = None,
    dashboard_url: str | None = None,
    recipes=None,
    menu_image: bytes | None = None,
    *,
    client: httpx.Client | None = None,
) -> None:
    """Append the per-receipt report to its own page: image, headline, insights (first), recipes
    you can cook from the haul, the items grouped by food type, then a link to the dashboard."""
    children: list[dict] = []

    # 1. the AI image of the haul, at the top
    if image_bytes:
        fid = upload_image(image_bytes, client=client)
        if fid:
            children.append({"object": "block", "type": "image",
                             "image": {"type": "file_upload", "file_upload": {"id": fid}}})

    # 2. headline callout
    children.append({"object": "block", "type": "callout", "callout": {
        "rich_text": _rich(report.headline),
        "icon": {"type": "emoji", "emoji": "\U0001f4a1"},
        "color": "blue_background",
    }})

    # 3. insights FIRST (the fun part)
    children.append(_blk("heading_2", "✨ Insights for this receipt"))
    for line in (report.insights or ["Nothing stood out on this one."]):
        children.append(_blk("bulleted_list_item", line))

    # 4. cook this tonight: recipes from the haul (+ a menu illustration)
    if recipes:
        children.append(_blk("heading_2", "\U0001f373 Cook this tonight"))
        if menu_image:
            mfid = upload_image(menu_image, "menu.png", client=client)
            if mfid:
                children.append({"object": "block", "type": "image",
                                 "image": {"type": "file_upload", "file_upload": {"id": mfid}}})
        for rec in recipes:
            children.append(_blk("heading_3", f"{rec.name}  ·  {rec.minutes} min"))
            if rec.uses:
                children.append(_blk("bulleted_list_item", "Uses: " + ", ".join(rec.uses)))
            if rec.steps:
                children.append(_blk("paragraph", rec.steps))

    # 5. what you bought, grouped by food type
    bought = f"\U0001f9fa What you bought ({len(receipt.items)} items, ${receipt.total or 0:.2f})"
    children.append(_blk("heading_2", bought))
    for group_name, group_items in report.groups:
        children.append(_blk("heading_3", group_name))
        for it in group_items:
            unit = f"${it.unit_price:.2f}" if it.unit_price is not None else "?"
            total = f"${it.total:.2f}" if it.total is not None else "?"
            children.append(_blk("bulleted_list_item", f"{it.name} - {_qty_str(it.qty)} x {unit} = {total}"))

    if dashboard_url:
        children.append({"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": _rich("See your overall spending dashboard", url=dashboard_url)}})

    # Notion caps appends at 100 blocks per call; trim defensively for a huge receipt.
    _request("PATCH", f"/blocks/{page_id}/children", {"children": children[:100]}, client)
