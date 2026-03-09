from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from yt_dlp import YoutubeDL

from ..config import DownloaderConfig
from ..enums import ContentType, Platform
from ..exceptions import YtDlpError
from ..models import ContentMetadata
from .base import AbstractDownloader

logger = logging.getLogger(__name__)


class YtDlpDownloader(AbstractDownloader):
    """Downloader for YouTube and TikTok using yt-dlp."""

    def __init__(self, config: DownloaderConfig, platform: Platform) -> None:
        self._config = config
        self._platform = platform

    def _build_ydl_opts(self, output_dir: Path) -> dict[str, object]:
        opts: dict[str, object] = {
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "format": self._config.preferred_video_quality,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "socket_timeout": self._config.request_timeout,
            "merge_output_format": "mp4",
            "progress_hooks": [self._progress_hook],
        }

        if self._config.proxy:
            proxy_url = self._config.proxy.https or self._config.proxy.http
            if proxy_url:
                opts["proxy"] = proxy_url

        return opts

    def _progress_hook(self, d: dict[str, object]) -> None:
        status = d.get("status")
        if status == "downloading":
            logger.debug("Downloading: %s", d.get("_percent_str", "?"))
        elif status == "finished":
            logger.info("Download finished: %s", d.get("filename"))

    def _build_extract_opts(self) -> dict[str, object]:
        opts: dict[str, object] = {"quiet": True, "no_warnings": True}
        if self._config.proxy:
            proxy_url = self._config.proxy.https or self._config.proxy.http
            if proxy_url:
                opts["proxy"] = proxy_url
        return opts

    async def extract_metadata(self, url: str) -> ContentMetadata:
        def _extract() -> dict[str, object]:
            with YoutubeDL(self._build_extract_opts()) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise YtDlpError(f"yt-dlp returned no info for: {url}")
                return dict(info)

        try:
            info = await asyncio.to_thread(_extract)
        except YtDlpError:
            raise
        except Exception as e:
            raise YtDlpError(f"Failed to extract metadata: {e}") from e

        return self._info_to_metadata(info, url)

    async def download(self, url: str, output_dir: Path) -> tuple[ContentMetadata, list[Path]]:
        opts = self._build_ydl_opts(output_dir)

        def _download() -> dict[str, object]:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise YtDlpError(f"yt-dlp returned no info for: {url}")
                return dict(info)

        try:
            info = await asyncio.to_thread(_download)
        except YtDlpError:
            raise
        except Exception as e:
            raise YtDlpError(f"Download failed: {e}") from e

        metadata = self._info_to_metadata(info, url)
        downloaded_files = sorted(output_dir.iterdir())
        if not downloaded_files:
            raise YtDlpError("yt-dlp reported success but no files were written")
        return metadata, downloaded_files

    def _info_to_metadata(self, info: dict[str, object], url: str) -> ContentMetadata:
        content_type = ContentType.VIDEO
        duration = info.get("duration")
        if duration is None and not info.get("is_live"):
            content_type = ContentType.IMAGE

        upload_date_raw = info.get("upload_date")
        upload_date: datetime | None = None
        if isinstance(upload_date_raw, str) and len(upload_date_raw) == 8:
            with contextlib.suppress(ValueError):
                upload_date = datetime.strptime(upload_date_raw, "%Y%m%d").replace(tzinfo=UTC)

        extra: dict[str, str | int | float | bool | None] = {}
        for key in ("extractor", "format", "resolution"):
            val = info.get(key)
            if isinstance(val, str | int | float | bool) or val is None:
                extra[key] = val

        return ContentMetadata(
            platform=self._platform,
            content_type=content_type,
            title=info.get("title") if isinstance(info.get("title"), str) else None,
            description=(
                info.get("description") if isinstance(info.get("description"), str) else None
            ),
            author=_str_or_none(info.get("uploader") or info.get("channel")),
            author_id=_str_or_none(info.get("uploader_id") or info.get("channel_id")),
            duration_seconds=float(duration) if isinstance(duration, int | float) else None,
            view_count=int(vc) if isinstance((vc := info.get("view_count")), int | float) else None,
            like_count=int(lc) if isinstance((lc := info.get("like_count")), int | float) else None,
            upload_date=upload_date,
            thumbnail_url=(
                info.get("thumbnail") if isinstance(info.get("thumbnail"), str) else None
            ),
            original_url=url,
            source_id=str(info.get("id", "")),
            tags=info.get("tags") if isinstance(info.get("tags"), list) else [],
            extra=extra,
        )


def _str_or_none(val: object) -> str | None:
    return str(val) if val is not None and isinstance(val, str) else None
