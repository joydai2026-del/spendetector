"""Generate the per-receipt 'report card' image via OpenAI gpt-image-1. Best-effort: returns
None on any failure so the report (and the bot) still work without it.

The locked house style (chosen by JJ 2026-06-04) is COZY PANTRY SHELVES: the haul drawn on cute
labeled shelves grouped by food type, each shelf tagged with its spend percentage, plus a small
chalkboard with the health grade and the top price alert. Warm, storybook, legible. gpt-image-1
renders text only approximately, so the exact numbers also live in the Notion fields below it.
Reuse PANTRY_PROMPT_TEMPLATE for every card so the style stays consistent (this is the convention).
"""

from __future__ import annotations

import base64

from .config import env

PANTRY_PROMPT_TEMPLATE = (
    "A cozy hand-drawn illustration of a grocery haul organized on warm wooden shelves like a "
    "tidy pantry, ONE shelf per food category, the items on each shelf drawn as cute simple icons. "
    "Each shelf has a small hand-lettered wooden sign showing the category name and its percentage. "
    "Shelves, top to bottom: {shelves}. "
    "A small chalkboard in the corner reads 'Health: {grade}'{alert_line}. "
    "A header banner at the very top reads '{store}  ·  {date}  ·  ${total}'. "
    "Warm wholesome storybook style, soft natural colors, clean legible labels, portrait "
    "orientation. No brand logos."
)


def _pantry_prompt(receipt, report) -> str:
    shelves = ", ".join(f"{g} {p:.0f}%" for g, p in (report.group_percents or [])[:6]) or "Groceries 100%"
    alert_line = f" and '{report.alert}'" if report.alert else ""
    return PANTRY_PROMPT_TEMPLATE.format(
        shelves=shelves,
        grade=report.grade,
        alert_line=alert_line,
        store=(receipt.store or "Groceries"),
        date=(receipt.date or ""),
        total=f"{receipt.total or 0:.0f}",
    )


def generate_report_card(receipt, report, *, client=None) -> bytes | None:
    if not receipt.items:
        return None
    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=env("OPENAI_API_KEY"))
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=_pantry_prompt(receipt, report),
            size="1024x1536",
            quality="medium",
            n=1,
        )
        return base64.b64decode(resp.data[0].b64_json)
    except Exception as exc:  # network, quota, content policy, etc. -> skip the image
        print(f"image gen failed: {type(exc).__name__}: {exc}")
        return None


def generate_menu_image(recipes, *, client=None) -> bytes | None:
    """A 'Tonight's Menu' illustration of the suggested dishes. Best-effort."""
    dishes = [r.name for r in recipes][:3]
    if not dishes:
        return None
    prompt = (
        f"A cozy 'Tonight's Menu' food illustration with {len(dishes)} appetizing plated dishes, "
        f"each clearly labeled with its name: {', '.join(dishes)}. Made from fresh groceries. "
        "Warm hand-drawn food-illustration style, soft colors, clean legible labels, portrait orientation."
    )
    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=env("OPENAI_API_KEY"))
        resp = client.images.generate(
            model="gpt-image-1", prompt=prompt, size="1024x1536", quality="medium", n=1
        )
        return base64.b64decode(resp.data[0].b64_json)
    except Exception as exc:
        print(f"menu image gen failed: {type(exc).__name__}: {exc}")
        return None
