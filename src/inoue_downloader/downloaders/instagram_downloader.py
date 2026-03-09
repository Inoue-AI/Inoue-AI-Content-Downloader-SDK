from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from ..config import DownloaderConfig
from ..enums import ContentType, DownloadProvider, Platform
from ..exceptions import InstagramAuthRequiredError, InstagramError, ScraperError
from ..models import ContentMetadata
from ..scrapers.snapinsta import SnapinstaScraper
from ..scrapers.sssinstagram import SssinstagramScraper
from .base import AbstractDownloader

logger = logging.getLogger(__name__)


class InstagramDownloader(AbstractDownloader):
    """Downloader for Instagram.

    When *provider* is ``None`` (default / ``YTDLP``), the downloader uses a
    three-level fallback chain: sssinstagram.com → snapinsta.to → instagrapi.

    When a specific *provider* is given (``SSSINSTAGRAM``, ``SNAPINSTA``, or
    ``INSTAGRAPI``), only that single scraper is used — no fallback.
    """

    def __init__(
        self,
        config: DownloaderConfig,
        *,
        provider: DownloadProvider | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._sssinstagram = SssinstagramScraper(proxy=config.proxy)
        self._snapinsta = SnapinstaScraper(proxy=config.proxy)
        self._insta_client: object | None = None

    # ------------------------------------------------------------------
    # extract_metadata
    # ------------------------------------------------------------------

    async def extract_metadata(self, url: str) -> ContentMetadata:
        if self._provider == DownloadProvider.SSSINSTAGRAM:
            return await self._extract_metadata_sssinstagram(url)
        if self._provider == DownloadProvider.SNAPINSTA:
            return await self._extract_metadata_snapinsta(url)
        if self._provider == DownloadProvider.INSTAGRAPI:
            return await self._extract_metadata_instagrapi(url)

        # Auto mode: fallback chain
        try:
            return await self._extract_metadata_sssinstagram(url)
        except (ScraperError, Exception):
            logger.debug("sssinstagram.com metadata failed, trying snapinsta.to")

        try:
            return await self._extract_metadata_snapinsta(url)
        except (ScraperError, Exception):
            logger.debug("snapinsta.to metadata failed, trying instagrapi")

        return await self._extract_metadata_instagrapi(url)

    # ------------------------------------------------------------------
    # download
    # ------------------------------------------------------------------

    async def download(self, url: str, output_dir: Path) -> tuple[ContentMetadata, list[Path]]:
        if self._provider == DownloadProvider.SSSINSTAGRAM:
            return await self._sssinstagram.download(url, output_dir)
        if self._provider == DownloadProvider.SNAPINSTA:
            return await self._snapinsta.download(url, output_dir)
        if self._provider == DownloadProvider.INSTAGRAPI:
            return await self._download_instagrapi(url, output_dir)

        # Auto mode: fallback chain
        try:
            return await self._sssinstagram.download(url, output_dir)
        except (ScraperError, Exception) as e:
            logger.debug("sssinstagram.com download failed (%s), trying snapinsta.to", e)

        try:
            return await self._snapinsta.download(url, output_dir)
        except (ScraperError, Exception):
            logger.debug("snapinsta.to download failed, trying instagrapi")

        return await self._download_instagrapi(url, output_dir)

    # ------------------------------------------------------------------
    # Per-scraper metadata helpers
    # ------------------------------------------------------------------

    async def _extract_metadata_sssinstagram(self, url: str) -> ContentMetadata:
        from ..scrapers.sssinstagram import _api_post, _parse_response, _sign_request

        signed = _sign_request(url)
        proxy = self._config.proxy.https if self._config.proxy else None
        raw = await _api_post(signed, proxy=proxy)
        metadata, _ = _parse_response(raw, url)
        return metadata

    async def _extract_metadata_snapinsta(self, url: str) -> ContentMetadata:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            token = await self._snapinsta._fetch_token(session)
            raw = await self._snapinsta._request_download(session, url, token)
            decoded = self._snapinsta._decode_response(raw)
            media_urls = self._snapinsta._extract_download_urls(decoded)

            source_id_match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
            if source_id_match:
                source_id = source_id_match.group(1)
            else:
                path_segments = [s for s in url.rstrip("/").split("/") if s]
                source_id = path_segments[-1] if path_segments else "unknown"

            has_video = any(t == "video" for _, t in media_urls)
            content_type = ContentType.VIDEO if has_video else ContentType.IMAGE

            return ContentMetadata(
                platform=Platform.INSTAGRAM,
                content_type=content_type,
                original_url=url,
                source_id=source_id,
            )

    # ------------------------------------------------------------------
    # instagrapi
    # ------------------------------------------------------------------

    async def _ensure_instagrapi_client(self) -> object:
        if self._insta_client is not None:
            return self._insta_client

        creds = self._config.instagram
        if creds is None:
            raise InstagramAuthRequiredError(
                "Instagram credentials are required for this content. "
                "Scrapers failed and no InstagramCredentials were provided in config."
            )

        try:
            from instagrapi import Client as InstaClient
        except ImportError as e:
            raise InstagramError(
                "instagrapi is required for authenticated Instagram downloads. "
                "Install it with: pip install instagrapi"
            ) from e

        client = InstaClient()

        if creds.session_file_path:
            session_path = Path(creds.session_file_path)
            if session_path.exists():
                try:
                    await asyncio.to_thread(client.load_settings, str(session_path))
                    await asyncio.to_thread(
                        client.login,
                        creds.username,
                        creds.password.get_secret_value(),
                    )
                    self._insta_client = client
                    logger.info("Restored Instagram session from file")
                    return client
                except Exception:
                    logger.debug("Session restore failed, will login fresh")

        try:
            await asyncio.to_thread(client.login, creds.username, creds.password.get_secret_value())
        except Exception as e:
            raise InstagramError(f"Instagram login failed: {e}") from e

        if creds.session_file_path:
            try:
                await asyncio.to_thread(client.dump_settings, creds.session_file_path)
            except Exception:
                logger.warning("Failed to persist Instagram session")

        self._insta_client = client
        return client

    async def _extract_metadata_instagrapi(self, url: str) -> ContentMetadata:
        client = await self._ensure_instagrapi_client()

        try:
            media_pk = await asyncio.to_thread(client.media_pk_from_url, url)  # type: ignore[union-attr]
            media_info = await asyncio.to_thread(client.media_info, media_pk)  # type: ignore[union-attr]
        except Exception as e:
            raise InstagramError(f"Failed to extract Instagram metadata: {e}") from e

        return self._media_to_metadata(media_info, url)

    async def _download_instagrapi(
        self, url: str, output_dir: Path
    ) -> tuple[ContentMetadata, list[Path]]:
        client = await self._ensure_instagrapi_client()

        try:
            media_pk = await asyncio.to_thread(client.media_pk_from_url, url)  # type: ignore[union-attr]
            media_info = await asyncio.to_thread(client.media_info, media_pk)  # type: ignore[union-attr]
        except Exception as e:
            raise InstagramError(f"Failed to get Instagram media info: {e}") from e

        metadata = self._media_to_metadata(media_info, url)
        downloaded_paths: list[Path] = []
        media_type = media_info.media_type

        try:
            if media_type == 1:
                path = await asyncio.to_thread(
                    client.photo_download,
                    media_pk,
                    folder=output_dir,  # type: ignore[union-attr]
                )
                downloaded_paths.append(Path(path))
            elif media_type == 2:
                path = await asyncio.to_thread(
                    client.video_download,
                    media_pk,
                    folder=output_dir,  # type: ignore[union-attr]
                )
                downloaded_paths.append(Path(path))
            elif media_type == 8:
                paths = await asyncio.to_thread(
                    client.album_download,
                    media_pk,
                    folder=output_dir,  # type: ignore[union-attr]
                )
                downloaded_paths.extend(Path(p) for p in paths)
            else:
                raise InstagramError(f"Unsupported Instagram media type: {media_type}")
        except InstagramError:
            raise
        except Exception as e:
            raise InstagramError(f"Instagram download failed: {e}") from e

        if not downloaded_paths:
            raise InstagramError("No files were downloaded from Instagram")

        return metadata, downloaded_paths

    @staticmethod
    def _media_to_metadata(media_info: object, url: str) -> ContentMetadata:
        type_map = {1: ContentType.IMAGE, 2: ContentType.VIDEO, 8: ContentType.CAROUSEL}
        media_type = getattr(media_info, "media_type", 2)
        content_type = type_map.get(media_type, ContentType.VIDEO)

        caption = getattr(media_info, "caption_text", None)
        user = getattr(media_info, "user", None)

        return ContentMetadata(
            platform=Platform.INSTAGRAM,
            content_type=content_type,
            title=caption[:100] if caption else None,
            description=caption,
            author=getattr(user, "username", None) if user else None,
            author_id=str(getattr(user, "pk", "")) if user else None,
            duration_seconds=getattr(media_info, "video_duration", None),
            view_count=getattr(media_info, "view_count", None),
            like_count=getattr(media_info, "like_count", None),
            upload_date=getattr(media_info, "taken_at", None),
            thumbnail_url=(
                str(getattr(media_info, "thumbnail_url", None))
                if getattr(media_info, "thumbnail_url", None)
                else None
            ),
            original_url=url,
            source_id=str(getattr(media_info, "pk", "")),
            tags=[],
        )

    async def cleanup(self) -> None:
        self._insta_client = None
