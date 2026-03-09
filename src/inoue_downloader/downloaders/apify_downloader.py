from __future__ import annotations

import contextlib
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from ..config import ApifyConfig, DownloaderConfig
from ..enums import ContentType, Platform
from ..exceptions import ApifyError
from ..models import ContentMetadata
from .base import AbstractDownloader

logger = logging.getLogger(__name__)

_APIFY_BASE = "https://api.apify.com/v2"


def _last_path_segment(url: str) -> str:
    """Extract the last non-empty path segment from a URL."""
    segments = [s for s in url.rstrip("/").split("/") if s]
    return segments[-1] if segments else "unknown"


class ApifyDownloader(AbstractDownloader):
    """Downloader that uses Apify actors for YouTube, TikTok, and Instagram."""

    def __init__(self, config: DownloaderConfig, platform: Platform) -> None:
        self._config = config
        self._platform = platform
        if config.apify is None:
            raise ApifyError("ApifyConfig is required for ApifyDownloader")
        self._apify: ApifyConfig = config.apify
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._apify.timeout + 60)
            self._session = aiohttp.ClientSession(
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
        return self._session

    def _get_actor_id(self) -> str:
        match self._platform:
            case Platform.YOUTUBE:
                return self._apify.youtube_actor
            case Platform.TIKTOK:
                return self._apify.tiktok_actor
            case Platform.INSTAGRAM:
                return self._apify.instagram_actor
            case _:
                raise ApifyError(f"Unsupported platform for Apify: {self._platform}")

    def _build_actor_input(self, url: str) -> dict[str, object]:
        match self._platform:
            case Platform.YOUTUBE:
                return {
                    "startUrls": [{"url": url}],
                    "maxResults": 1,
                    "maxResultStreams": 0,
                    "maxResultsShorts": 0,
                }
            case Platform.TIKTOK:
                return {
                    "postURLs": [url],
                }
            case Platform.INSTAGRAM:
                return {
                    "directUrls": [url],
                    "resultsLimit": 1,
                    "resultsType": "posts",
                }
            case _:
                raise ApifyError(f"Unsupported platform for Apify: {self._platform}")

    async def _run_actor(self, url: str) -> list[dict[str, object]]:
        """Run an Apify actor synchronously and return dataset items."""
        session = await self._get_session()
        actor_id = self._get_actor_id()
        actor_input = self._build_actor_input(url)
        token = self._apify.api_key.get_secret_value()

        # Apify API requires ~ separator (not /) in actor IDs within URL path
        api_actor_id = actor_id.replace("/", "~")
        endpoint = f"{_APIFY_BASE}/acts/{api_actor_id}/run-sync-get-dataset-items"
        params = {"token": token, "timeout": str(self._apify.timeout)}

        logger.info("Running Apify actor %s for %s URL: %s", actor_id, self._platform, url)

        async with session.post(endpoint, json=actor_input, params=params) as resp:
            if resp.status == 408:
                raise ApifyError(f"Apify actor {actor_id} timed out after {self._apify.timeout}s")
            if resp.status == 400:
                body = await resp.text()
                raise ApifyError(f"Apify actor {actor_id} run failed: {body}")
            if resp.status not in (200, 201):
                body = await resp.text()
                raise ApifyError(f"Apify API returned status {resp.status}: {body[:500]}")
            items: list[dict[str, object]] = await resp.json()

        if not items:
            raise ApifyError(f"Apify actor {actor_id} returned no results for URL: {url}")

        logger.info("Apify actor returned %d result(s)", len(items))
        return items

    async def extract_metadata(self, url: str) -> ContentMetadata:
        items = await self._run_actor(url)
        return self._parse_metadata(items[0], url)

    async def download(self, url: str, output_dir: Path) -> tuple[ContentMetadata, list[Path]]:
        items = await self._run_actor(url)
        item = items[0]

        # Check if the actor returned an error (e.g. restricted access)
        item_error = item.get("error")
        if isinstance(item_error, str) and item_error:
            error_desc = item.get("errorDescription", "")
            raise ApifyError(f"Apify actor returned error for {url}: {item_error} - {error_desc}")

        metadata = self._parse_metadata(item, url)
        media_urls = self._extract_media_urls(item)

        if not media_urls:
            raise ApifyError(f"No downloadable media URLs found in Apify results for: {url}")

        session = await self._get_session()
        downloaded: list[Path] = []

        for i, (media_url, media_type) in enumerate(media_urls):
            try:
                async with session.get(media_url) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Failed to download media %d from %s: HTTP %s",
                            i,
                            media_url[:80],
                            resp.status,
                        )
                        continue

                    content = await resp.read()
                    if not content:
                        logger.warning("Empty content from media URL %d", i)
                        continue

                    ext = _guess_extension(media_url, media_type)
                    suffix = f"_{i}" if len(media_urls) > 1 else ""
                    filename = f"{metadata.source_id}{suffix}{ext}"
                    out_path = output_dir / filename
                    out_path.write_bytes(content)
                    downloaded.append(out_path)
            except aiohttp.ClientError as e:
                logger.warning("Network error downloading media %d: %s", i, e)
                continue

        if not downloaded:
            raise ApifyError("Failed to download any media files from Apify results")

        logger.info("Downloaded %d file(s) via Apify for %s", len(downloaded), self._platform)
        return metadata, downloaded

    def _parse_metadata(self, item: dict[str, object], url: str) -> ContentMetadata:
        match self._platform:
            case Platform.YOUTUBE:
                return self._parse_youtube_metadata(item, url)
            case Platform.TIKTOK:
                return self._parse_tiktok_metadata(item, url)
            case Platform.INSTAGRAM:
                return self._parse_instagram_metadata(item, url)
            case _:
                raise ApifyError(f"Unsupported platform: {self._platform}")

    def _parse_youtube_metadata(self, item: dict[str, object], url: str) -> ContentMetadata:
        source_id = _str(item.get("id", ""))
        if not source_id:
            match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
            source_id = match.group(1) if match else _last_path_segment(url)

        upload_date: datetime | None = None
        date_raw = item.get("date")
        if isinstance(date_raw, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d", "%Y%m%d"):
                try:
                    upload_date = datetime.strptime(date_raw, fmt).replace(tzinfo=UTC)
                    break
                except ValueError:
                    continue

        duration = item.get("duration")
        duration_secs: float | None = None
        if isinstance(duration, int | float):
            duration_secs = float(duration)
        elif isinstance(duration, str):
            duration_secs = _parse_duration_string(duration)

        return ContentMetadata(
            platform=Platform.YOUTUBE,
            content_type=ContentType.VIDEO,
            title=_str(item.get("title")),
            description=_str(item.get("description")),
            author=_str(item.get("channelName") or item.get("channel")),
            author_id=_str(item.get("channelUrl") or item.get("channelId")),
            duration_seconds=duration_secs,
            view_count=_int(item.get("viewCount") or item.get("views")),
            like_count=_int(item.get("likes")),
            upload_date=upload_date,
            thumbnail_url=_str(item.get("thumbnailUrl") or item.get("thumbnail")),
            original_url=url,
            source_id=source_id,
            tags=[],
            extra={"provider": "apify", "actor": self._apify.youtube_actor},
        )

    def _parse_tiktok_metadata(self, item: dict[str, object], url: str) -> ContentMetadata:
        source_id = _str(item.get("id", ""))
        if not source_id:
            match = re.search(r"/video/(\d+)", url)
            source_id = match.group(1) if match else _last_path_segment(url)

        create_time = item.get("createTime") or item.get("createTimeISO")
        upload_date: datetime | None = None
        if isinstance(create_time, int | float):
            upload_date = datetime.fromtimestamp(int(create_time), tz=UTC)
        elif isinstance(create_time, str):
            with contextlib.suppress(ValueError):
                upload_date = datetime.fromisoformat(create_time.replace("Z", "+00:00"))

        author_meta = item.get("authorMeta")
        author_name: str | None = None
        author_id: str | None = None
        if isinstance(author_meta, dict):
            author_name = _str(author_meta.get("name") or author_meta.get("nickName"))
            author_id = _str(author_meta.get("id"))

        video_meta = item.get("videoMeta")
        duration_secs: float | None = None
        if isinstance(video_meta, dict):
            dur = video_meta.get("duration")
            if isinstance(dur, int | float):
                duration_secs = float(dur)

        return ContentMetadata(
            platform=Platform.TIKTOK,
            content_type=ContentType.VIDEO,
            title=_str(item.get("text")),
            author=author_name,
            author_id=author_id,
            duration_seconds=duration_secs,
            view_count=_int(item.get("playCount")),
            like_count=_int(item.get("diggCount") or item.get("likesCount")),
            upload_date=upload_date,
            thumbnail_url=_str(
                covers.get("default") if isinstance((covers := item.get("covers")), dict) else None
            ),
            original_url=url,
            source_id=source_id,
            tags=_extract_hashtag_names(item.get("hashtags")),
            extra={"provider": "apify", "actor": self._apify.tiktok_actor},
        )

    def _parse_instagram_metadata(self, item: dict[str, object], url: str) -> ContentMetadata:
        source_id = _str(item.get("id") or item.get("shortCode", ""))
        if not source_id:
            match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
            source_id = match.group(1) if match else _last_path_segment(url)

        # Determine content type
        ig_type = _str(item.get("type", ""))
        if ig_type and "video" in ig_type.lower():
            content_type = ContentType.VIDEO
        elif ig_type and "sidecar" in ig_type.lower():
            content_type = ContentType.CAROUSEL
        elif item.get("videoUrl"):
            content_type = ContentType.VIDEO
        else:
            content_type = ContentType.IMAGE

        timestamp = item.get("timestamp")
        upload_date: datetime | None = None
        if isinstance(timestamp, str):
            with contextlib.suppress(ValueError):
                upload_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif isinstance(timestamp, int | float):
            upload_date = datetime.fromtimestamp(int(timestamp), tz=UTC)

        return ContentMetadata(
            platform=Platform.INSTAGRAM,
            content_type=content_type,
            title=(_str(item.get("caption")) or "")[:100] or None,
            description=_str(item.get("caption")),
            author=_str(item.get("ownerUsername")),
            author_id=_str(item.get("ownerId")),
            view_count=_int(item.get("videoViewCount")),
            like_count=_int(item.get("likesCount")),
            upload_date=upload_date,
            thumbnail_url=_str(item.get("displayUrl")),
            original_url=url,
            source_id=source_id,
            tags=_extract_hashtag_strings(item.get("hashtags")),
            extra={"provider": "apify", "actor": self._apify.instagram_actor},
        )

    def _extract_media_urls(self, item: dict[str, object]) -> list[tuple[str, str]]:
        """Extract downloadable media URLs from an Apify result item.

        Returns a list of (url, media_type) tuples.
        """
        urls: list[tuple[str, str]] = []

        match self._platform:
            case Platform.YOUTUBE:
                urls.extend(self._extract_youtube_media(item))
            case Platform.TIKTOK:
                urls.extend(self._extract_tiktok_media(item))
            case Platform.INSTAGRAM:
                urls.extend(self._extract_instagram_media(item))

        return urls

    @staticmethod
    def _extract_youtube_media(item: dict[str, object]) -> list[tuple[str, str]]:
        urls: list[tuple[str, str]] = []

        # Some actors provide a direct download URL
        for key in ("downloadUrl", "videoUrl", "mediaUrl", "url"):
            val = item.get(key)
            if isinstance(val, str) and val.startswith("http"):
                urls.append((val, "video"))
                break

        # Some actors store in mediaUrls array
        media_urls = item.get("mediaUrls")
        if isinstance(media_urls, list) and not urls:
            for mu in media_urls:
                if isinstance(mu, str) and mu.startswith("http"):
                    urls.append((mu, "video"))

        return urls

    @staticmethod
    def _extract_tiktok_media(item: dict[str, object]) -> list[tuple[str, str]]:
        urls: list[tuple[str, str]] = []

        # mediaUrls is the primary field for TikTok scrapers
        media_urls = item.get("mediaUrls")
        if isinstance(media_urls, list):
            for mu in media_urls:
                if isinstance(mu, str) and mu.startswith("http"):
                    urls.append((mu, "video"))

        # Fallback to videoUrl or webVideoUrl
        if not urls:
            for key in ("videoUrl", "webVideoUrl", "videoUrlNoWaterMark"):
                val = item.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    urls.append((val, "video"))
                    break

        return urls

    @staticmethod
    def _extract_instagram_media(item: dict[str, object]) -> list[tuple[str, str]]:
        urls: list[tuple[str, str]] = []

        # Video posts
        video_url = item.get("videoUrl")
        if isinstance(video_url, str) and video_url.startswith("http"):
            urls.append((video_url, "video"))

        # Image posts / carousel images
        display_url = item.get("displayUrl")
        if isinstance(display_url, str) and display_url.startswith("http") and not urls:
            urls.append((display_url, "image"))

        # Carousel children (sidecar posts)
        children = item.get("childPosts") or item.get("images") or item.get("sidecarPosts")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    cv = child.get("videoUrl")
                    if isinstance(cv, str) and cv.startswith("http"):
                        urls.append((cv, "video"))
                    else:
                        cd = child.get("displayUrl") or child.get("url")
                        if isinstance(cd, str) and cd.startswith("http"):
                            urls.append((cd, "image"))
                elif isinstance(child, str) and child.startswith("http"):
                    urls.append((child, "image"))

        return urls

    async def cleanup(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


def _str(val: object) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val if val else None
    return str(val) if val else None


def _int(val: object) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val.replace(",", ""))
        except ValueError:
            return None
    return None


def _extract_hashtag_names(raw: object) -> list[str]:
    """Extract hashtag name strings from a list of dicts (TikTok format)."""
    if not isinstance(raw, list):
        return []
    return [_str(h.get("name")) or "" for h in raw if isinstance(h, dict) and h.get("name")]


def _extract_hashtag_strings(raw: object) -> list[str]:
    """Extract plain string hashtags from a list (Instagram format)."""
    if not isinstance(raw, list):
        return []
    return [_str(h) or "" for h in raw if isinstance(h, str)]


def _parse_duration_string(s: str) -> float | None:
    """Parse duration strings like '5:23' or '1:02:30' into seconds."""
    parts = s.strip().split(":")
    try:
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None
    return None


def _guess_extension(url: str, media_type: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if "." in path.split("/")[-1]:
        ext = "." + path.split("/")[-1].rsplit(".", 1)[-1].split("?")[0]
        if len(ext) <= 5:
            return ext
    return ".mp4" if media_type == "video" else ".jpg"
