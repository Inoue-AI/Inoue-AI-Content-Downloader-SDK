from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..config import ProxyConfig
from ..models import ContentMetadata


class AbstractScraper(ABC):
    """Base class for web-scraper fallback downloaders."""

    def __init__(self, proxy: ProxyConfig | None = None) -> None:
        self._proxy = proxy

    def _proxy_url(self) -> str | None:
        """Return the HTTPS proxy (preferred) or HTTP proxy."""
        if self._proxy is None:
            return None
        return self._proxy.https or self._proxy.http

    @abstractmethod
    async def download(self, url: str, output_dir: Path) -> tuple[ContentMetadata, list[Path]]:
        """Download content via web scraper.

        Returns:
            A tuple of (metadata, list_of_downloaded_file_paths).
        """
        ...
