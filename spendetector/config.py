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

# Food-type grouping for the per-receipt report ("what you bought", grouped). Distinct from the
# spending Category above: a supermarket run is all "Groceries" but spans many food groups.
FOOD_GROUP_ORDER = [
    "Produce",
    "Meat & Seafood",
    "Dairy & Eggs",
    "Bakery & Grains",
    "Pantry",
    "Snacks & Sweets",
    "Beverages",
    "Frozen",
    "Household",
    "Other",
]
FALLBACK_FOOD_GROUP = "Other"

# Health tiers (Nutri-Score / Kroger OptUp style): green = whole/nutritious, yellow = neutral,
# red = treat/processed. The model tags each item; the report turns it into a health score.
HEALTH_TIERS = ["green", "yellow", "red"]
FALLBACK_HEALTH_TIER = "yellow"

# Full GPT-4o (NOT mini: mini's image-token quirk erases the cost savings). Overridable
# via env, but the default is a full, vision-capable, structured-output snapshot.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-2024-08-06")

# Insight thresholds.
PRICE_MOVE_THRESHOLD = 0.10  # a repeat item moving >= 10% triggers the price-creep insight
# Category-spike (insight ladder rung 2) is deferred past the Jun 12 demo: the demo's beats only
# use price_move and cold_start, so this constant is reserved, not yet wired.
CATEGORY_SPIKE_FACTOR = 2.0


def env(name: str) -> str:
    """Return a required env var, or raise a clear error. Never silently returns ''."""
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def env_optional(name: str, default: str = "") -> str:
    """Return an optional env var with a default."""
    return os.environ.get(name, default)
