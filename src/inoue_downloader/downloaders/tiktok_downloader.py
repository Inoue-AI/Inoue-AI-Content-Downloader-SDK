from __future__ import annotations

import logging
from pathlib import Path

import aiohttp

from ..config import DownloaderConfig
from ..exceptions import ScraperError
from ..models import ContentMetadata
from ..scrapers.ssstik import SsstikScraper
from .base import AbstractDownloader

logger = logging.getLogger(__name__)


class TikTokDownloader(AbstractDownloader):
    """Downloader for TikTok via ssstik.io web scraper."""

    def __init__(self, config: DownloaderConfig) -> None:
        self._config = config
        self._scraper = SsstikScraper(proxy=config.proxy)

    async def extract_metadata(self, url: str) -> ContentMetadata:
        """Extract metadata from a TikTok URL via ssstik.io."""
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                token = await self._scraper._fetch_token(session)
                html = await self._scraper._request_download(session, url, token)
                return self._scraper._extract_metadata_from_html(html, url)
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"TikTok metadata extraction failed: {e}") from e

    async def download(self, url: str, output_dir: Path) -> tuple[ContentMetadata, list[Path]]:
        """Download a TikTok video via ssstik.io."""
        try:
            return await self._scraper.download(url, output_dir)
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"TikTok download failed: {e}") from e
