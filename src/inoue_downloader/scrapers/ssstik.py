from __future__ import annotations

import logging
import re
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

from ..config import ProxyConfig
from ..enums import ContentType, Platform
from ..exceptions import ScraperError
from ..models import ContentMetadata
from .base import AbstractScraper

logger = logging.getLogger(__name__)

_BASE_URL = "https://ssstik.io"
_DOWNLOAD_ENDPOINT = f"{_BASE_URL}/abc?url=dl"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_HTMX_HEADERS = {
    "Origin": _BASE_URL,
    "Referer": f"{_BASE_URL}/en",
    "Content-Type": "application/x-www-form-urlencoded",
    "HX-Request": "true",
    "HX-Target": "target",
    "HX-Current-URL": f"{_BASE_URL}/en",
}


class SsstikScraper(AbstractScraper):
    """TikTok downloader via ssstik.io web scraper."""

    def __init__(self, proxy: ProxyConfig | None = None) -> None:
        super().__init__(proxy)

    async def _fetch_token(self, session: aiohttp.ClientSession) -> str:
        """GET ssstik.io and extract the `tt` token from the page."""
        async with session.get(f"{_BASE_URL}/en", proxy=self._proxy_url()) as resp:
            if resp.status != 200:
                raise ScraperError(f"ssstik.io returned status {resp.status}")
            text = await resp.text()

        # Try multiple token patterns (site changes over time)
        for pattern in [r"s_tt\s*=\s*'([^']+)'", r"tt:'([\w\d]+)'"]:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        raise ScraperError("Could not extract ssstik.io token from page")

    async def _request_download(self, session: aiohttp.ClientSession, url: str, token: str) -> str:
        """POST to ssstik.io to get the download page HTML."""
        data = {"id": url, "locale": "en", "tt": token}
        async with session.post(
            _DOWNLOAD_ENDPOINT,
            data=data,
            headers=_HTMX_HEADERS,
            proxy=self._proxy_url(),
        ) as resp:
            if resp.status != 200:
                raise ScraperError(f"ssstik.io download endpoint returned status {resp.status}")
            return await resp.text()

    @staticmethod
    def _extract_download_url(html: str) -> str:
        """Parse the response HTML and extract the best download URL."""
        soup = BeautifulSoup(html, "html.parser")

        # Look for the "Without watermark" download link first
        for link in soup.find_all("a", href=True):
            href = str(link["href"])
            link_text = link.get_text(strip=True).lower()
            if href.startswith("http") and "without watermark" in link_text:
                return href

        # Fallback: first valid download link
        for link in soup.find_all("a", href=True):
            href = str(link["href"])
            if href.startswith("http"):
                return href

        raise ScraperError("No download URL found in ssstik.io response")

    @staticmethod
    def _extract_metadata_from_html(html: str, url: str) -> ContentMetadata:
        """Extract whatever metadata we can from the ssstik response."""
        soup = BeautifulSoup(html, "html.parser")

        title = None
        author = None

        # ssstik typically shows the video description
        desc_elem = soup.select_one("#mainpicture .maintext")
        if desc_elem:
            title = desc_elem.get_text(strip=True)[:200]

        # Try to get author from subtext
        sub_elem = soup.select_one("#mainpicture .subtext")
        if sub_elem:
            author = sub_elem.get_text(strip=True)

        # Extract source ID from the TikTok URL
        source_id_match = re.search(r"/video/(\d+)", url)
        if source_id_match:
            source_id = source_id_match.group(1)
        else:
            # Short URLs (vm.tiktok.com/ZNRufq2ex/) - use the last path segment
            path_segments = [s for s in url.rstrip("/").split("/") if s]
            source_id = path_segments[-1] if path_segments else "unknown"

        return ContentMetadata(
            platform=Platform.TIKTOK,
            content_type=ContentType.VIDEO,
            title=title,
            author=author,
            original_url=url,
            source_id=source_id,
        )

    async def download(self, url: str, output_dir: Path) -> tuple[ContentMetadata, list[Path]]:
        """Download a TikTok video via ssstik.io."""
        logger.info("Attempting TikTok download via ssstik.io for: %s", url)

        session_headers = {"User-Agent": _USER_AGENT}
        async with aiohttp.ClientSession(headers=session_headers) as session:
            token = await self._fetch_token(session)
            html = await self._request_download(session, url, token)
            download_url = self._extract_download_url(html)
            metadata = self._extract_metadata_from_html(html, url)

            # Download the actual video file (direct connection, no proxy)
            # tikcdn.io requires Referer header
            dl_headers = {"Referer": f"{_BASE_URL}/"}
            async with session.get(download_url, headers=dl_headers) as resp:
                if resp.status != 200:
                    raise ScraperError(f"Failed to download TikTok video: HTTP {resp.status}")

                # Determine filename
                filename = f"{metadata.source_id}.mp4"
                output_path = output_dir / filename

                content = await resp.read()
                if not content:
                    raise ScraperError("Downloaded empty file from ssstik.io")

                output_path.write_bytes(content)

        logger.info("TikTok video saved via ssstik.io: %s", output_path)
        return metadata, [output_path]
