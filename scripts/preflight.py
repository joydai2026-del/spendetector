#!/usr/bin/env python3
"""Spendetector preflight: verify every external dependency the live receipt loop needs,
BEFORE a demo. GREEN means the loop's dependencies are up. RED means fix it now, not on stage.

    python3 scripts/preflight.py        (run from the repo root)

It reads credentials from .env, which are the SAME ones the deployed Notion Worker uses
(they were set on the worker from this file). The deterministic pipeline can only work if
all three external services answer: OpenAI (reads the receipt), Notion (stores + charts it),
Telegram (delivers the photo and the reply). This catches the one that broke the June 10
demo test: OpenAI returning 429 insufficient_quota.

After every check is GREEN, send ONE real receipt photo to the bot to confirm the full loop.
"""
from __future__ import annotations
import json, os, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env() -> dict:
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        print(f"no .env found at {path}")
        sys.exit(2)
    env = {}
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


E = load_env()
GREEN, RED, RESET = "\033[32m", "\033[31m", "\033[0m"
results: list[bool] = []


def ok(msg: str) -> None:
    results.append(True)
    print(f"  {GREEN}GREEN{RESET}  {msg}")


def bad(msg: str) -> None:
    results.append(False)
    print(f"  {RED}RED{RESET}    {msg}")


def http(method: str, url: str, headers: dict, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:  # noqa: BLE001
        return None, str(e)


print("Spendetector preflight")
print("-" * 52)

# 1) OpenAI: the only paid, quota-bound dependency. This is the step that broke.
print("OpenAI (GPT-4o vision):")
model = E.get("OPENAI_MODEL") or "gpt-4o-2024-08-06"
code, body = http(
    "POST", "https://api.openai.com/v1/chat/completions",
    {"Authorization": f"Bearer {E.get('OPENAI_API_KEY', '')}", "Content-Type": "application/json"},
    {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
)
if code == 200:
    ok(f"chat 200, quota OK (model {model})")
else:
    reason = ""
    try:
        err = (json.loads(body) or {}).get("error") or {}
        reason = err.get("code") or err.get("type") or err.get("message") or ""
    except Exception:  # noqa: BLE001
        pass
    bad(f"chat {code}{' - ' + reason if reason else ''}")
    if code == 429:
        print("         FIX: add credits or raise the budget on this OpenAI project, then re-run.")

# 2) Notion: the store and the dashboard.
print("Notion (Items database):")
code, _ = http(
    "GET", f"https://api.notion.com/v1/databases/{E.get('SPENDETECTOR_ITEMS_DB_ID', 'x')}",
    {"Authorization": f"Bearer {E.get('NOTION_TOKEN', '')}", "Notion-Version": "2022-06-28"},
)
ok("items DB reachable (200)") if code == 200 else bad(f"items DB {code}")

# 3) Telegram: capture, and where receipts are actually routed right now.
print("Telegram (bot + webhook route):")
code, body = http("GET", f"https://api.telegram.org/bot{E.get('TELEGRAM_BOT_TOKEN', '')}/getWebhookInfo", {})
try:
    r = (json.loads(body) or {}).get("result", {})
    url = r.get("url", "")
    host = url.split("/")[2] if "://" in url else (url or "(none set)")
    if code == 200 and url:
        ok(f"webhook set -> {host}")
        print(f"         pending={r.get('pending_update_count', 0)}  last_error={r.get('last_error_message') or '(none)'}")
    else:
        bad(f"getWebhookInfo {code}, url={url or '(none)'}")
except Exception:  # noqa: BLE001
    bad(f"getWebhookInfo {code}: {str(body)[:80]}")

print("-" * 52)
n_ok, n_bad = results.count(True), results.count(False)
print(f"GREEN: {n_ok}   RED: {n_bad}")
if n_bad == 0:
    print("Preflight PASS. Dependencies are up. Now send ONE real receipt to the bot to confirm the full loop.")
    sys.exit(0)
print("Preflight FAIL. Fix the RED item(s) above before the demo.")
sys.exit(1)
