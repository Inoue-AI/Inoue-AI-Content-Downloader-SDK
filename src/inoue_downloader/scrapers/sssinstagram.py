"""Instagram downloader via sssinstagram.com API.

This scraper reverse-engineers the sssinstagram.com signing mechanism to make
authenticated API calls without a browser.  The site uses HMAC-SHA256 request
signing with a key embedded in an obfuscated webpack chunk (link.chunk.js,
module 7027).

Key technical details
---------------------
* **API endpoint**: ``POST https://sssinstagram.com/api/convert``
* **Signing**: HMAC-SHA256(embedded_key, url + timestamp_ms)
* **Transport**: HTTP/2 via noble-tls with Chrome TLS fingerprinting.
  Cloudflare rejects HTTP/1.1 requests with a captcha challenge.
* **Body encoding**: ``application/x-www-form-urlencoded``
* **Response format**: JSON array of media items (for profiles) or a single
  JSON object (for individual posts/reels).

Note: The HMAC key (``_HMAC_KEY``) is extracted from the site's JS bundle and
may change when the site is updated.  If requests start returning
``invalid_request`` the key likely needs to be re-extracted.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
import noble_tls
from noble_tls import Client

from ..config import ProxyConfig
from ..enums import ContentType, Platform
from ..exceptions import ScraperError
from ..models import ContentMetadata
from .base import AbstractScraper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signing constants extracted from sssinstagram.com (link.chunk.js module 7027)
# ---------------------------------------------------------------------------
_HMAC_KEY = bytes.fromhex(
    "df73cf7be343f9701ce0f2ae809f9bd752e82fbb7017f463141664465b8ce8e0"
)
_EMBEDDED_TS = 1770970183770
_SIGNING_VERSION = 2

# ---------------------------------------------------------------------------
# API configuration
# ---------------------------------------------------------------------------
_API_URL = "https://sssinstagram.com/api/convert"

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_COMMON_HEADERS = {
    "Origin": "https://sssinstagram.com",
    "Referer": "https://sssinstagram.com/en1",
    "Accept": "*/*",
}

# noble-tls profile for HTTP/2 + Chrome TLS fingerprint
_TLS_CLIENT = Client.CHROME_131


def _sign_request(url: str) -> dict[str, str]:
    """Generate signed request parameters for the sssinstagram API.

    The signing algorithm is:
    1. ``ts`` = current Unix time in milliseconds.
    2. ``_s`` = HMAC-SHA256(key, url + ts) as hex digest.
    3. ``_ts`` = embedded timestamp from chunk (constant).
    4. ``_tsc`` = 0 (counter, always zero).
    5. ``_sv`` = 2 (signing version).
    """
    ts = int(time.time() * 1000)
    message = f"{url}{ts}"
    signature = hmac.new(_HMAC_KEY, message.encode(), hashlib.sha256).hexdigest()
    return {
        "sf_url": url,
        "ts": str(ts),
        "_ts": str(_EMBEDDED_TS),
        "_tsc": "0",
        "_sv": str(_SIGNING_VERSION),
        "_s": signature,
    }


# ---------------------------------------------------------------------------
# HTTP transport via noble-tls (HTTP/2, Chrome TLS fingerprint)
# ---------------------------------------------------------------------------


async def _api_post(
    data: dict[str, str], proxy: str | None = None
) -> dict[str, Any] | list[Any]:
    """Send a signed POST to the sssinstagram convert API via noble-tls."""
    session = noble_tls.Session(client=_TLS_CLIENT, proxy=proxy)
    try:
        resp = await session.post(
            _API_URL, data=data, headers=_COMMON_HEADERS
        )

        if resp.status_code == 422:
            body = resp.text
            if "Captcha required" in body:
                raise ScraperError(
                    "sssinstagram.com: Captcha required. "
                    "This usually means the HMAC key has changed."
                )
            raise ScraperError(
                f"sssinstagram.com returned HTTP 422: {body[:200]}"
            )

        if resp.status_code != 200:
            raise ScraperError(
                f"sssinstagram.com returned HTTP {resp.status_code}"
            )

        return resp.json()  # type: ignore[no-any-return]
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_response(
    raw: dict[str, Any] | list[Any],
    original_url: str,
) -> tuple[ContentMetadata, list[tuple[str, str, str]]]:
    """Parse the API response into metadata and a list of (url, type, ext).

    The API returns either:
    - A JSON **array** of items (for profile / multi-post responses).
    - A JSON **object** with ``url``, ``meta``, ``thumb`` etc.
      (for single-post responses).
    """
    items: list[dict[str, Any]]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if raw.get("success") is False:
            msg = raw.get(
                "message", raw.get("response_type", "unknown error")
            )
            raise ScraperError(f"sssinstagram.com API error: {msg}")
        items = [raw]
    else:
        raise ScraperError(f"Unexpected API response type: {type(raw)}")

    if not items:
        raise ScraperError("sssinstagram.com returned empty result set")

    # Collect all downloadable media
    media: list[tuple[str, str, str]] = []  # (url, media_type, extension)
    first_meta: dict[str, Any] = {}

    for item in items:
        meta = item.get("meta", {})
        if not first_meta:
            first_meta = meta

        urls = item.get("url", [])
        if isinstance(urls, list):
            for u in urls:
                if isinstance(u, dict) and u.get("url"):
                    media.append((
                        u["url"],
                        u.get("type", "video"),
                        u.get(
                            "ext",
                            _guess_ext(u["url"], u.get("type", "video")),
                        ),
                    ))

    if not media:
        raise ScraperError(
            "No downloadable media found in sssinstagram.com response"
        )

    # Build metadata
    source_id_match = re.search(
        r"/(?:p|reel|tv|stories)/([A-Za-z0-9_-]+)", original_url
    )
    if not source_id_match:
        # For profile URLs
        username_match = re.search(
            r"instagram\.com/([A-Za-z0-9_.]+)", original_url
        )
        source_id = (
            username_match.group(1) if username_match else original_url
        )
    else:
        source_id = source_id_match.group(1)

    # Determine content type
    types = {ext for _, _, ext in media}
    if len(media) > 1:
        content_type = ContentType.CAROUSEL
    elif "mp4" in types or "video" in {t for _, t, _ in media}:
        content_type = ContentType.VIDEO
    else:
        content_type = ContentType.IMAGE

    title = first_meta.get("title")
    if isinstance(title, str) and len(title) > 200:
        title = title[:200]

    metadata = ContentMetadata(
        platform=Platform.INSTAGRAM,
        content_type=content_type,
        title=title,
        author=first_meta.get("username"),
        like_count=first_meta.get("like_count"),
        original_url=original_url,
        source_id=source_id,
        thumbnail_url=items[0].get("thumb") if items else None,
    )

    return metadata, media


def _guess_ext(url: str, media_type: str) -> str:
    """Guess file extension from URL path or media type."""
    parsed = urlparse(url)
    path = parsed.path
    if "." in path.split("/")[-1]:
        ext = path.split("/")[-1].rsplit(".", 1)[-1].split("?")[0]
        if len(ext) <= 5:
            return ext
    return "mp4" if media_type == "video" else "jpg"


# ---------------------------------------------------------------------------
# Public scraper class
# ---------------------------------------------------------------------------


class SssinstagramScraper(AbstractScraper):
    """Instagram downloader via sssinstagram.com API.

    This scraper uses the sssinstagram.com service to download Instagram
    content without requiring Instagram credentials.  It works by:

    1. Signing the request with an HMAC-SHA256 key extracted from the site's JS.
    2. Sending the signed request via HTTP/2 (noble-tls with Chrome fingerprint).
    3. Parsing the JSON response to extract download URLs.

    Supports:
    - Individual posts (``/p/...``)
    - Reels (``/reel/...``)
    - Profile pages (returns latest posts from ``@username``)
    - Photos, videos, and carousels

    Example::

        scraper = SssinstagramScraper()
        metadata, files = await scraper.download(
            "https://www.instagram.com/reel/DVZRlGvkdWg/",
            Path("./downloads"),
        )
    """

    def __init__(self, proxy: ProxyConfig | None = None) -> None:
        super().__init__(proxy)

    async def download(
        self,
        url: str,
        output_dir: Path,
    ) -> tuple[ContentMetadata, list[Path]]:
        """Download Instagram content via sssinstagram.com."""
        logger.info(
            "Attempting Instagram download via sssinstagram.com for: %s", url
        )

        # Step 1: Sign and send the request
        signed = _sign_request(url)
        try:
            raw = await _api_post(signed, proxy=self._proxy_url())
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(
                f"sssinstagram.com request failed: {e}"
            ) from e

        # Step 2: Parse response
        metadata, media_list = _parse_response(raw, url)

        # Step 3: Download each media file
        output_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []

        async with aiohttp.ClientSession(
            headers={"User-Agent": _USER_AGENT},
        ) as session:
            for i, (media_url, _media_type, ext) in enumerate(media_list):
                try:
                    async with session.get(media_url) as resp:
                        if resp.status != 200:
                            logger.warning(
                                "Failed to download media %d: HTTP %s",
                                i,
                                resp.status,
                            )
                            continue

                        content = await resp.read()
                        if not content:
                            logger.warning("Empty content for media %d", i)
                            continue

                        if len(media_list) > 1:
                            filename = f"{metadata.source_id}_{i}.{ext}"
                        else:
                            filename = f"{metadata.source_id}.{ext}"

                        output_path = output_dir / filename
                        output_path.write_bytes(content)
                        downloaded.append(output_path)

                except aiohttp.ClientError as e:
                    logger.warning(
                        "Network error downloading media %d: %s", i, e
                    )
                    continue

        if not downloaded:
            raise ScraperError(
                "Failed to download any files from sssinstagram.com. "
                "The media URLs may have expired."
            )

        logger.info(
            "Instagram content saved via sssinstagram.com: %d file(s)",
            len(downloaded),
        )
        return metadata, downloaded
