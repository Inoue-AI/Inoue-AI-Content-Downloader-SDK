from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import ContentMetadata


class AbstractDownloader(ABC):
    """Base class that all platform downloaders must implement."""

    @abstractmethod
    async def extract_metadata(self, url: str) -> ContentMetadata:
        """Extract metadata from a URL without downloading content."""
        ...

    @abstractmethod
    async def download(self, url: str, output_dir: Path) -> tuple[ContentMetadata, list[Path]]:
        """Download content to a local directory.

        Returns:
            A tuple of (metadata, list_of_downloaded_file_paths).
        """
        ...

    async def cleanup(self) -> None:
        """Optional cleanup hook for releasing resources."""
