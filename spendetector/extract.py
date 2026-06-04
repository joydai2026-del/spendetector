"""GPT-4o vision extraction: receipt image bytes -> structured line items.

Card digits are never extracted (absent from the schema, forbidden in the prompt).
The deterministic part (`to_receipt`, `normalize_name`) is split out so it can be unit
tested against saved fixtures without calling the API.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field

from .config import CATEGORIES, FALLBACK_CATEGORY, OPENAI_MODEL, env

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
                "required": ["name", "qty", "unit_price", "total", "category", "confidence"],
                "properties": {
                    "name": {"type": "string"},
                    "qty": {"type": "number"},
                    "unit_price": {"type": ["number", "null"]},
                    "total": {"type": "number"},
                    "category": {"type": "string", "enum": CATEGORIES},
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
    total: float
    category: str
    confidence: float
    norm_name: str = ""


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


def normalize_name(raw: str, *, max_words: int = 3) -> str:
    """Normalize a raw item name to a stable matching/select key.

    "Oat Milk 64oz", "OAT MILK", and "Oat Milk" all collapse to "oat milk". This matches
    the common real case (the same store prints the same string across visits). It does NOT
    merge spelling variants like "OATMILK" (no space); that needs a dictionary and is out of
    scope for the demo.
    """
    s = raw.lower()
    s = _SIZE_TOKEN.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return " ".join(s.split()[:max_words])


def _coerce_category(value: str) -> str:
    return value if value in CATEGORIES else FALLBACK_CATEGORY


def to_receipt(data: dict) -> Receipt:
    """Build a Receipt from raw model JSON. Pure and deterministic (unit-test boundary)."""
    items: list[Item] = []
    for raw in data.get("items", []):
        qty = raw.get("qty") or 1
        total = raw.get("total")
        unit_price = raw.get("unit_price")
        if unit_price is None and total is not None and qty:
            unit_price = round(total / qty, 2)
        items.append(
            Item(
                name=raw["name"],
                qty=qty,
                unit_price=unit_price,
                total=total,
                category=_coerce_category(raw.get("category", FALLBACK_CATEGORY)),
                confidence=raw.get("confidence", 1.0),
                norm_name=normalize_name(raw["name"]),
            )
        )
    return Receipt(
        is_receipt=data.get("is_receipt", True),
        store=data.get("store"),
        date=data.get("date"),
        items=items,
        subtotal=data.get("subtotal"),
        tax=data.get("tax"),
        total=data.get("total"),
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
        max_tokens=1500,
        temperature=0,
    )
    return to_receipt(json.loads(resp.choices[0].message.content))
