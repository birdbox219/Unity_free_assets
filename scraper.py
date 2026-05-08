"""
Unity Publisher Sale Page Scraper
=================================
Extracts promotion data from https://assetstore.unity.com/publisher-sale

Strategy:
    1. PRIMARY — Parse the React Server Components (RSC) payload embedded in
       the page's inline <script> tags.  Unity uses Next.js App Router with
       Contentful CMS; all promotion metadata is streamed in the RSC chunks.
    2. FALLBACK — If RSC parsing fails (e.g., Unity changes their frontend),
       fall back to conventional HTML + regex extraction.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PUBLISHER_SALE_URL = "https://assetstore.unity.com/publisher-sale"
BASE_URL = "https://assetstore.unity.com"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

REQUEST_TIMEOUT = 30  # seconds

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

@dataclass
class PromotionData:
    """Structured representation of a Unity Publisher Sale promotion."""

    publisher_name: str = ""
    publisher_url: str = ""
    free_asset_name: str = ""
    free_asset_url: str = ""
    coupon_code: str = ""
    expiration_date: str = ""
    description: str = ""
    publisher_description: str = ""
    hero_image_url: str = ""
    free_asset_image_url: str = ""
    discounted_assets: list[dict] = field(default_factory=list)
    page_url: str = PUBLISHER_SALE_URL

    @property
    def is_valid(self) -> bool:
        """Return True if we extracted at least the minimum required data."""
        return bool(self.free_asset_name or self.coupon_code)

    def to_dict(self) -> dict:
        """Serialise to a plain dict for JSON storage / debugging."""
        return {
            "publisher_name": self.publisher_name,
            "publisher_url": self.publisher_url,
            "free_asset_name": self.free_asset_name,
            "free_asset_url": self.free_asset_url,
            "coupon_code": self.coupon_code,
            "expiration_date": self.expiration_date,
            "description": self.description,
            "publisher_description": self.publisher_description,
            "hero_image_url": self.hero_image_url,
            "free_asset_image_url": self.free_asset_image_url,
            "discounted_assets": self.discounted_assets,
            "page_url": self.page_url,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _absolute_url(path: str) -> str:
    """Convert a relative Unity Asset Store path to an absolute URL."""
    if path.startswith("http"):
        return path
    return f"{BASE_URL}{path}" if path.startswith("/") else f"{BASE_URL}/{path}"


def _extract_coupon_from_text(text: str) -> str:
    """
    Extract a coupon code from descriptive text.

    Unity's pattern is: "enter the coupon code XXXXX at checkout"
    Coupon codes are typically ALL-CAPS, 5–30 characters.
    """
    # Pattern 1: Explicit "coupon code XXXXX" phrasing
    match = re.search(r"coupon\s+code\s+([A-Z0-9_-]{3,30})", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    # Pattern 2: Any standalone ALL-CAPS word ≥ 5 chars (heuristic)
    # Filter out common false positives
    false_positives = {
        "HTTPS", "HTTP", "HTML", "UNITY", "ASSET", "STORE", "CHECKOUT",
        "PURCHASE", "FREE", "SALE", "CLICK", "ENTER", "NECESSARY",
    }
    caps_words = re.findall(r"\b([A-Z][A-Z0-9]{4,29})\b", text)
    for word in caps_words:
        if word not in false_positives:
            return word

    return ""


def _extract_expiration(text: str) -> str:
    """
    Extract the promotion expiration date from text.

    Expected pattern: "end May 14, 2026 at 7:59am PT."
    """
    match = re.search(
        r"(?:end|expire|valid)[s ].*?(\w+ \d{1,2},\s*\d{4}\s*(?:at\s*\d{1,2}:\d{2}\s*[ap]m\s*[A-Z]{2,4})?)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip(".")
    return ""


def _clean_html(html_text: str) -> str:
    """Strip HTML tags and decode entities from a text fragment."""
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = text.replace("&#39;", "'").replace("&amp;", "&").replace("&quot;", '"')
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# RSC Payload Parser  (Primary Strategy)
# ---------------------------------------------------------------------------

def _parse_rsc_payload(soup: BeautifulSoup) -> Optional[PromotionData]:
    """
    Extract promotion data from the RSC (React Server Components) streaming
    payload embedded in <script> tags.

    Unity's publisher-sale page uses Next.js App Router.  The server streams
    content as ``self.__next_f.push([...])`` calls containing JSON-like data
    with Contentful CMS section objects.

    Sections of interest:
        • Hero          — heading, banner image, titleInternal (has publisher name)
        • CalloutSlim   — free asset name, coupon, image, CTA link, legal/expiry
        • DynamicProductListing — publisher filter ID, description HTML
    """
    promo = PromotionData()
    rsc_text = ""

    for script in soup.find_all("script"):
        content = script.string or ""
        if "self.__next_f.push" in content:
            rsc_text += content

    if not rsc_text:
        logger.debug("No RSC payload found in page.")
        return None

    # ---- Unescape the RSC payload for easier regex matching ----
    # The payload is double-escaped JSON inside JS string literals
    readable = rsc_text.replace('\\"', '"').replace("\\\\", "\\")
    readable = readable.replace("\\u003c", "<").replace("\\u003e", ">")
    readable = readable.replace("\\u0026", "&")

    # ================================================================
    # Hero Section  →  publisher name + hero image
    # ================================================================
    hero_match = re.search(
        r'"__typename"\s*:\s*"Hero".*?"titleInternal"\s*:\s*"([^"]*)"',
        readable,
        re.DOTALL,
    )
    if hero_match:
        title_internal = hero_match.group(1)
        # Pattern: "Hero - Publisher of the week - Daniel Ilett"
        parts = title_internal.split(" - ")
        if len(parts) >= 3:
            promo.publisher_name = parts[-1].strip()
        elif len(parts) == 2:
            promo.publisher_name = parts[-1].strip()

    hero_image_match = re.search(
        r'"__typename"\s*:\s*"Hero".*?"image"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"',
        readable,
        re.DOTALL,
    )
    if hero_image_match:
        promo.hero_image_url = hero_image_match.group(1)

    # ================================================================
    # CalloutSlim Section  →  free asset details
    # ================================================================
    callout_match = re.search(
        r'"__typename"\s*:\s*"CalloutSlim"(.*?)(?:"__typename"|$)',
        readable,
        re.DOTALL,
    )
    if callout_match:
        callout_text = callout_match.group(1)

        # Free asset name (heading)
        heading = re.search(r'"heading"\s*:\s*"([^"]+)"', callout_text)
        if heading:
            promo.free_asset_name = heading.group(1)

        # Subheading (e.g., "Daniel Ilett asset giveaway")
        subheading = re.search(r'"subheading"\s*:\s*"([^"]+)"', callout_text)
        if subheading:
            sub_text = subheading.group(1)
            # Can also extract publisher name from subheading
            if not promo.publisher_name:
                # "Daniel Ilett asset giveaway" → "Daniel Ilett"
                promo.publisher_name = re.sub(
                    r"\s*(asset\s+)?giveaway.*", "", sub_text, flags=re.IGNORECASE
                ).strip()

        # Description (contains coupon code in plain text)
        desc = re.search(r'"description"\s*:\s*"([^"]+)"', callout_text)
        if desc:
            promo.description = desc.group(1)
            promo.coupon_code = _extract_coupon_from_text(desc.group(1))

        # CTA link (free asset URL)
        cta_url = re.search(r'"cta"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"', callout_text)
        if cta_url:
            promo.free_asset_url = _absolute_url(cta_url.group(1))

        # Image
        img_url = re.search(r'"image"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"', callout_text)
        if img_url:
            promo.free_asset_image_url = img_url.group(1)

        # Legal disclaimer (expiration date)
        legal = re.search(r'"legalDisclaimer"\s*:\s*"([^"]+)"', callout_text)
        if legal:
            promo.expiration_date = _extract_expiration(legal.group(1))

    # ================================================================
    # DynamicProductListing Section  →  publisher info + deal summary
    # ================================================================
    #
    # NOTE: The actual product cards (individual assets with prices) are
    # loaded client-side via Coveo search API, which requires browser-side
    # authentication tokens.  We extract the metadata available in the
    # server-rendered RSC payload instead.
    #
    dpl_match = re.search(
        r'"__typename"\s*:\s*"DynamicProductListing"(.*?)(?:"__typename"|$)',
        readable,
        re.DOTALL,
    )
    if dpl_match:
        dpl_text = dpl_match.group(1)

        # Publisher page link (e.g., "/publishers/42768")
        link_href = re.search(r'"linkHref"\s*:\s*"([^"]+)"', dpl_text)
        if link_href:
            promo.publisher_url = _absolute_url(link_href.group(1))

        # Publisher description from the <h2>/<p> HTML text field
        text_field = re.search(r'"text"\s*:\s*"(.*?)"(?:,|})', dpl_text)
        if text_field:
            promo.publisher_description = _clean_html(text_field.group(1))

        # Title internal (e.g., "Shop up to 50% off Daniel Ilett")
        title_int = re.search(r'"titleInternal"\s*:\s*"([^"]+)"', dpl_text)
        if title_int:
            if not promo.publisher_name:
                name_match = re.search(r"off\s+(.+)", title_int.group(1))
                if name_match:
                    promo.publisher_name = name_match.group(1).strip()

        # Publisher filter ID — tells us which publisher's assets are on sale
        pub_filter = re.search(r'"publishersFilter"\s*:\s*"([^"]+)"', dpl_text)
        if pub_filter:
            publisher_id = pub_filter.group(1)
            # Build a direct sale browse link filtered to this publisher
            sale_browse_url = (
                f"{BASE_URL}/?publisher={publisher_id}"
                f"&on_sale=true&orderBy=1"
            )
            promo.discounted_assets = [{
                "name": f"Browse all {promo.publisher_name or 'publisher'} deals",
                "url": sale_browse_url,
                "original_price": "",
                "sale_price": "50% off",
            }]

    if promo.is_valid:
        logger.info("RSC parsing succeeded.")
        return promo

    logger.warning("RSC parsing yielded incomplete data; will try HTML fallback.")
    return None


# ---------------------------------------------------------------------------
# HTML Fallback Parser  (Secondary Strategy)
# ---------------------------------------------------------------------------

def _parse_html_fallback(soup: BeautifulSoup) -> Optional[PromotionData]:
    """
    Fallback: extract promotion data from visible HTML elements and text
    when the RSC payload cannot be parsed.
    """
    promo = PromotionData()
    page_text = soup.get_text(separator=" ", strip=True)

    # ---- Coupon code ----
    promo.coupon_code = _extract_coupon_from_text(page_text)

    # ---- Expiration date ----
    promo.expiration_date = _extract_expiration(page_text)

    # ---- Free asset link ----
    for a_tag in soup.find_all("a", href=True):
        link_text = a_tag.get_text(strip=True).lower()
        if "free" in link_text and ("gift" in link_text or "get" in link_text):
            promo.free_asset_url = _absolute_url(a_tag["href"])
            # Try to get asset name from the URL slug
            slug_match = re.search(r"/([^/]+)-(\d+)$", a_tag["href"])
            if slug_match:
                promo.free_asset_name = slug_match.group(1).replace("-", " ").title()
            break

    # ---- Publisher name ----
    # Look for "publisher of the week" related heading contexts
    for heading in soup.find_all(["h1", "h2", "h3"]):
        text = heading.get_text(strip=True)
        if "publisher" in text.lower() and "week" in text.lower():
            # The publisher name is often in a nearby element or the page title
            pass

    # Try extracting from meta title
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        # Pattern: "Publisher of the week | Unity Asset Store"
        logger.debug("Page title: %s", title_text)

    # ---- Hero / promotional images ----
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").lower()
        src = img.get("src") or img.get("data-src") or ""
        if "publisher" in alt or "sale" in alt or "week" in alt:
            promo.hero_image_url = src
            break

    # ---- Discounted assets (links to /packages/) ----
    seen: set[str] = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = a_tag.get_text(strip=True)
        if "/packages/" in href and text and len(text) > 2 and href not in seen:
            if href == promo.free_asset_url:
                continue  # Skip the free asset itself
            if any(skip in href for skip in ["/asset-store-tools", "/category/"]):
                continue
            seen.add(href)
            promo.discounted_assets.append({
                "name": text,
                "url": _absolute_url(href),
                "original_price": "",
                "sale_price": "",
            })

    if promo.is_valid:
        logger.info("HTML fallback parsing succeeded.")
        return promo

    logger.warning("HTML fallback also yielded insufficient data.")
    return promo  # Return whatever we have


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_publisher_sale() -> PromotionData:
    """
    Scrape the Unity Publisher Sale page and return structured promotion data.

    Tries the RSC payload parser first; falls back to raw HTML parsing.

    Returns:
        PromotionData with all extracted fields populated (best-effort).

    Raises:
        requests.RequestException: If the page cannot be fetched.
    """
    logger.info("Fetching Unity Publisher Sale page: %s", PUBLISHER_SALE_URL)

    response = requests.get(
        PUBLISHER_SALE_URL,
        headers=REQUEST_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    logger.info(
        "Page fetched successfully (status=%d, length=%d bytes).",
        response.status_code,
        len(response.text),
    )

    soup = BeautifulSoup(response.text, "html.parser")

    # Strategy 1: RSC payload
    promo = _parse_rsc_payload(soup)
    if promo and promo.is_valid:
        return promo

    # Strategy 2: HTML fallback
    logger.info("Falling back to HTML-based extraction.")
    promo = _parse_html_fallback(soup)
    return promo if promo else PromotionData()


# ---------------------------------------------------------------------------
# CLI entry point (for local testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    data = scrape_publisher_sale()
    print("\n" + "=" * 60)
    print("SCRAPED PROMOTION DATA")
    print("=" * 60)
    print(json.dumps(data.to_dict(), indent=2, ensure_ascii=False))
