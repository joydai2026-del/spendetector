"""GPT-4o vision extraction: receipt image bytes -> structured line items.

Card digits are never extracted (absent from the schema, forbidden in the prompt, and scrubbed
from item names as defense in depth). The deterministic part (`to_receipt`, `normalize_name`)
is split out so it can be unit tested against saved fixtures without calling the API.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import math
import re
from dataclasses import dataclass, field

from .config import (
    CATEGORIES,
    FALLBACK_CATEGORY,
    FALLBACK_FOOD_GROUP,
    FALLBACK_HEALTH_TIER,
    FOOD_GROUP_ORDER,
    HEALTH_TIERS,
    OPENAI_MODEL,
    env,
)


class ReceiptParseError(RuntimeError):
    """The model response could not be turned into a receipt (refusal, truncation, empty)."""


# --- Structured-outputs JSON schema (strict). Note: NO card/last4 property exists. ---
RECEIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["is_receipt", "store", "date", "items", "subtotal", "tax", "total"],
    "properties": {
        "is_receipt": {"type": "boolean"},
        "store": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"], "description": "purchase date as ISO YYYY-MM-DD"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name", "qty", "unit_price", "total",
                    "category", "food_group", "health_tier", "confidence",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "qty": {"type": "number"},
                    "unit_price": {"type": ["number", "null"]},
                    "total": {"type": ["number", "null"]},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "food_group": {"type": "string", "enum": FOOD_GROUP_ORDER},
                    "health_tier": {"type": "string", "enum": HEALTH_TIERS,
                                    "description": "green=whole/nutritious, yellow=neutral, red=treat/processed"},
                    "confidence": {"type": "number", "description": "0..1 legibility"},
                },
            },
        },
        "subtotal": {"type": ["number", "null"]},
        "tax": {"type": ["number", "null"]},
        "total": {"type": ["number", "null"]},
    },
}

SYSTEM_PROMPT = (
    "You read retail receipts from a photo and return strict JSON. "
    f"Classify each line item into exactly one of these categories: {', '.join(CATEGORIES)}. "
    "If unsure, use Other. "
    f"Also tag each item with a food_group (one of: {', '.join(FOOD_GROUP_ORDER)}) and a "
    "health_tier: green for whole/nutritious foods (fresh produce, lean proteins, plain dairy, "
    "eggs, whole grains, nuts), yellow for neutral or processed staples (bread, pantry, oils), "
    "red for treats (sweets, soda, chips, candy, desserts). Non-food items are Household + yellow. "
    "NEVER output any card number, account number, or last-4 digits, ever. "
    "If only a line total is printed, set unit_price = total / qty. "
    "Output the purchase date as YYYY-MM-DD. "
    "Set confidence between 0 and 1 for how clearly you could read each item. "
    "If the image is not a receipt, set is_receipt to false and return an empty items list."
)


@dataclass
class Item:
    name: str
    qty: float
    unit_price: float | None
    total: float | None
    category: str
    confidence: float
    norm_name: str = ""
    food_group: str = FALLBACK_FOOD_GROUP
    health_tier: str = FALLBACK_HEALTH_TIER


@dataclass
class Receipt:
    is_receipt: bool
    store: str | None
    date: str | None
    items: list[Item] = field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None


# --- Item-name normalization (pure; collapses case, size tokens, punctuation) ---
_SIZE_TOKEN = re.compile(r"\b\d+(?:\.\d+)?\s?(?:oz|ct|pk|lb|lbs|g|kg|ml|l|pack|x)\b", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

# --- Card-digit scrub (defense in depth: the prompt forbids these, this enforces it) ---
_CARD_RUN = re.compile(r"\d(?:[ -]?\d){11,18}")  # 12-19 digit PAN-like runs
_CARD_MASK = re.compile(r"[*xX#•]{2,}\s*\d{2,4}")  # masked tails like ****1234


def _scrub_card(text: str) -> str:
    return _CARD_MASK.sub("####", _CARD_RUN.sub("####", text))


def normalize_name(raw: str, *, max_words: int = 3) -> str:
    """Normalize a raw item name to a stable matching/select key.

    "Oat Milk 64oz", "OAT MILK", and "Oat Milk" all collapse to "oat milk". This matches
    the common real case (the same store prints the same string across visits). It does NOT
    merge spelling variants like "OATMILK" (no space); that needs a dictionary and is out of
    scope for the demo, so the hero item's Norm Name must be verified on the seeded rows.
    """
    s = raw.lower()
    s = _SIZE_TOKEN.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return " ".join(s.split()[:max_words])


def _coerce_category(value) -> str:
    return value if value in CATEGORIES else FALLBACK_CATEGORY


def _coerce_enum(value, allowed: list[str], fallback: str) -> str:
    return value if value in allowed else fallback


def _to_float(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None  # reject NaN / Infinity


def _valid_iso_date(value) -> str | None:
    """Return the value if it is an ISO date string, else None (so buckets never crash)."""
    if not isinstance(value, str):
        return None
    try:
        dt.date.fromisoformat(value)
        return value
    except ValueError:
        return None


def to_receipt(data: dict) -> Receipt:
    """Build a Receipt from raw model JSON. Pure and defensive (the unit-test boundary)."""
    items: list[Item] = []
    for raw in data.get("items", []):
        if not isinstance(raw, dict):
            continue
        name = _scrub_card(str(raw.get("name") or "Item")).strip() or "Item"
        qty = _to_float(raw.get("qty")) or 1.0
        total = _to_float(raw.get("total"))
        unit_price = _to_float(raw.get("unit_price"))
        if unit_price is None and total is not None and qty:
            unit_price = round(total / qty, 2)
        confidence = _to_float(raw.get("confidence"))
        if confidence is None:  # missing or non-numeric; do NOT use `or` (a real 0.0 is meaningful)
            confidence = 1.0
        items.append(
            Item(
                name=name,
                qty=qty,
                unit_price=unit_price,
                total=total,
                category=_coerce_category(raw.get("category", FALLBACK_CATEGORY)),
                confidence=confidence,
                norm_name=normalize_name(name),
                food_group=_coerce_enum(raw.get("food_group"), FOOD_GROUP_ORDER, FALLBACK_FOOD_GROUP),
                health_tier=_coerce_enum(raw.get("health_tier"), HEALTH_TIERS, FALLBACK_HEALTH_TIER),
            )
        )
    return Receipt(
        is_receipt=bool(data.get("is_receipt", True)),
        store=_scrub_card(data["store"]) if isinstance(data.get("store"), str) else None,
        date=_valid_iso_date(data.get("date")),
        items=items,
        subtotal=_to_float(data.get("subtotal")),
        tax=_to_float(data.get("tax")),
        total=_to_float(data.get("total")),
    )


def parse_receipt(image_bytes: bytes, *, client=None) -> Receipt:
    """Call GPT-4o vision on the image bytes and return a structured Receipt."""
    if client is None:
        from openai import OpenAI

        client = OpenAI(api_key=env("OPENAI_API_KEY"))

    b64 = base64.b64encode(image_bytes).decode()
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract this receipt."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "receipt", "strict": True, "schema": RECEIPT_SCHEMA},
        },
        max_tokens=2000,
        temperature=0,
    )
    choice = resp.choices[0]
    content = getattr(choice.message, "content", None)
    if not content:  # refusal or empty
        raise ReceiptParseError("the model returned no usable content")
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:  # truncation / malformed
        raise ReceiptParseError("the model response was not valid JSON") from exc
    return to_receipt(data)
