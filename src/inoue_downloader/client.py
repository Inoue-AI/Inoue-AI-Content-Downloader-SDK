from __future__ import annotations

import asyncio
import logging
import mimetypes
import time
from types import TracebackType

from .config import DownloaderConfig
from .downloaders.base import AbstractDownloader
from .downloaders.factory import DownloaderFactory
from .enums import DownloadStatus
from .exceptions import ContentTooLargeError, InoueDownloaderError
from .models import ContentMetadata, DownloadedFile, DownloadResult
from .platform_detection import detect_platform
from .storage.base import AbstractStorageBackend
from .storage.local_storage import LocalStorageBackend
from .storage.s3_storage import S3StorageBackend
from .utils.temp_files import AsyncTempDir

logger = logging.getLogger(__name__)


class InoueDownloader:
    """Main SDK client for downloading social media content.

    Usage::

        async with InoueDownloader(config) as downloader:
            result = await downloader.download("https://youtube.com/watch?v=...")
    """

    def __init__(self, config: DownloaderConfig) -> None:
        self._config = config
        self._downloaders: dict[str, AbstractDownloader] = {}
        self._setup_logging()

    def _setup_logging(self) -> None:
        level = getattr(logging, self._config.log_level.upper(), logging.INFO)
        logging.basicConfig(level=level)

    def _is_s3_storage(self, save_locally: str | None = None) -> bool:
        return save_locally is None and self._config.s3 is not None

    def _get_storage(self, save_locally: str | None = None) -> AbstractStorageBackend:
        if save_locally:
            return LocalStorageBackend(save_locally)
        if self._config.s3:
            return S3StorageBackend(self._config.s3)
        if self._config.local_output_dir:
            return LocalStorageBackend(self._config.local_output_dir)
        raise InoueDownloaderError("No storage backend configured")

    def _get_downloader(self, platform: object) -> AbstractDownloader:
        key = str(platform)
        if key not in self._downloaders:
            self._downloaders[key] = DownloaderFactory.create(platform, self._config)  # type: ignore[arg-type]
        return self._downloaders[key]

    async def download(
        self,
        url: str,
        save_locally: str | None = None,
    ) -> DownloadResult:
        """Download content from a URL and upload to configured storage.

        Args:
            url: The content URL (YouTube, TikTok, Instagram).
            save_locally: If provided, saves to this local directory instead of S3.

        Returns:
            DownloadResult with metadata, file info, and S3/local URLs.
        """
        start = time.monotonic()
        platform = detect_platform(url)
        downloader = self._get_downloader(platform)
        storage = self._get_storage(save_locally)
        is_s3 = self._is_s3_storage(save_locally)

        async with AsyncTempDir(self._config.temp_dir) as temp_dir:
            metadata, local_files = await downloader.download(url, temp_dir)
            downloaded_files: list[DownloadedFile] = []

            for file_path in local_files:
                file_size = file_path.stat().st_size

                if (
                    self._config.max_file_size_mb
                    and file_size > self._config.max_file_size_mb * 1024 * 1024
                ):
                    raise ContentTooLargeError(
                        f"File {file_path.name} is {file_size} bytes, "
                        f"exceeds limit of {self._config.max_file_size_mb}MB"
                    )

                mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                s3_key = f"{platform.value}/{metadata.source_id}/{file_path.name}"
                result_url = await storage.upload(file_path, s3_key, mime_type)

                downloaded_files.append(
                    DownloadedFile(
                        filename=file_path.name,
                        content_type=metadata.content_type,
                        file_size_bytes=file_size,
                        mime_type=mime_type,
                        s3_key=s3_key if is_s3 else None,
                        s3_url=result_url if is_s3 else None,
                        local_path=result_url if not is_s3 else None,
                    )
                )

            elapsed = time.monotonic() - start
            return DownloadResult(
                status=DownloadStatus.SUCCESS,
                source_url=url,
                platform=platform,
                metadata=metadata,
                files=downloaded_files,
                elapsed_seconds=round(elapsed, 2),
            )

    async def download_many(
        self,
        urls: list[str],
        save_locally: str | None = None,
    ) -> list[DownloadResult]:
        """Download multiple URLs concurrently (bounded by max_concurrent_downloads)."""
        semaphore = asyncio.Semaphore(self._config.max_concurrent_downloads)

        async def _bounded_download(url: str) -> DownloadResult:
            async with semaphore:
                return await self.download(url, save_locally=save_locally)

        results = await asyncio.gather(
            *[_bounded_download(url) for url in urls],
            return_exceptions=False,
        )
        return list(results)

    async def extract_metadata(self, url: str) -> ContentMetadata:
        """Extract metadata from a URL without downloading."""
        platform = detect_platform(url)
        downloader = self._get_downloader(platform)
        return await downloader.extract_metadata(url)

    async def __aenter__(self) -> InoueDownloader:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        for downloader in self._downloaders.values():
            await downloader.cleanup()
        self._downloaders.clear()
