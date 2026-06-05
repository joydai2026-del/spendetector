"""Modal app: a fast-ACK Telegram webhook that spawns the worker.

    modal profile activate mengzxapp
    modal deploy spendetector/app.py

Then register the printed URL with Telegram setWebhook (see README). The webhook does NO heavy
work: it verifies the secret header, spawns the worker, and returns 200 in well under a second,
so Telegram never retry-storms.
"""

from __future__ import annotations

import modal
from fastapi import Header
from fastapi.responses import JSONResponse

from spendetector.webhook import verify_secret

image = (
    modal.Image.debian_slim()
    .pip_install("openai>=1.40", "httpx>=0.27", "fastapi>=0.110")
    .add_local_python_source("spendetector")
)
app = modal.App("spendetector", image=image)
secret = modal.Secret.from_name("spendetector-secrets")
seen = modal.Dict.from_name("spendetector-seen", create_if_missing=True)


@app.function(secrets=[secret], timeout=120, retries=2)
def process_receipt(update: dict) -> None:
    from spendetector import worker

    result = worker.process_update(update, seen=seen)
    print("process_receipt:", result)


@app.function(secrets=[secret])
@modal.fastapi_endpoint(method="POST")
def telegram_webhook(
    update: dict,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if not verify_secret(x_telegram_bot_api_secret_token):
        return JSONResponse({"ok": False}, status_code=403)
    process_receipt.spawn(update)
    return {"ok": True}
