"""
Discord Webhook Module
======================
Builds and sends professional Discord embed announcements for
Unity Publisher Sale promotions via Discord Webhooks.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from scraper import PromotionData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Rich green colour for the embed sidebar
EMBED_COLOR = 0x00C853

# Maximum number of discounted assets to show in the embed
MAX_DEAL_ITEMS = 10

# Discord webhook URL — loaded from environment variable (GitHub Secret)
WEBHOOK_ENV_VAR = "DISCORD_WEBHOOK_URL"


# ---------------------------------------------------------------------------
# Embed Builder
# ---------------------------------------------------------------------------

def _build_embed(promo: PromotionData) -> dict:
    """
    Build a Discord embed payload from the promotion data.

    Returns a dict ready to be included in the webhook JSON body.
    """
    fields: list[dict] = []

    # 🎁 FREE Asset
    if promo.free_asset_name:
        asset_value = promo.free_asset_name
        if promo.free_asset_url:
            asset_value = f"**[{promo.free_asset_name}]({promo.free_asset_url})**"
        fields.append({
            "name": "🎁 FREE Asset",
            "value": asset_value,
            "inline": False,
        })

    # 🎟️ Coupon Code
    if promo.coupon_code:
        fields.append({
            "name": "🎟️ Coupon Code",
            "value": f"```\n{promo.coupon_code}\n```",
            "inline": True,
        })

    # 🏷️ Publisher
    if promo.publisher_name:
        pub_value = promo.publisher_name
        if promo.publisher_url:
            pub_value = f"[{promo.publisher_name}]({promo.publisher_url})"
        fields.append({
            "name": "🏷️ Publisher",
            "value": pub_value,
            "inline": True,
        })

    # 🛒 Other Deals (50% off)
    if promo.discounted_assets:
        deal_lines: list[str] = []
        for asset in promo.discounted_assets[:MAX_DEAL_ITEMS]:
            name = asset.get("name", "Unknown")
            url = asset.get("url", "")
            sale_price = asset.get("sale_price", "")
            original_price = asset.get("original_price", "")

            if url:
                line = f"• [{name}]({url})"
            else:
                line = f"• {name}"

            if sale_price and original_price:
                line += f"  ~~{original_price}~~ → **{sale_price}**"
            elif sale_price:
                line += f"  **{sale_price}**"

            deal_lines.append(line)

        remaining = len(promo.discounted_assets) - MAX_DEAL_ITEMS
        if remaining > 0:
            deal_lines.append(f"*... and {remaining} more*")

        fields.append({
            "name": "🛒 Other Deals (-50%)",
            "value": "\n".join(deal_lines),
            "inline": False,
        })

    # ⏳ Expires
    if promo.expiration_date:
        fields.append({
            "name": "⏳ Ends",
            "value": promo.expiration_date,
            "inline": True,
        })

    # 📝 How to claim
    if promo.description:
        fields.append({
            "name": "📝 How to Claim",
            "value": promo.description,
            "inline": False,
        })

    # ---- Construct the embed ----
    embed: dict = {
        "title": "🔥 Unity Publisher of the Week",
        "url": promo.page_url,
        "color": EMBED_COLOR,
        "fields": fields,
        "footer": {
            "text": "Unity Publisher Sale Monitor • github.com",
        },
    }

    # Optional description
    if promo.publisher_name:
        embed["description"] = (
            f"This week's featured publisher is **{promo.publisher_name}**! "
            f"Save 50% on their assets and grab a **free gift**."
        )

    # Thumbnail (free asset image)
    if promo.free_asset_image_url:
        embed["thumbnail"] = {"url": promo.free_asset_image_url}

    # Large image (hero banner)
    if promo.hero_image_url:
        embed["image"] = {"url": promo.hero_image_url}

    return embed


def _build_webhook_payload(promo: PromotionData) -> dict:
    """
    Build the full webhook JSON payload including the embed.

    Returns a dict suitable for ``requests.post(json=...)``.
    """
    embed = _build_embed(promo)

    payload: dict = {
        "username": "Unity Asset Store",
        "avatar_url": (
            "https://images.ctfassets.net/t8hl2pirfi15/"
            "5otX5hEJunYOfCsZpbQTHZ/d7569ef4f4691f39a5959e7d36bc5624/"
            "asset_store_logo.svg"
        ),
        "embeds": [embed],
    }

    # Add a button-like component linking to the free asset
    if promo.free_asset_url:
        payload["components"] = [
            {
                "type": 1,  # Action Row
                "components": [
                    {
                        "type": 2,      # Button
                        "style": 5,     # Link
                        "label": "🎁 Get Free Asset",
                        "url": promo.free_asset_url,
                    },
                    {
                        "type": 2,
                        "style": 5,
                        "label": "🛒 View Sale Page",
                        "url": promo.page_url,
                    },
                ],
            }
        ]

    return payload


# ---------------------------------------------------------------------------
# Webhook Sender
# ---------------------------------------------------------------------------

def send_discord_announcement(
    promo: PromotionData,
    webhook_url: Optional[str] = None,
) -> bool:
    """
    Send a Discord webhook embed for the given promotion.

    Args:
        promo:       Populated PromotionData from the scraper.
        webhook_url: Discord webhook URL.  If not provided, reads from
                     the DISCORD_WEBHOOK_URL environment variable.

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    url = webhook_url or os.environ.get(WEBHOOK_ENV_VAR, "")

    if not url:
        logger.error(
            "Discord webhook URL not configured. "
            "Set the %s environment variable or pass webhook_url.",
            WEBHOOK_ENV_VAR,
        )
        return False

    if not promo.is_valid:
        logger.warning("Promotion data is empty / invalid — skipping announcement.")
        return False

    payload = _build_webhook_payload(promo)

    logger.info("Sending Discord webhook announcement...")
    logger.debug("Payload: %s", payload)

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )

        if resp.status_code in (200, 204):
            logger.info("Discord announcement sent successfully! (status=%d)", resp.status_code)
            return True

        logger.error(
            "Discord webhook returned status %d: %s",
            resp.status_code,
            resp.text[:500],
        )
        return False

    except requests.RequestException as exc:
        logger.error("Failed to send Discord webhook: %s", exc)
        return False


# ---------------------------------------------------------------------------
# CLI entry point (for local testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    # Build a sample payload for visual inspection
    sample = PromotionData(
        publisher_name="Daniel Ilett",
        publisher_url="https://assetstore.unity.com/publishers/42768",
        free_asset_name="Toon Shaders Pro for URP",
        free_asset_url="https://assetstore.unity.com/packages/vfx/shaders/toon-shaders-pro-for-urp-305845",
        coupon_code="DANIELILETT",
        expiration_date="May 14, 2026 at 7:59am PT",
        description=(
            "Add Toon Shaders Pro for URP to your cart, then enter the "
            "coupon code DANIELILETT at checkout to get it for free. "
            "No purchase necessary.*"
        ),
        hero_image_url=(
            "https://images.ctfassets.net/t8hl2pirfi15/5dfW7MSOO6Lzul0m3Dl00t/"
            "deccb7107a95e95fb0c8c02eee67fe61/as-dec-sale-lp-1920x1080-contentful.jpg"
        ),
        free_asset_image_url=(
            "https://images.ctfassets.net/t8hl2pirfi15/49t0V3yJ1zASwXE2GuoDXT/"
            "1ab1b085ed09454cee50263e3ee176eb/e48991b3-6ff5-4cd3-aa8d-7953cc9eaa78.webp"
        ),
        discounted_assets=[
            {"name": "Sample Shader Pack", "url": "https://example.com/asset1"},
            {"name": "VFX Collection", "url": "https://example.com/asset2"},
        ],
    )

    payload = _build_webhook_payload(sample)
    print("\n" + "=" * 60)
    print("WEBHOOK PAYLOAD (preview)")
    print("=" * 60)
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    # Optionally send if a webhook URL is provided
    url = os.environ.get(WEBHOOK_ENV_VAR)
    if url:
        print("\nWebhook URL detected — sending test message...")
        send_discord_announcement(sample, url)
    else:
        print(f"\nSet {WEBHOOK_ENV_VAR} to send a test message.")
