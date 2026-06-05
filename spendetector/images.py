"""Generate a pretty image of the grocery haul via OpenAI gpt-image-1. Best-effort:
returns None on any failure so the report (and the bot) still work without it.
"""

from __future__ import annotations

import base64

from .config import env


def generate_haul_image(items, *, client=None) -> bytes | None:
    names = [it.name for it in items if it.name][:12]
    if not names:
        return None
    prompt = (
        "A bright, appetizing top-down flat-lay of a grocery haul on a clean light surface, "
        "neatly and attractively arranged: " + ", ".join(names) + ". "
        "Fresh produce and lean proteins look vibrant and prominent; any treats are smaller and to "
        "the side. Modern editorial food photography, soft natural light. No text, no labels, no logos."
    )
    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=env("OPENAI_API_KEY"))
        resp = client.images.generate(
            model="gpt-image-1", prompt=prompt, size="1024x1024", quality="low", n=1
        )
        return base64.b64decode(resp.data[0].b64_json)
    except Exception as exc:  # network, quota, content policy, etc. -> skip the image
        print(f"image gen failed: {type(exc).__name__}: {exc}")
        return None
