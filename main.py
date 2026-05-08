"""
Unity Publisher Sale — Discord Announcement Bot
================================================
Main orchestrator that ties together the scraper, cache, and webhook modules.

Flow:
    1. Load cache.json (previous promotion state)
    2. Scrape the Unity Publisher Sale page
    3. Compare current promotion against cache
    4. If changed → send Discord webhook → update cache
    5. If unchanged → log "No changes" and exit
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scraper import scrape_publisher_sale
from discord_webhook import send_discord_announcement

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("unity-bot")

# ---------------------------------------------------------------------------
# Cache System
# ---------------------------------------------------------------------------

CACHE_FILE = Path(__file__).parent / "cache.json"

DEFAULT_CACHE = {
    "last_coupon": "",
    "last_asset": "",
    "last_publisher": "",
    "last_check": "",
}


def load_cache() -> dict:
    """Load the promotion cache from disk."""
    if not CACHE_FILE.exists():
        logger.info("No cache file found — creating default cache.")
        return dict(DEFAULT_CACHE)

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        logger.info("Cache loaded: %s", cache)
        return cache
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read cache file: %s — using defaults.", exc)
        return dict(DEFAULT_CACHE)


def save_cache(cache: dict) -> None:
    """Persist the promotion cache to disk."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        logger.info("Cache saved: %s", cache)
    except OSError as exc:
        logger.error("Failed to write cache file: %s", exc)


def has_promotion_changed(cache: dict, coupon: str, asset: str) -> bool:
    """
    Determine whether the current promotion differs from the cached one.

    A promotion is considered "changed" if either the coupon code or the
    free asset name has changed (case-insensitive comparison).
    """
    cached_coupon = cache.get("last_coupon", "").strip().upper()
    cached_asset = cache.get("last_asset", "").strip().lower()

    current_coupon = coupon.strip().upper()
    current_asset = asset.strip().lower()

    if cached_coupon != current_coupon:
        logger.info(
            "Coupon changed: '%s' → '%s'",
            cached_coupon or "(empty)",
            current_coupon or "(empty)",
        )
        return True

    if cached_asset != current_asset:
        logger.info(
            "Free asset changed: '%s' → '%s'",
            cached_asset or "(empty)",
            current_asset or "(empty)",
        )
        return True

    return False


# ---------------------------------------------------------------------------
# Main Logic
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Run the promotion check pipeline.

    Returns:
        0 on success, 1 on failure.
    """
    logger.info("=" * 60)
    logger.info("Unity Publisher Sale — Promotion Check")
    logger.info("=" * 60)

    # ---- Step 1: Load cache ----
    cache = load_cache()

    # ---- Step 2: Scrape ----
    try:
        promo = scrape_publisher_sale()
    except Exception as exc:
        logger.error("Scraper failed: %s", exc, exc_info=True)
        return 1

    if not promo.is_valid:
        logger.warning(
            "Scraper returned no valid promotion data. "
            "The page structure may have changed."
        )
        return 1

    logger.info("Scraped promotion:")
    logger.info("  Publisher  : %s", promo.publisher_name)
    logger.info("  Free Asset : %s", promo.free_asset_name)
    logger.info("  Coupon     : %s", promo.coupon_code)
    logger.info("  Expires    : %s", promo.expiration_date)
    logger.info("  Deals      : %d assets", len(promo.discounted_assets))

    # ---- Step 3: Compare with cache ----
    if not has_promotion_changed(cache, promo.coupon_code, promo.free_asset_name):
        logger.info("No promotion change detected — skipping announcement.")
        # Still update the last-check timestamp
        cache["last_check"] = datetime.now(timezone.utc).isoformat()
        save_cache(cache)
        return 0

    # ---- Step 4: Send Discord webhook ----
    logger.info("🔔 New promotion detected! Sending Discord announcement...")

    success = send_discord_announcement(promo)

    if success:
        logger.info("✅ Announcement sent successfully.")
    else:
        logger.error("❌ Failed to send announcement.")
        # Don't update cache so we retry next run
        return 1

    # ---- Step 5: Update cache ----
    cache["last_coupon"] = promo.coupon_code
    cache["last_asset"] = promo.free_asset_name
    cache["last_publisher"] = promo.publisher_name
    cache["last_check"] = datetime.now(timezone.utc).isoformat()
    save_cache(cache)

    logger.info("Pipeline complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
