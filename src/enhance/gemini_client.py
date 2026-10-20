"""
Gemini web cookie-based client for Xool clothing enhancement.

Extracted and simplified from gemini.py — only networking, upload, and
image-extraction parts.  No CLI, no interactive chat, no color output.

This module talks to the *unofficial* Gemini web endpoints using a browser
cookie.  The official Gemini API (api-key based) is handled separately in
the main enhance module.
"""

import base64
from email.utils import parsedate_to_datetime
import html
import json
import mimetypes
import os
import random
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests


TEMP_IMAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "src", "assets", "temp",
)


# ---------------------------------------------------------------------------
# Constants (trimmed from gemini.py)
# ---------------------------------------------------------------------------

UPLOAD_BASE_URL = "https://push.clients6.google.com/upload/"
STREAM_URL = (
    "https://gemini.google.com/_/BardChatUi/data/"
    "assistant.lamda.BardFrontendService/StreamGenerate"
)
REQUEST_TIMEOUT = 120
DEFAULT_MIN_STREAM_INTERVAL_SECONDS = 30
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 600
DEFAULT_MAX_ATTACHMENT_STRATEGIES = 3

BASE_HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
    "origin": "https://gemini.google.com",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://gemini.google.com/",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Chromium";v="145", "Google Chrome";v="145"',
    "sec-ch-ua-arch": '"x86"',
    "sec-ch-ua-bitness": '"64"',
    "sec-ch-ua-form-factors": '"Desktop"',
    "sec-ch-ua-full-version": '"145.0.7632.117"',
    "sec-ch-ua-full-version-list": (
        '"Not:A-Brand";v="99.0.0.0", "Chromium";v="145.0.7632.117", '
        '"Google Chrome";v="145.0.7632.117"'
    ),
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-model": '""',
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-platform-version": '"19.0.0"',
    "sec-ch-ua-wow64": "?0",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    ),
    "x-browser-channel": "stable",
    "x-browser-copyright": "Copyright 2025 Google LLC. All rights reserved.",
    "x-browser-validation": "cr7cHVG+SNcWXljUH9Du0os0RUg=",
    "x-browser-year": "1969",
}

UPLOAD_START_HEADERS = {
    **BASE_HEADERS,
    "sec-fetch-site": "same-site",
    "push-id": "feeds/mcudyrk2a4khkz",
    "x-client-pctx": "CgcSBWjK7pYx",
    "x-tenant-id": "bard-storage",
}

UPLOAD_FINALIZE_HEADERS = {
    **BASE_HEADERS,
    "content-type": "application/x-www-form-urlencoded;charset=utf-8",
    "sec-fetch-site": "same-site",
    "push-id": "feeds/mcudyrk2a4khkz",
    "x-client-pctx": "CgcSBWjK7pYx",
    "x-tenant-id": "bard-storage",
}

STREAM_HEADERS = {
    **BASE_HEADERS,
    "sec-fetch-site": "same-origin",
    "x-goog-ext-525001261-jspb": (
        '[1,null,null,null,"56fdd199312815e2",null,null,0,[4],null,null,2]'
    ),
    "x-goog-ext-525005358-jspb": (
        '["B9539BFD-588D-4BD4-81DA-29CA16A776E7",1]'
    ),
    "x-goog-ext-73010989-jspb": "[0]",
    "x-goog-ext-73010990-jspb": "[0]",
    "x-same-domain": "1",
}

STREAM_QUERY_TEMPLATE = {
    "bl": "boq_assistant-bard-web-server_20260304.08_p3",
    "f.sid": "-5184243035764461411",
    "hl": "en",
    "_reqid": "7040743",
    "rt": "c",
}

STREAM_AT_TEMPLATE = "AJvLN6NxgUaWYeZ_-vBm0_UVXNun:1772770742758"

# Base64-encoded default StreamGenerate f.req template from gemini.py
STREAM_F_REQ_TEMPLATE_B64 = (
    "W251bGwsIltbXCJyZXZlcnNlIHRoaXMgZmlsZSB0byBzb3VyY2UgY29kZVwiLDAsbnVsbCxbW1tcIi9jb250cmliX3NlcnZpY2UvdHRsXzFkL2N5YnVsemU3"
    "YWpxdGVyd2x3ZnpzeXU0bnk0b29oeTE3NzI3NzM2NTVfQWJ6d2wycmVwMEV1OERxdjFrRzNmSnpyS2lkejh1dFdNb016ejFoV09kem1OMUkxd0o4NnIzNmNO"
    "OUdNXCIsMyxudWxsLFwidGV4dC9wbGFpblwiXSxcImRpc2Fzc2VtYmxlci50eHRcIl1dLG51bGwsbnVsbCwwXSxbXCJlblwiXSxbXCJcIixcIlwiLFwiXCIs"
    "bnVsbCxudWxsLG51bGwsbnVsbCxudWxsLG51bGwsXCJcIl0sXCIhQWdHbEFWbk5BQVlrdzFKUkJNTkNGODBvcEhQdU5wQTdBRFFCRUFyWjFNOGVaMk1mbjdx"
    "UDRRdnpkdGFyYzI5cEwwNm1fQy13bzdJczdGNGdGb2hFMWUySm5mUnhmNzg5SWI0MXB3djVBZ0FBQVZGU0FBQUFCR2dCQjM0QVFXMXJZRWIzVFJLSkk4UjJH"
    "VExGWGVRcDJLMnJVTTRUS283dzRqM0xTMmNhc1hneHEzUU5Tc1lMN05DaVZ0c0hfY085RVFzeTk3Slc0NnNneUZITkEzVGltUU9SalhRMmRaMi1zb0tweFJt"
    "NlhpcXlzMTlidzk3ZGwwNy1zNnZHWkYzQ1BQRG5RMXkxdlR4c1hma196Rm5ENDJ5TTdIejNpNWpaNGhoSkRER2NGanJHbHBuMmUyLUt0bVhYcUVqdWRLTGVM"
    "OGhUZ2Z2endob3o3Yy1tbkZrUDdPWDhrRG5Xc2s2SEdORzVtUWpYTDF4RHdsdnNFZlNfQk44TXNyY1RjaUw4eTktR0UwYzF3OWlzN3JEYXJVVEV4OWYxLXhD"
    "LVRUbmktLWl0RTI3WGg1QjZiUU5PdUJOSWpTVnFjR0dmakYxbmZzeEVGekl4Nzl1a0VxeDFhczRhZmx0dlhlVXNiU3htQi12Q2dsS2tEby00UUk2NkR1Si1O"
    "cTZxME1HTDB6dENYTktfR3lqVnJIcmJGWG5tMzRLWGpaX3JKQ2NJd2tFVGRMTkRBMTM5bzhXRExtazdqa0E3U1l4Y0lvOWUyV3RaVjh6cHEtXy1GWFVqVXdh"
    "VjFKcVBGdksyMnZwYzdiU3pHWkRXdElPMjdyRG04RmZWTEtVRXhYclFCQU5HTFNZRWtxM0VQMUJqUjV2ZUdIQkFmdE5rbHoyYnJoUGc5dW91NWJjZ0FISEQt"
    "VlRva25XbDhxOGNGeTluWnhiRm9ETWhGQjZUV013X1loVXM3Z3l1aUdLX3REREZMS25Fd1FuZmhzNktDMGx1T2dyYlZjd0F0TlhOSFpVVFAyVG9GbFRYeFJJ"
    "Qlo2WU5zUTFHWGIxZ2dMOW1GM0s5TUhGQjUyd0puWWxnb0ZMbG9wci00WEllTENWeTJFNnBuS3ZGNHA1Z1pId29HZUtXdXZXbEc2WWJFOXI0WWdpOEpnSmw0"
    "RXBWbmc2d0RleVlQSGhKYUQtZHVMZS1PajZmTnFzOGtDRTNNUFNFZnpaNkpMR0N2TFFWNUgxWEZJdnFkeXJQSXpWX3pPbWxnVUZsa0xVblpKTG0wZldGN0p0"
    "b1VWTFA4dFFXMHFPUUtuZDZGbjNBZ1JYWnlmY1hGZFdtRkszWkZlUkhBdks0UVRhOVFMT1ByTU5hREN1bHpKMjQ2RnZBS1dDdzhobkZKZmdEOG9tNm9Pd1FO"
    "OEdKYl9tUjQwRlZFTWJlYVZOS01fbC04OU1uN2h5dWM3UHVib2VEdUNGUE1ObnpZX2pMNlE1c2xJczFJZzE3Zjh3MWJ5Z1JTVVpSVlN3NVhnYkJidjUtclFD"
    "bEZfSjQ4SURDU3Zxb0VpYnNBUmFMY1E5MG1NTVpMSERuaDliQy15cGFBbU9BVVE3dEE5X3dUTnFmY0pDVTdGeGNsQVBMTnVfci1RNzNzQ3l5Qzc1d01VRjNB"
    "ODJBRmhGMGI3MHJldlE0SjUtMlk0bG0xcGZxeGs3NXRmVElvVVRZdDRrb25tYkQxXzlmNURhbzJMb1dyekdPU3pSdGx5M1AxMGkyeEh5Q3VtNVJvVFpTQ1NX"
    "aXNnRnVscWZnb2N2UDNmczdMX1d2SzE4em9MX2pLWHEyOUNpNkowdGhyME8zaUlCSE04RFFidjdJbjRuVFBlRmY4aEJ5c3FEOHd5eVVjM3BXTFJXd2d3bDNj"
    "T3JLX0VYMFY5RVVLem9VT3ljR25HaXk3cWtFcTJOYUxnXCIsXCIyZTJlYTkwZjI2ODQwNWU1YTNhOTNkMzc1OGQ4NWFlMFwiLG51bGwsWzBdLDEsbnVsbCxu"
    "dWxsLDEsMCxudWxsLG51bGwsbnVsbCxudWxsLG51bGwsW1swXV0sMCxudWxsLG51bGwsbnVsbCxudWxsLG51bGwsbnVsbCxudWxsLG51bGwsMSxudWxsLG51"
    "bGwsWzRdLG51bGwsbnVsbCxudWxsLG51bGwsbnVsbCxudWxsLG51bGwsbnVsbCxudWxsLG51bGwsWzFdLG51bGwsbnVsbCxudWxsLG51bGwsbnVsbCxudWxs"
    "LG51bGwsbnVsbCxudWxsLG51bGwsbnVsbCwwLG51bGwsbnVsbCxudWxsLG51bGwsbnVsbCxcIkI5NTM5QkZELTU4OEQtNEJENC04MURBLTI5Q0ExNkE3NzZF"
    "N1wiLG51bGwsW10sbnVsbCxudWxsLG51bGwsbnVsbCxudWxsLG51bGwsMV0iXQ=="
)

# Patterns to identify image URLs in Gemini response payloads.
_IMAGE_URL_RE = re.compile(
    r"https://(?:lh\d+|[a-z0-9._-]+)\.google(?:usercontent|apis)\.com/[^\s\"'<>)}\]]+",
    re.IGNORECASE,
)
_GGPHT_URL_RE = re.compile(
    r"https://[a-z0-9._-]+\.ggpht\.com/[^\s\"'<>)}\]]+",
    re.IGNORECASE,
)
_GG_DL_SIZE_SUFFIXES = ("=s0", "=s1024", "=w1024-h1024")
MAX_GENERATED_IMAGE_URL_CANDIDATES = 16


def _positive_float(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _positive_int(value, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _looks_like_image(content):
    return (
        content.startswith(b"\x89PNG\r\n\x1a\n")
        or content.startswith(b"\xff\xd8\xff")
        or content.startswith(b"RIFF") and content[8:12] == b"WEBP"
        or content.startswith(b"GIF87a")
        or content.startswith(b"GIF89a")
    )


def _dedupe_preserve_order(items):
    seen = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _clean_image_url(url):
    text = html.unescape(str(url or "")).strip()
    text = text.strip(" \t\r\n\"'<>")
    text = text.replace("\\u003d", "=").replace("\\u0026", "&").replace("\\/", "/")
    return text.rstrip("\\")


def _add_query_param(url, name, value):
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if any(k == name for k, _ in query):
        return url
    query.append((name, value))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment)
    )


def _append_path_suffix(url, suffix):
    parts = urlsplit(url)
    if parts.path.endswith(suffix):
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path + suffix, parts.query, parts.fragment))


def _image_url_variants(url):
    base = _clean_image_url(url)
    if not base:
        return []

    variants = [base]
    parts = urlsplit(base)
    if "/gg-dl/" in parts.path:
        variants.extend(_append_path_suffix(base, suffix) for suffix in _GG_DL_SIZE_SUFFIXES)

    with_authuser = []
    for candidate in variants:
        if not urlsplit(candidate).query:
            with_authuser.append(_add_query_param(candidate, "authuser", "0"))
    variants.extend(with_authuser)
    return _dedupe_preserve_order(variants)


def _extract_image_urls_from_text(text):
    if not text:
        return []
    text = html.unescape(str(text))
    urls = []
    if "googleusercontent.com/" in text or "googleapis.com/" in text or "ggpht.com/" in text:
        for pattern in (_IMAGE_URL_RE, _GGPHT_URL_RE):
            for match in pattern.finditer(text):
                urls.append(_clean_image_url(match.group(0)))
    return _dedupe_preserve_order(urls)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class UploadedFileRef:
    """Reference to a file uploaded to Gemini storage."""
    ref_path: str
    mime_type: str
    file_name: str


class AttachmentRefRejectedError(RuntimeError):
    """Gemini rejected the uploaded attachment reference."""
    pass


class GeminiFatalResponseError(RuntimeError):
    """Gemini web returned a response that should not be retried with strategies."""
    pass


class GeminiRateLimitError(RuntimeError):
    """Gemini web rate limit is active."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class XoolGeminiClient:
    """Simplified Gemini web client for clothing image enhancement."""

    def __init__(
        self,
        cookie_header,
        timeout=REQUEST_TIMEOUT,
        min_stream_interval=None,
        rate_limit_cooldown=None,
        max_attachment_strategies=None,
        download_cookie=None,
    ):
        cookie = cookie_header.strip()
        if not cookie:
            raise RuntimeError("Gemini cookie is empty")

        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Cookie"] = cookie
        self.cookie_str = cookie

        # Dedicated cookie for downloading generated images (optional).
        # Falls back to the main Gemini cookie when not configured.
        self.download_cookie = (
            download_cookie or os.environ.get("XOOL_GEMINI_DOWNLOAD_COOKIE", "")
        )
        self.download_session = requests.Session()
        if self.download_cookie:
            print(f"[gemini] loaded dedicated download_cookie (length: {len(self.download_cookie)})")
        self._apply_download_cookies(self.download_cookie or cookie)
            
        self.min_stream_interval = _positive_float(
            min_stream_interval or os.environ.get("XOOL_GEMINI_COOKIE_MIN_DELAY"),
            DEFAULT_MIN_STREAM_INTERVAL_SECONDS,
        )
        self.rate_limit_cooldown = _positive_float(
            rate_limit_cooldown or os.environ.get("XOOL_GEMINI_COOKIE_COOLDOWN"),
            DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
        )
        self.max_attachment_strategies = _positive_int(
            max_attachment_strategies or os.environ.get("XOOL_GEMINI_COOKIE_MAX_STRATEGIES"),
            DEFAULT_MAX_ATTACHMENT_STRATEGIES,
        )
        self._last_stream_request_at = 0
        self._rate_limited_until = 0

        self.stream_query_template = dict(STREAM_QUERY_TEMPLATE)
        self.stream_headers = dict(STREAM_HEADERS)
        self.stream_at_template = STREAM_AT_TEMPLATE

        # Parse the hardcoded template
        outer_text = base64.b64decode(STREAM_F_REQ_TEMPLATE_B64).decode("utf-8")
        outer = json.loads(outer_text)
        if not isinstance(outer, list) or len(outer) < 2 or not isinstance(outer[1], str):
            raise RuntimeError("Invalid StreamGenerate template")

        inner = json.loads(outer[1])
        if not isinstance(inner, list) or not inner or not isinstance(inner[0], list):
            raise RuntimeError("Invalid StreamGenerate inner template")

        self.conversation_id = ""
        self.response_id = ""
        self.response_context_id = ""
        self.session_token = ""

        if len(inner) > 2 and isinstance(inner[2], list):
            slot = inner[2]
            if len(slot) > 0 and isinstance(slot[0], str):
                self.conversation_id = slot[0]
            if len(slot) > 1 and isinstance(slot[1], str):
                self.response_id = slot[1]
            if len(slot) > 2 and isinstance(slot[2], str):
                self.response_context_id = slot[2]
            if len(slot) > 9 and isinstance(slot[9], str):
                self.session_token = slot[9]

        default_slot = inner[0][3] if len(inner[0]) > 3 else None
        if isinstance(default_slot, list) and default_slot:
            default_slot = None
        self.default_attachment_slot = default_slot

        outer[1] = json.dumps(inner, ensure_ascii=False, separators=(",", ":"))
        self.stream_outer_template = outer

        self.attachment_kind = 3
        try:
            sample = inner[0][3]
            if isinstance(sample, list) and sample:
                first = sample[0]
                if isinstance(first, list) and first:
                    meta = first[0]
                    if isinstance(meta, list) and len(meta) >= 2 and isinstance(meta[1], int):
                        self.attachment_kind = meta[1]
        except Exception:
            pass

    # ---- helpers ----

    def _rate_limit_remaining(self):
        return max(0, int(self._rate_limited_until - time.time()))

    def _retry_after_seconds(self, response):
        retry_after = response.headers.get("Retry-After", "").strip()
        if not retry_after:
            return None
        if retry_after.isdigit():
            return int(retry_after)
        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError):
            return None
        return max(0, int(retry_at.timestamp() - time.time()))

    def _remember_rate_limit(self, response=None):
        retry_after = None
        if response is not None:
            retry_after = self._retry_after_seconds(response)
        wait_seconds = retry_after or self.rate_limit_cooldown
        self._rate_limited_until = max(
            self._rate_limited_until,
            time.time() + wait_seconds,
        )
        return int(wait_seconds)

    def _wait_for_stream_slot(self):
        remaining = self._rate_limit_remaining()
        if remaining > 0:
            raise GeminiRateLimitError(
                f"Gemini web cooldown active; wait about {remaining}s",
                retry_after=remaining,
            )

        elapsed = time.time() - self._last_stream_request_at
        wait = self.min_stream_interval - elapsed
        if self._last_stream_request_at and wait > 0:
            print(f"[gemini] waiting {int(wait) + 1}s to avoid web rate limit...")
            time.sleep(wait)
        self._last_stream_request_at = time.time()

    def _raise_for_status(self, response, action):
        if response.ok:
            return
        snippet = response.text[:500]
        if response.status_code == 429:
            wait_seconds = self._remember_rate_limit(response)
            raise GeminiRateLimitError(
                f"Failed to {action}: HTTP 429. Cooling down for about {wait_seconds}s.",
                retry_after=wait_seconds,
            )
        raise RuntimeError(
            f"Failed to {action}: HTTP {response.status_code} - {snippet}"
        )

    @staticmethod
    def _parse_cookie_header(cookie_header):
        cookie_map = {}
        for part in cookie_header.split(";"):
            token = part.strip()
            if not token or "=" not in token:
                continue
            name, value = token.split("=", 1)
            name, value = name.strip(), value.strip()
            if name:
                cookie_map[name] = value
        return cookie_map

    @staticmethod
    def _serialize_cookie_header(cookie_map):
        return "; ".join(f"{n}={v}" for n, v in cookie_map.items() if n)

    def _merge_response_cookies(self, response):
        try:
            fresh = response.cookies.get_dict()
        except Exception:
            return
        if not fresh:
            return
        current = self.session.headers.get("Cookie", "")
        if isinstance(current, bytes):
            current = current.decode("utf-8", errors="ignore")
        cmap = self._parse_cookie_header(str(current))
        changed = False
        for name, value in fresh.items():
            if cmap.get(name) != value:
                cmap[name] = value
                changed = True
        if changed:
            merged = self._serialize_cookie_header(cmap)
            if merged:
                self.session.headers["Cookie"] = merged
                self.cookie_str = merged
                try:
                    for name, value in fresh.items():
                        for domain in (".google.com", ".googleusercontent.com"):
                            self.download_session.cookies.set(name, value, domain=domain)
                except Exception:
                    pass

    def _apply_download_cookies(self, cookie_header):
        """Load cookies into the download session jar for Google image hosts."""
        cookie_map = self._parse_cookie_header(cookie_header)
        for name, value in cookie_map.items():
            for domain in (".google.com", ".googleusercontent.com"):
                self.download_session.cookies.set(name, value, domain=domain)

    # ---- runtime context refresh ----

    def _fetch_app_page(self):
        headers = {
            "accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "accept-language": BASE_HEADERS["accept-language"],
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "sec-ch-ua": BASE_HEADERS["sec-ch-ua"],
            "sec-ch-ua-mobile": BASE_HEADERS["sec-ch-ua-mobile"],
            "sec-ch-ua-platform": BASE_HEADERS["sec-ch-ua-platform"],
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "referer": "https://gemini.google.com/",
            "user-agent": BASE_HEADERS["user-agent"],
        }
        resp = self.session.get(
            "https://gemini.google.com/app",
            headers=headers,
            timeout=self.timeout,
        )
        self._raise_for_status(resp, "load Gemini app page")
        self._merge_response_cookies(resp)
        return resp.text

    @classmethod
    def _first_match(cls, text, pattern):
        m = re.search(pattern, text)
        if not m:
            return ""
        v = m.group(1)
        return v.strip() if isinstance(v, str) else ""

    @classmethod
    def _extract_at_from_html(cls, html):
        patterns = [
            r'"SNlM0e":"([^"]+)"',
            r'\bat=([A-Za-z0-9_\-]{8,}:[0-9]{8,})',
            r'\b([A-Za-z0-9_\-]{10,}:[0-9]{10,})\b',
        ]
        for p in patterns:
            v = cls._first_match(html, p)
            if v:
                return v
        return ""

    def _refresh_runtime_context(self, verbose=False):
        try:
            html = self._fetch_app_page()
        except Exception as e:
            if verbose:
                print(f"[gemini] Gemini web session refresh failed: {e}")
            return False
        changed = False
        fresh_fsid = self._first_match(html, r'"FdrFJe":"([^"]+)"')
        fresh_bl = self._first_match(html, r'"cfb2h":"([^"]+)"')
        fresh_at = self._extract_at_from_html(html)
        if fresh_fsid and self.stream_query_template.get("f.sid") != fresh_fsid:
            self.stream_query_template["f.sid"] = fresh_fsid
            changed = True
        if fresh_bl and self.stream_query_template.get("bl") != fresh_bl:
            self.stream_query_template["bl"] = fresh_bl
            changed = True
        if fresh_at and self.stream_at_template != fresh_at:
            self.stream_at_template = fresh_at
            changed = True
        if verbose:
            state = "updated tokens/cookies" if changed else "loaded app page"
            print(f"[gemini] Gemini web session refreshed ({state})")
        return changed

    # ---- session state ----

    def reset_session_state(self):
        self.conversation_id = ""
        self.response_id = ""
        self.response_context_id = ""
        self.session_token = ""

    def _update_session_state_from_payload(self, payload):
        if not isinstance(payload, list):
            return
        if len(payload) > 1 and isinstance(payload[1], list):
            pair = payload[1]
            if len(pair) > 0 and isinstance(pair[0], str):
                self.conversation_id = pair[0]
            if len(pair) > 1 and isinstance(pair[1], str):
                self.response_id = pair[1]
        if len(payload) > 25 and isinstance(payload[25], str) and payload[25]:
            self.session_token = payload[25]

    # ---- file upload ----

    def upload_file(self, file_path):
        """Upload a file to Gemini storage.  Returns an UploadedFileRef."""
        file_path = Path(file_path)
        file_data = file_path.read_bytes()
        mime_type = mimetypes.guess_type(str(file_path))[0] or "image/png"
        print(f"[gemini] uploading {file_path.name} ({len(file_data)} bytes, {mime_type})")

        start_headers = dict(UPLOAD_START_HEADERS)
        start_headers["x-goog-upload-command"] = "start"
        start_headers["x-goog-upload-protocol"] = "resumable"
        start_headers["x-goog-upload-header-content-length"] = str(len(file_data))
        start_headers["x-goog-upload-header-content-type"] = mime_type

        start_resp = self.session.post(
            UPLOAD_BASE_URL,
            headers=start_headers,
            data=f"File name: {file_path.name}".encode("utf-8"),
            timeout=self.timeout,
        )
        self._raise_for_status(start_resp, "start upload")
        self._merge_response_cookies(start_resp)

        upload_url = start_resp.headers.get("x-goog-upload-url", "").strip()
        if not upload_url:
            raise RuntimeError("Upload start did not return x-goog-upload-url")

        fin_headers = dict(UPLOAD_FINALIZE_HEADERS)
        fin_headers["x-goog-upload-command"] = "upload, finalize"
        fin_headers["x-goog-upload-offset"] = "0"

        fin_resp = self.session.post(
            upload_url,
            headers=fin_headers,
            data=file_data,
            timeout=self.timeout,
        )
        self._raise_for_status(fin_resp, "finalize upload")
        self._merge_response_cookies(fin_resp)

        ref_path = fin_resp.text.strip()
        if not ref_path.startswith("/contrib_service/"):
            sample = fin_resp.text[:300]
            raise RuntimeError(f"Unexpected upload reference: {sample}")

        print("[gemini] upload OK")
        return UploadedFileRef(
            ref_path=ref_path,
            mime_type=mime_type,
            file_name=file_path.name,
        )

    def upload_file_with_refresh(self, file_path):
        """Refresh the Gemini web session, then upload the file once."""
        self._refresh_runtime_context()
        return self.upload_file(file_path)

    # ---- request building ----

    def _build_stream_form(self, prompt, uploaded, attachment_kind, include_mime):
        outer = json.loads(json.dumps(self.stream_outer_template))
        inner = json.loads(outer[1])
        if not isinstance(inner, list) or not inner or not isinstance(inner[0], list):
            raise RuntimeError("Invalid StreamGenerate template")

        user_msg = inner[0]
        while len(user_msg) <= 3:
            user_msg.append(None)

        user_msg[0] = prompt
        if uploaded is None:
            user_msg[3] = self.default_attachment_slot
        else:
            items = uploaded if isinstance(uploaded, list) else [uploaded]
            entries = []
            for u in items:
                meta = [u.ref_path, attachment_kind, None]
                if include_mime:
                    meta.append(u.mime_type)
                entries.append([meta, u.file_name])
            user_msg[3] = entries

        while len(inner) <= 2:
            inner.append(None)
        if not isinstance(inner[2], list):
            inner[2] = []
        slot = inner[2]
        while len(slot) <= 9:
            slot.append(None)
        if self.conversation_id:
            slot[0] = self.conversation_id
        if self.response_id:
            slot[1] = self.response_id
        if self.response_context_id:
            slot[2] = self.response_context_id
        if self.session_token:
            slot[9] = self.session_token

        outer[1] = json.dumps(inner, ensure_ascii=False, separators=(",", ":"))
        return {
            "f.req": json.dumps(outer, ensure_ascii=False, separators=(",", ":")),
            "at": self.stream_at_template,
        }

    # ---- image extraction from response ----

    @staticmethod
    def _scan_for_images(node, urls, b64_images, exclude_ref=""):
        """Recursively scan a parsed JSON payload for image URLs and base64 data."""
        if isinstance(node, str):
            text = html.unescape(node)
            if text.startswith("data:image/") and ";base64," in text:
                b64_images.append(text.split(";base64,", 1)[1])
                return

            # Check Google CDN image URLs
            if "googleusercontent.com/" in text or "googleapis.com/" in text or "ggpht.com/" in text:
                for pattern in (_IMAGE_URL_RE, _GGPHT_URL_RE):
                    for match in pattern.finditer(text):
                        url = match.group(0).rstrip("\\")
                        if exclude_ref and exclude_ref in url:
                            continue
                        urls.append(url)
            # Check base64-encoded image data (PNG header iVBOR, JPEG header /9j/)
            elif len(text) > 2000:
                if text.startswith("iVBOR") or text.startswith("/9j/") or text.startswith("UklGR"):
                    b64_images.append(text)
        elif isinstance(node, list):
            for item in node:
                XoolGeminiClient._scan_for_images(item, urls, b64_images, exclude_ref)
        elif isinstance(node, dict):
            for value in node.values():
                XoolGeminiClient._scan_for_images(value, urls, b64_images, exclude_ref)

    def _parse_response_for_images(self, body_text, uploaded_ref=""):
        """Parse the full StreamGenerate response body for images.

        Returns (image_urls, base64_images) where each is a list of strings.
        """
        all_urls = []
        all_b64 = []

        for raw_line in body_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(")]}'"):
                line = line[4:]
            try:
                root = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(root, list):
                continue

            for item in root:
                if not isinstance(item, list) or not item:
                    continue
                tag = item[0]
                if tag != "wrb.fr":
                    continue
                payload_str = item[2] if len(item) > 2 else None
                if not isinstance(payload_str, str) or not payload_str:
                    continue
                try:
                    payload = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue

                self._update_session_state_from_payload(payload)
                self._scan_for_images(payload, all_urls, all_b64, uploaded_ref)

        # De-duplicate while preserving order
        seen = set()
        unique_urls = []
        for u in all_urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)

        seen_b64 = set()
        unique_b64 = []
        for item in all_b64:
            if item not in seen_b64:
                seen_b64.add(item)
                unique_b64.append(item)

        return unique_urls, unique_b64

    # ---- attachment strategy rotation (from gemini.py) ----

    def _attachment_strategies(self):
        """Yield (attachment_kind, include_mime) tuples to try."""
        candidate_kinds = [self.attachment_kind, 3, 2, 1, 4, 5, 6]
        unique = []
        for k in candidate_kinds:
            if k not in unique:
                unique.append(k)
        for kind in unique:
            yield kind, True
            yield kind, False

    # ---- core request ----

    def _request_images(self, prompt, uploaded, attachment_kind, include_mime, refresh=True):
        """Send prompt+attachment to StreamGenerate and extract images.

        Returns (image_urls, base64_images).
        Raises AttachmentRefRejectedError if attachment is rejected.
        """
        print(f"[gemini] sending StreamGenerate (kind={attachment_kind}, mime={include_mime})")
        if refresh:
            self._refresh_runtime_context()
        self._wait_for_stream_slot()

        query = dict(self.stream_query_template)
        query["_reqid"] = str(random.randint(1_000_000, 9_999_999))

        form = self._build_stream_form(prompt, uploaded, attachment_kind, include_mime)
        headers = dict(self.stream_headers)
        headers["accept-encoding"] = "identity"

        resp = self.session.post(
            STREAM_URL,
            params=query,
            headers=headers,
            data=form,
            timeout=self.timeout,
        )
        self._raise_for_status(resp, "StreamGenerate")
        self._merge_response_cookies(resp)

        body = resp.text

        # Check for attachment rejection error
        if "BardErrorInfo" in body:
            codes = sorted(set(re.findall(r"BardErrorInfo[^\]]*\[(\d+)\]", body)))
            if "1100" in codes:
                raise GeminiFatalResponseError(
                    "Gemini rejected the uploaded attachment (BardErrorInfo 1100). "
                    "Refresh gemini_cookie from the StreamGenerate request in your browser."
                )

        if '"er"' in body:
            for raw_line in body.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith(")]}'"):
                    line = line[4:]
                try:
                    root = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(root, list):
                    continue
                for it in root:
                    if isinstance(it, list) and it and it[0] == "er":
                        if len(it) > 9 and it[9] == 3:
                            raise AttachmentRefRejectedError(
                                "Attachment rejected (error code 3)"
                            )

        exclude_ref = uploaded.ref_path if uploaded else ""
        image_urls, b64_images = self._parse_response_for_images(body, exclude_ref)
        print(f"[gemini] parsed response: {len(image_urls)} image URLs, {len(b64_images)} base64 images")

        # Keep a silent debug dump when Gemini returned no images.
        if not image_urls and not b64_images:
            os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)
            dump_path = Path(TEMP_IMAGE_DIR) / "gemini_dump.txt"
            with open(dump_path, "w", encoding="utf-8") as f:
                f.write(body)

        return image_urls, b64_images

    # ---- generated image download ----

    def _generated_image_download_attempts(self):
        image_headers = {
            "accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "accept-encoding": "identity",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://gemini.google.com/",
            "sec-fetch-dest": "image",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-site": "cross-site",
            "user-agent": BASE_HEADERS["user-agent"],
        }
        navigation_headers = {
            "accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "accept-encoding": "identity",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://gemini.google.com",
            "referer": "https://gemini.google.com/",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "upgrade-insecure-requests": "1",
            "user-agent": BASE_HEADERS["user-agent"],
        }
        return [
            (self.download_session.get, image_headers, "Download Session + Image Fetch"),
            (self.download_session.get, navigation_headers, "Download Session + Browser Navigate"),
            (requests.get, image_headers, "No Cookie + Image Fetch"),
            (requests.get, navigation_headers, "No Cookie + Browser Navigate"),
        ]

    @staticmethod
    def _save_generated_image(content):
        os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="gemini_", suffix=".png", dir=TEMP_IMAGE_DIR)
        os.close(fd)
        with open(path, "wb") as f:
            f.write(content)
        return path

    @staticmethod
    def _add_download_candidates(queue, seen, urls, reason=""):
        added = 0
        for raw_url in urls:
            for candidate in _image_url_variants(raw_url):
                if candidate in seen:
                    continue
                if len(seen) >= MAX_GENERATED_IMAGE_URL_CANDIDATES:
                    return added
                seen.add(candidate)
                queue.append(candidate)
                added += 1
        return added

    @staticmethod
    def _write_failed_image_debug(attempted):
        try:
            lines = [
                "Gemini generated image download failed.",
                "No cookies are written here; only generated image URLs and HTTP results.",
                "",
            ]
            lines.extend(attempted)
            os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)
            debug_path = Path(TEMP_IMAGE_DIR) / "failed_image_url.txt"
            debug_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass

    def _download_generated_image(self, image_urls):
        queue = []
        seen = set()
        attempted = []
        printed_403_sample = False
        self._add_download_candidates(queue, seen, image_urls)

        if not queue:
            return None

        attempt_number = 0
        while queue:
            url = queue.pop(0)

            for get_method, headers, desc in self._generated_image_download_attempts():
                attempt_number += 1
                try:
                    img_resp = get_method(
                        url,
                        headers=headers,
                        timeout=60,
                        allow_redirects=True,
                    )
                except requests.RequestException as e:
                    attempted.append(f"ERROR {desc} | {url} | {e}")
                    print(f"[gemini] download attempt {attempt_number} ({desc}) error: {e}")
                    continue

                content = img_resp.content or b""
                content_type = img_resp.headers.get("content-type", "")
                attempted.append(
                    f"HTTP {img_resp.status_code} | {content_type} | {len(content)} bytes | {url}"
                )
                if img_resp.ok and len(content) > 1000 and _looks_like_image(content):
                    return self._save_generated_image(content)

                print(
                    f"[gemini] download attempt {attempt_number} ({desc}) "
                    f"HTTP {img_resp.status_code}, type={content_type}, size={len(content)} bytes"
                )

                if content and ("text/html" in content_type or img_resp.status_code in (401, 403)):
                    if img_resp.status_code == 403 and not printed_403_sample:
                        printed_403_sample = True
                        sample = img_resp.text[:150].replace("\n", " ").replace("\r", "")
                        print(f"[gemini] 403 body sample: {sample}")
                    body_urls = _extract_image_urls_from_text(img_resp.text)
                    if body_urls:
                        self._add_download_candidates(queue, seen, body_urls, "html body")

        self._write_failed_image_debug(attempted)
        return None

    # ---- public API ----

    def enhance_image(self, file_path, prompt):
        """Upload image, send enhance prompt, return path to enhanced image or None.

        This is the main entry point for Xool clothing enhancement.
        """
        file_path = Path(file_path)
        self.reset_session_state()
        print(f"[gemini] === enhance_image start: {file_path.name} ===")

        remaining = self._rate_limit_remaining()
        if remaining > 0:
            print(f"[gemini] cooldown active after HTTP 429; skipping Gemini web for {remaining}s")
            return None

        try:
            uploaded = self.upload_file_with_refresh(file_path)
        except Exception as e:
            print(f"[gemini] UPLOAD FAILED: {e}")
            return None

        image_urls = []
        b64_images = []
        strategies_tried = 0

        for kind, include_mime in self._attachment_strategies():
            if strategies_tried >= self.max_attachment_strategies:
                print(
                    f"[gemini] stopped after {strategies_tried} attachment strategies "
                    "to avoid web rate limit"
                )
                break
            strategies_tried += 1
            try:
                image_urls, b64_images = self._request_images(
                    prompt, uploaded, kind, include_mime, refresh=(strategies_tried == 1)
                )
                if image_urls or b64_images:
                    print(f"[gemini] found images on strategy #{strategies_tried} (kind={kind})")
                    break
            except AttachmentRefRejectedError:
                print(f"[gemini] attachment rejected (kind={kind}, mime={include_mime}), trying next...")
                continue
            except GeminiFatalResponseError as e:
                print(f"[gemini] fatal response: {e}")
                raise
            except GeminiRateLimitError as e:
                wait = e.retry_after or self._rate_limit_remaining() or self.rate_limit_cooldown
                print(f"[gemini] Rate limited (HTTP 429). Cooling down for about {int(wait)}s.")
                break
            except Exception as e:
                print(f"[gemini] request error (kind={kind}): {e}")
                if "HTTP 429" in str(e):
                    self._remember_rate_limit()
                    print("[gemini] Rate limited (HTTP 429). Stop checking strategies to prevent ban.")
                    break
                continue

        if not image_urls and not b64_images:
            print(f"[gemini] NO IMAGES found after {strategies_tried} strategies. Gemini did not return an image.")
            return None

        # Auto-download the generated image (download session owns its cookie jar and follows redirects).
        if image_urls:
            downloaded_path = self._download_generated_image(image_urls)
            if downloaded_path:
                return downloaded_path
                
        # Try base64-encoded images
        for i, b64_data in enumerate(b64_images):
            try:
                raw = base64.b64decode(b64_data)
                if len(raw) > 1000 and _looks_like_image(raw):
                    os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)
                    fd, path = tempfile.mkstemp(prefix="gemini_", suffix=".png", dir=TEMP_IMAGE_DIR)
                    os.close(fd)
                    with open(path, "wb") as f:
                        f.write(raw)
                    return path
                else:
                    print(f"[gemini] base64 image rejected: size={len(raw)}, image={_looks_like_image(raw)}")
            except Exception as e:
                print(f"[gemini] base64 decode error [{i}]: {e}")
                continue

        print("[gemini] all image download/decode attempts failed")
        return None
