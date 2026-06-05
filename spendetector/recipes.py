"""Suggest 2-3 quick recipes from a receipt's actual items, via GPT-4o. Best-effort: returns []
on any failure so the report (and the bot) still work without it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .config import OPENAI_MODEL, env

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recipes"],
    "properties": {
        "recipes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "minutes", "uses", "steps"],
                "properties": {
                    "name": {"type": "string"},
                    "minutes": {"type": "integer"},
                    "uses": {"type": "array", "items": {"type": "string"}},
                    "steps": {"type": "string", "description": "1 to 2 sentence method"},
                },
            },
        }
    },
}

_SYSTEM = (
    "You are a practical, friendly home cook. Given the items on a grocery receipt, suggest 2 to 3 "
    "easy recipes that use mainly those items (assume basic staples are on hand: salt, pepper, oil, "
    "water, common spices). Prefer using the fresh and perishable items first. For each recipe give a "
    "short appetizing name, total minutes, the exact receipt items it uses, and a 1 to 2 sentence method."
)


@dataclass
class Recipe:
    name: str
    minutes: int
    uses: list[str]
    steps: str


def suggest_recipes(items, *, client=None) -> list[Recipe]:
    names = [it.name for it in items if it.name][:25]
    if not names:
        return []
    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=env("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": "Receipt items: " + ", ".join(names)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "recipes", "strict": True, "schema": _SCHEMA},
            },
            max_tokens=900,
            temperature=0.4,
        )
        data = json.loads(resp.choices[0].message.content)
        out = []
        for r in data.get("recipes", [])[:3]:
            out.append(
                Recipe(
                    name=str(r.get("name") or "Recipe"),
                    minutes=int(r.get("minutes") or 20),
                    uses=[str(u) for u in (r.get("uses") or [])][:8],
                    steps=str(r.get("steps") or ""),
                )
            )
        return out
    except Exception as exc:  # network, refusal, quota -> no recipes this time
        print(f"recipe gen failed: {type(exc).__name__}: {exc}")
        return []
