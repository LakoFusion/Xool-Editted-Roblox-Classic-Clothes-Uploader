<div align="center">

# Xool — Roblox Classic Clothes Uploader

**Automated catalog scraping, AI-driven texture enhancement, neural NSFW filtering, and bulk publishing for Roblox Classic Shirts & Pants — featuring a real-time ANSI terminal UI.**

![Version](https://img.shields.io/badge/version-1.0-00bcd4?style=for-the-badge)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](https://opensource.org/licenses/MIT)

[Features](#core-features) · [Terminal UI](#terminal-preview) · [Quick Start](#installation--quick-start) · [Architecture & Workflow](#architecture--workflow) · [FAQ](#troubleshooting--faq) · [Support](#connect--support)

</div>

---

## Terminal Preview

Real-time ANSI Console UI running on an independent background daemon thread (`console-ui`), refreshing live operational metrics without blocking concurrent network workers:

```text
Clothes Uploader Roblox  v1.0
Status     : Running
Uptime     : 00:04:12

Account    : group 12345678 | 1 cookie
Target     : y2k emo goth grunge
Mode       : gemini_cookie | enhance on

Uploaded   : 1
Remaining  : 0
Skipped    : 3
Failed     : 0
Pending    : 0
Round      : 2
Candidates : 18

Recent activity
[10:54:12] > scan classicshirts: 18 candidate(s)
[10:54:15] > downloaded one asset
[10:54:20] > enhanced asset style=y2k mode=provider
[10:54:28] > asset 189283741 moderation status: ReviewApproved
[10:54:32] > published one asset
[Ctrl+C to stop]
```

---

## Core Features

**Xool** is a closed-loop automated pipeline engineered for Roblox clothing groups: discovery, title translation, safety screening, texture enhancement, asset creation, and marketplace release — executed autonomously within a continuous loop.

- **Multi-Threaded & Asynchronous UI**: UI renders on a dedicated daemon thread `console-ui` (`src/ui`) with `threading.Lock`/`RLock`; `LogStream` captures line-buffered logs so terminal output remains smooth without blocking upload network threads.
- **Automated Session & Token Management** (`src/cookie`): Authenticates `.ROBLOSECURITY`, automatically refreshes `X-CSRF-TOKEN` on HTTP 403 CSRF responses, and applies exponential backoff honoring `Retry-After` (capped at 60s) on HTTP 429 rate limits.
- **Proxy Compatibility**: All network calls route through `requests.Session`, reading `HTTP_PROXY` / `HTTPS_PROXY` from the environment automatically; SOCKS proxies supported via `pip install "requests[socks]"`.
- **Intelligent Catalog Scraping** (`src/scrape`): Cursor-based pagination scanning up to 150 items per search, shuffling a candidate pool of 40 items per round, filtering blacklisted creator IDs and banned keywords.
- **Automated Title Translation & SEO Normalization** (`src/naming.py`): Offline VI→EN fashion dictionary (~90 phrase mappings), Unicode NFD diacritic stripping, and non-Latin character sanitization ensuring valid ASCII-only English product names.
- **Perceptual Deduplication** (`src/files`): Perceptual hashing (`imagehash`) matches candidate textures against the local repository to prevent downloading or uploading duplicate assets.
- **Neural NSFW Screening** (`src/download`): Convolutional neural network evaluation powered by TensorFlow and OpenNSFW2, discarding templates exceeding the configurable `max_nudity_value` threshold.
- **Hybrid Texture Enhancement Engine** (`src/enhance`): Seamless integration with Gemini Web Cookies (zero official API quota consumption), Gemini API with automated multi-key rotation, Replicate Stable Diffusion (LoRA / ControlNet), or a local procedural UV seam and ambient occlusion (AO) shading pipeline.
- **Robux Deposit Protection** (`src/upload`): Detects Roblox's 80 Robux creation deposit fee; if release fails temporarily after deposit, the item is queued into `src/assets/pending_sales.json` for automated periodic retry.
- **Crash & Starvation Guards**: Automatically halts execution safely after 10 consecutive zero-progress rounds or 10 consecutive exception rounds.

---

## Disclaimer & Security Warnings

> [!WARNING]
> **Roblox Terms of Service & Account Risk**
> This automation tool directly interfaces with undocumented and internal Roblox APIs. Automated asset uploads may violate Roblox Community Guidelines or Terms of Service and could result in account warnings, temporary moderation bans, or permanent group termination. **The author accepts no liability for account penalties, loss of Robux, or group enforcement actions.** Running this software on dedicated, disposable bot accounts is strongly advised.

> [!CAUTION]
> **Credential Security & Token Hygiene**
> Your `.ROBLOSECURITY` cookie, `gemini_cookie`, and third-party API keys provide unrestricted access to your respective accounts. Never share your `config.json` or `ai_settings.json` files, and never commit active credentials to public repositories.

Example `.gitignore` snippet to protect sensitive configurations and runtime caches:

```gitignore
config.json
ai_settings.json
.env
proxies.txt
*.cookie
src/assets/temp/
src/assets/pending_sales.json
__pycache__/
*.py[cod]
.venv/
venv/
```

---

## Installation & Quick Start

**Prerequisites:** Windows 10/11, Linux, or macOS; **Python 3.10 / 3.11 (64-bit)**. Node.js / npm is not required.

```bash
# 1) Clone repository and create a virtual environment
python -m venv venv
.\venv\Scripts\activate        # Windows
source venv/bin/activate       # Linux/macOS

# 2) Install dependencies
pip install -r requirements.txt

# 3) Run the uploader
python main.py
```

### Configuration: `config.json` (Required)

```json
{
    "groups": {
        "YOUR_GROUP_ID": {
            "uploader_cookies": ["_|WARNING:-DO-NOT-SHARE-THIS...|_YOUR_COOKIE"]
        }
    },
    "upload_amount": 5,
    "assets_price": 5,
    "searching_tags": "y2k emo goth grunge",
    "require_one_tag_in_name": true,
    "sleep_each_upload": 5,
    "max_nudity_value": 0.3,
    "delete_all_images_on_restart": false,
    "blacklisted_words": ["nike", "adidas", "gucci", "supreme", "hot", "bikini"],
    "description": "★ High quality Y2K aesthetic fit crafted for the streets.\n\ntags: y2k, cyber, goth, grunge, streetwear"
}
```

| Key | Description |
| --- | --- |
| `groups` | Target Group ID mapped to an array of uploader `.ROBLOSECURITY` cookies |
| `upload_amount` | Target number of clothing items to publish during this run |
| `assets_price` | Marketplace sale price in Robux (minimum 5 Robux) |
| `searching_tags` | Keywords used to query and scrape the Roblox catalog |
| `sleep_each_upload` | Cooldown period between consecutive upload attempts (seconds) |
| `max_nudity_value` | Maximum acceptable NSFW classification score (recommended 0.25–0.35) |
| `require_one_tag_in_name` | Requires at least one search tag to appear in the candidate item name |
| `delete_all_images_on_restart` | Clears all downloaded template images in `src/assets/` on startup |

### AI Configuration: `ai_settings.json` (Optional)

```json
{
    "enhance_clothes": false,
    "enhance_provider": "gemini_cookie",
    "gemini_cookie": "YOUR_GEMINI_BROWSER_COOKIE"
}
```

Supported `enhance_provider` values:
- `local` — Fast offline procedural enhancement (AO shading + UV seams). Default fallback.
- `gemini_cookie` — High-quality texture redesign using Gemini Web cookies (no API quota needed).
- `gemini` — Official Google Gemini API with multi-key rotation (`gemini_api_keys`).
- `replicate_sd` — Stable Diffusion image-to-image or ControlNet via Replicate API.
- `openai` — DALL-E / OpenAI image edit API.
- `photoroom` — PhotoRoom API for background cleaning and beautification.

---

## Architecture & Workflow

```text
xool-main/
├── main.py                 # Pipeline orchestrator: pick → process → upload → release
├── config.json             # Core configuration (groups, cookies, tags, filters, pricing)
├── ai_settings.json        # Enhancement settings (Gemini, Replicate, local engine)
├── requirements.txt        # requests, Pillow, tensorflow, opennsfw2, imagehash...
├── LICENSE                 # MIT License
└── src/
    ├── cookie/             # .ROBLOSECURITY parser, CSRF refresher, 429 rate limiter
    ├── download/           # Catalog asset downloader + neural NSFW filtering
    ├── enhance/            # Gemini Web/API, Replicate SD, UV seam alignment, AO shading
    ├── files/              # ImageHash deduplication and file lifecycle management
    ├── naming.py           # VI→EN catalog translator and ASCII/SEO sanitizer
    ├── scrape/             # Catalog cursor pagination and blacklist filter
    ├── ui/                 # Multi-threaded ANSI Console UI
    ├── upload/             # Asset creation, moderation polling, publishing, pending queue
    └── assets/
        ├── overlays/       # Pre-baked fashion overlays (folds, shines, aesthetics)
        ├── pants/          # Local pants texture repository
        ├── shading/        # Procedural AO templates (shirt & pants)
        ├── shirts/         # Local shirts texture repository
        ├── template/       # Official 585x559 Roblox clothing UV template
        └── pending_sales.json  # Persistent queue for assets awaiting release retry
```

**End-to-End Execution Flow:**

```text
[INPUT]   Cookie + Group ID + searching_tags + assets_price (config.json)
   ↓
[PROCESS] Scrape catalog (150 items) → translate title to English → blacklist filter
          → perceptual hash deduplication → NSFW neural check → texture enhance (AI/local)
   ↓
[OUTPUT]  Upload asset (80 R$ fee) → poll moderation status → publish to Group store
          → success: metrics updated on ANSI terminal UI
          → transient error: saved to pending_sales.json for automated retry
```

---

## Troubleshooting & FAQ

**1. `ModuleNotFoundError` / `ImportError: DLL load failed`**
Ensure dependencies are installed via `pip install -r requirements.txt`. On Windows, TensorFlow requires the **Visual C++ Redistributable (x64)** installed from Microsoft. Ensure you are executing with 64-bit Python 3.10 or 3.11.

**2. `InvalidURL: Missing scheme` or `ProxyError`**
Ensure your proxy configuration includes the protocol scheme:
```powershell
$env:HTTP_PROXY="http://user:pass@ip:port"
$env:HTTPS_PROXY="http://user:pass@ip:port"
# SOCKS5: pip install "requests[socks]" then use socks5://user:pass@ip:port
```

**3. `cookie is invalid (HTTP 401/403)`**
The `.ROBLOSECURITY` cookie has expired or been invalidated by a logout/IP change. Obtain a fresh cookie from an incognito session via Developer Tools (F12 → Application → Cookies → `.ROBLOSECURITY`) and update `config.json`. If this is only a CSRF mismatch, the tool refreshes the token automatically.

**4. `[cookie] rate limited; retrying in XXs` (HTTP 429)**
Roblox API has rate limited your IP. The tool honors the `Retry-After` header automatically (capped at 60s). To reduce frequency, increase `sleep_each_upload` to 10–15 seconds or route requests through clean residential proxies.

> [!NOTE]
> `80 Robux is needed`: Roblox requires an 80 Robux deposit per Classic Clothing creation. Ensure the uploader account or group fund possesses sufficient Robux before initiating uploads.

---

## Connect & Support

- **Discord**: [https://discord.gg/rxw8Hwk3qA](https://discord.gg/rxw8Hwk3qA)
- **TikTok**: [@lakofusion](https://www.tiktok.com/@lakofusion)
- **YouTube**: [@lakofusion2010](https://www.youtube.com/@lakofusion2010)

---

## License

MIT License

```text
Copyright (c) 2026 Lako Fusion

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
