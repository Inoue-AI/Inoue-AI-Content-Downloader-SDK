from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import noble_tls
from bs4 import BeautifulSoup
from noble_tls import Client

from ..config import ProxyConfig
from ..enums import ContentType, Platform
from ..exceptions import ScraperError
from ..models import ContentMetadata
from .base import AbstractScraper

logger = logging.getLogger(__name__)

_BASE_URL = "https://snapinsta.to"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# noble-tls profile that bypasses Cloudflare on snapinsta.to
_TLS_CLIENT = Client.CHROME_131


class SnapinstaScraper(AbstractScraper):
    """Instagram downloader via snapinsta.to web scraper.

    Uses noble-tls with HTTP/2 and Chrome TLS fingerprinting to bypass
    Cloudflare protection, then calls the snapinsta.to /api/ajaxSearch endpoint.

    Note: snapinsta.to may require Cloudflare Turnstile CAPTCHA tokens,
    which cannot be generated without a real browser. In that case,
    requests will fail and the caller should fall back to another method
    (e.g., sssinstagram.com, instagrapi with credentials, or Apify).
    """

    def __init__(self, proxy: ProxyConfig | None = None) -> None:
        super().__init__(proxy)

    async def _create_session(self) -> noble_tls.Session:
        """Create a noble-tls session with Chrome TLS fingerprint."""
        proxy = self._proxy_url()
        session = noble_tls.Session(client=_TLS_CLIENT)
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}
        return session

    async def _fetch_page_config(self, session: noble_tls.Session) -> dict[str, str]:
        """GET snapinsta.to and extract page configuration variables."""
        resp = await session.get(f"{_BASE_URL}/")
        if resp.status_code != 200:
            raise ScraperError(f"snapinsta.to returned status {resp.status_code}")

        text = resp.text

        if "Just a moment" in text:
            raise ScraperError("snapinsta.to Cloudflare challenge could not be bypassed")

        config: dict[str, str] = {}

        # Extract k_* variables from inline script
        for match in re.finditer(r'k_(\w+)="([^"]+)"', text):
            config[f"k_{match.group(1)}"] = match.group(2)

        if "k_url_search" not in config:
            raise ScraperError("Could not extract snapinsta.to API configuration from page")

        return config

    async def _search(
        self,
        session: noble_tls.Session,
        config: dict[str, str],
        url: str,
    ) -> dict[str, object]:
        """POST to the ajaxSearch API endpoint."""
        search_url = config.get("k_url_search", f"{_BASE_URL}/api/ajaxSearch")

        headers = {
            "Origin": _BASE_URL,
            "Referer": f"{_BASE_URL}/",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }

        data = {
            "q": url,
            "t": "media",
            "lang": config.get("k_lang", "en"),
            "v": config.get("k_ver", ""),
        }

        resp = await session.post(search_url, data=data, headers=headers)
        if resp.status_code != 200:
            raise ScraperError(f"snapinsta.to search endpoint returned status {resp.status_code}")

        try:
            result: dict[str, object] = resp.json()
        except Exception as e:
            raise ScraperError(f"snapinsta.to returned invalid JSON: {e}") from e

        status = result.get("status")
        if status != "ok":
            mess = result.get("mess", "Unknown error")
            raise ScraperError(f"snapinsta.to search failed: {mess}")

        # Check if response contains data or an error message
        if result.get("mess") and "token" in str(result.get("mess", "")).lower():
            raise ScraperError(
                "snapinsta.to requires Cloudflare Turnstile CAPTCHA token. "
                "This cannot be automated without a real browser."
            )

        return result

    @staticmethod
    def _extract_download_urls_from_result(
        result: dict[str, object],
    ) -> list[tuple[str, str]]:
        """Extract download URLs from the API response."""
        urls: list[tuple[str, str]] = []

        # The response may contain HTML with download links
        data = result.get("data", "")
        if isinstance(data, str) and data:
            urls.extend(_extract_media_urls_from_html(data))

        # Some responses have direct URL fields
        for key in ("url", "video_url", "download_url"):
            val = result.get(key)
            if isinstance(val, str) and val.startswith("http"):
                urls.append((val, "video"))

        return urls

    @staticmethod
    def _extract_download_urls(html: str) -> list[tuple[str, str]]:
        """Parse decoded HTML for download URLs (legacy compatibility)."""
        return _extract_media_urls_from_html(html)

    @staticmethod
    def _decode_response(raw_js: str) -> str:
        """Extract and deobfuscate the HTML from a JS response (legacy)."""
        match = re.search(r'\("([^"]+)",\d+,"([^"]+)",(\d+),(\d+),\d+\)', raw_js)
        if not match:
            if "<" in raw_js and ("href=" in raw_js or "src=" in raw_js):
                return raw_js
            raise ScraperError("Could not extract obfuscated parameters from snapinsta.to")

        h = match.group(1)
        t = match.group(2)
        e = int(match.group(3))
        r = int(match.group(4))

        return _deobfuscate(h, 0, t, e, r)

    async def _fetch_token(self, session: aiohttp.ClientSession) -> str:
        """Legacy: GET snapinsta.to and extract the CSRF token."""
        async with session.get(f"{_BASE_URL}/", proxy=self._proxy_url()) as resp:
            if resp.status != 200:
                raise ScraperError(f"snapinsta.to returned status {resp.status}")
            text = await resp.text()

        match = re.search(r'name="token"\s+value="(.*?)"', text)
        if not match:
            raise ScraperError("Could not extract snapinsta.to CSRF token")
        return match.group(1)

    async def _request_download(self, session: aiohttp.ClientSession, url: str, token: str) -> str:
        """Legacy: POST to snapinsta.to to get the obfuscated response."""
        data = {"url": url, "token": token}
        headers = {
            "Origin": _BASE_URL,
            "Referer": f"{_BASE_URL}/",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        async with session.post(
            f"{_BASE_URL}/action2.php",
            data=data,
            headers=headers,
            proxy=self._proxy_url(),
        ) as resp:
            if resp.status != 200:
                raise ScraperError(f"snapinsta.to action endpoint returned status {resp.status}")
            return await resp.text()

    async def download(self, url: str, output_dir: Path) -> tuple[ContentMetadata, list[Path]]:
        """Download Instagram content via snapinsta.to."""
        logger.info("Attempting Instagram download via snapinsta.to for: %s", url)

        # Use noble-tls (async, HTTP/2, Chrome TLS fingerprint)
        session = await self._create_session()
        try:
            config = await self._fetch_page_config(session)
            result = await self._search(session, config, url)
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"snapinsta.to request failed: {e}") from e
        finally:
            await session.close()

        media_urls = self._extract_download_urls_from_result(result)

        if not media_urls:
            raise ScraperError("No download URLs found in snapinsta.to response")

        # Extract source ID from Instagram URL
        source_id_match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
        if source_id_match:
            source_id = source_id_match.group(1)
        else:
            path_segments = [s for s in url.rstrip("/").split("/") if s]
            source_id = path_segments[-1] if path_segments else "unknown"

        # Determine content type
        has_video = any(t == "video" for _, t in media_urls)
        if len(media_urls) > 1 and not has_video:
            content_type = ContentType.CAROUSEL
        elif has_video:
            content_type = ContentType.VIDEO
        else:
            content_type = ContentType.IMAGE

        # Download media files using aiohttp for async streaming
        downloaded_paths: list[Path] = []
        async with aiohttp.ClientSession(headers={"User-Agent": _USER_AGENT}) as dl_session:
            for i, (media_url, media_type) in enumerate(media_urls):
                try:
                    async with dl_session.get(media_url) as resp:
                        if resp.status != 200:
                            logger.warning(
                                "Failed to download media %d: HTTP %s",
                                i,
                                resp.status,
                            )
                            continue

                        content = await resp.read()
                        if not content:
                            continue

                        ext = _guess_extension(media_url, media_type)
                        if len(media_urls) > 1:
                            filename = f"{source_id}_{i}{ext}"
                        else:
                            filename = f"{source_id}{ext}"
                        output_path = output_dir / filename
                        output_path.write_bytes(content)
                        downloaded_paths.append(output_path)
                except aiohttp.ClientError as e:
                    logger.warning("Network error downloading media %d: %s", i, e)
                    continue

        if not downloaded_paths:
            raise ScraperError("Failed to download any files from snapinsta.to")

        metadata = ContentMetadata(
            platform=Platform.INSTAGRAM,
            content_type=content_type,
            original_url=url,
            source_id=source_id,
        )

        logger.info(
            "Instagram content saved via snapinsta.to: %d file(s)",
            len(downloaded_paths),
        )
        return metadata, downloaded_paths


def _deobfuscate(h: str, n: int, t: str, e: int, r: int) -> str:
    """Deobfuscate the JS-encoded response from snapinsta.to (legacy)."""
    result = ""
    i = 0

    while i < len(h):
        s = ""
        while i < len(h) and h[i] != t[e]:
            s += h[i]
            i += 1
        i += 1

        for j, ch in enumerate(t[:e]):
            s = s.replace(ch, str(j))

        val = 0
        for ch in s:
            val = val * e + int(ch)

        result += chr(val - r)

    return result


def _extract_media_urls_from_html(html: str) -> list[tuple[str, str]]:
    """Parse HTML for Instagram media download URLs."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[tuple[str, str]] = []

    # Look for video download links
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        if href.startswith("http") and ("cdninstagram" in href or "scontent" in href):
            urls.append((href, "video"))

    # Look for image sources
    for img in soup.find_all("img", src=True):
        src = str(img["src"])
        if src.startswith("http") and ("cdninstagram" in src or "scontent" in src):
            urls.append((src, "image"))

    # Fallback: any http links that look like media downloads
    if not urls:
        for link in soup.find_all("a", href=True):
            href = str(link["href"])
            if href.startswith("http") and href != "#":
                btn_text = link.get_text(strip=True).lower()
                if "download" in btn_text:
                    media_type = "video" if "video" in btn_text else "image"
                    urls.append((href, media_type))

    return urls


def _guess_extension(url: str, media_type: str) -> str:
    """Guess file extension from URL path or media type."""
    parsed = urlparse(url)
    path = parsed.path
    if "." in path.split("/")[-1]:
        ext = "." + path.split("/")[-1].rsplit(".", 1)[-1].split("?")[0]
        if len(ext) <= 5:
            return ext
    return ".mp4" if media_type == "video" else ".jpg"
