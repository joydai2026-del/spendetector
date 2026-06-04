"""Central config: the fixed category list, the model id, and env accessors.

No secret or id is hardcoded. Everything mutable lives here or in the environment
(populated locally by .env and in the cloud by the `spendetector-secrets` Modal secret).
"""

import os

# The fixed canonical categories the model classifies each item into (locked 2026-06-04).
# A small, stable set keeps the Notion donut chart readable instead of sprawling into
# near-duplicate names ("Snacks" vs "snack" vs "Junk food").
CATEGORIES = [
    "Groceries",
    "Dining",
    "Coffee",
    "Snacks",
    "Household",
    "Health",
    "Transport",
    "Other",
]
FALLBACK_CATEGORY = "Other"

# Full GPT-4o (NOT mini: mini's image-token quirk erases the cost savings). Overridable
# via env, but the default is a full, vision-capable, structured-output snapshot.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-2024-08-06")

# Insight thresholds.
PRICE_MOVE_THRESHOLD = 0.10  # a repeat item moving >= 10% triggers the price-creep insight
CATEGORY_SPIKE_FACTOR = 2.0  # a category > 2x its trailing-4-week average flags a spike


def env(name: str) -> str:
    """Return a required env var, or raise a clear error. Never silently returns ''."""
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def env_optional(name: str, default: str = "") -> str:
    """Return an optional env var with a default."""
    return os.environ.get(name, default)
