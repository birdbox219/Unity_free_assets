# Unity Publisher Sale — Discord Announcement Bot

Automated Discord notification system that monitors the [Unity Asset Store Publisher of the Week](https://assetstore.unity.com/publisher-sale) page and posts rich embed announcements whenever a new weekly promotion appears.

Runs entirely on **GitHub Actions** (free tier) — no servers, no databases, no paid hosting.

---

## Features

- **Automatic detection** of new weekly promotions (free asset, coupon code, publisher, expiration)
- **Professional Discord embeds** with images, clickable links, and action buttons
- **Duplicate prevention** via JSON cache — only posts when the promotion actually changes
- **Dual-strategy scraper** — parses Next.js RSC payload for structured data, with HTML fallback
- **Zero cost** — GitHub Actions cron + Discord Webhooks = completely free
- **Lightweight** — only 2 Python dependencies (`requests`, `beautifulsoup4`)

## What Gets Announced

| Field | Source |
|---|---|
| 🎁 Free asset name + link | Promotion callout section |
| 🎟️ Coupon code | Extracted from description text |
| 🏷️ Publisher name + link | Hero / callout metadata |
| 🛒 Discounted assets (50% off) | Publisher page |
| ⏳ Expiration date | Legal disclaimer |
| 🖼️ Promotional images | Contentful CMS assets |

---

## Architecture

```
GitHub Actions (cron: every hour)
        │
        ▼
   main.py (orchestrator)
        │
        ├── Load cache.json
        ├── scraper.py ──► Fetch & parse Unity page
        ├── Compare with cache
        ├── discord_webhook.py ──► Send embed (if changed)
        └── Save updated cache.json
```

---

## Quick Start

### 1. Fork / Clone This Repository

```bash
git clone https://github.com/YOUR_USERNAME/unity-publisher-bot.git
cd unity-publisher-bot
```

### 2. Create a Discord Webhook

1. Open your Discord server settings
2. Go to **Integrations** → **Webhooks**
3. Click **New Webhook**
4. Choose the target channel
5. Copy the **Webhook URL**

### 3. Add the GitHub Secret

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `DISCORD_WEBHOOK_URL`
5. Value: Paste your Discord webhook URL
6. Click **Add secret**

### 4. Enable GitHub Actions

1. Go to the **Actions** tab in your repository
2. If prompted, click **I understand my workflows, go ahead and enable them**
3. The workflow runs automatically every hour
4. You can also click **Run workflow** to trigger it manually

That's it! The bot is now live.

---

## Local Testing

### Setup

```bash
# Create a virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Test the Scraper Only

```bash
python scraper.py
```

This will fetch the Unity page and print all extracted promotion data without sending any webhook.

### Test the Full Pipeline

```bash
# Set the webhook URL
set DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL   # Windows
# export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...           # macOS/Linux

# Run the bot
python main.py
```

### Preview the Discord Embed (Without Sending)

```bash
python discord_webhook.py
```

This prints the JSON payload that would be sent to Discord.

---

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── check.yml          # GitHub Actions cron workflow
│
├── main.py                    # Orchestrator (cache + scrape + webhook)
├── scraper.py                 # Unity page scraper (RSC + HTML fallback)
├── discord_webhook.py         # Discord embed builder + sender
├── cache.json                 # Promotion state (auto-updated)
├── requirements.txt           # Python dependencies
├── README.md                  # This file
└── .gitignore                 # Git ignore rules
```

---

## How the Scraper Works

Unity's publisher sale page is a **Next.js App Router** application that uses **React Server Components (RSC)** streamed via inline `<script>` tags. The page content comes from **Contentful CMS**.

### Primary Strategy: RSC Payload Parsing

The scraper extracts structured data from the RSC streaming payload:

- **Hero section** → publisher name, banner image
- **CalloutSlim section** → free asset name, coupon code, CTA link, promo image, expiration date
- **DynamicProductListing section** → publisher ID, description, link to publisher page

### Fallback Strategy: HTML Parsing

If Unity changes their frontend framework, the scraper falls back to:

- Regex extraction of coupon codes (ALL-CAPS patterns)
- Regex extraction of dates from text
- Link scanning for `/packages/` URLs
- Meta tag reading

---

## Configuration

| Setting | Location | Default |
|---|---|---|
| Webhook URL | GitHub Secret `DISCORD_WEBHOOK_URL` | Required |
| Check frequency | `.github/workflows/check.yml` cron | Every hour |
| Embed color | `discord_webhook.py` `EMBED_COLOR` | Green (`0x00C853`) |
| Max deals shown | `discord_webhook.py` `MAX_DEAL_ITEMS` | 10 |
| Request timeout | `scraper.py` `REQUEST_TIMEOUT` | 30 seconds |

---

## Troubleshooting

### Bot isn't posting

1. Check the **Actions** tab for workflow run logs
2. Verify the `DISCORD_WEBHOOK_URL` secret is set correctly
3. Run `python scraper.py` locally to test if scraping works
4. Check if the promotion has actually changed since the last check

### "No valid promotion data" error

Unity may have changed their page structure. Try:

1. Run `python scraper.py` locally with `DEBUG` logging
2. Check if the page loads at https://assetstore.unity.com/publisher-sale
3. Open an issue if the page structure has fundamentally changed

### Duplicate announcements

The cache file (`cache.json`) tracks the last posted promotion. If you see duplicates:

1. Check that the GitHub Actions workflow has `permissions: contents: write`
2. Verify the "Commit cache changes" step succeeds in the workflow logs
3. Ensure no branch protection rules block the bot's commits

### GitHub Actions free tier limits

- **Public repos**: Unlimited minutes
- **Private repos**: 2,000 minutes/month
- Hourly runs ≈ 720 runs/month × ~1 min = ~720 minutes (well within limits)

---

## License

MIT
