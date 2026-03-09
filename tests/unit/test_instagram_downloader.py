from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inoue_downloader.config import DownloaderConfig, InstagramCredentials, S3Config
from inoue_downloader.downloaders.instagram_downloader import InstagramDownloader
from inoue_downloader.enums import ContentType, DownloadProvider, Platform
from inoue_downloader.exceptions import (
    InstagramAuthRequiredError,
    ScraperError,
)


@pytest.fixture
def config_no_creds() -> DownloaderConfig:
    return DownloaderConfig(s3=S3Config(bucket_name="test"))


@pytest.fixture
def config_with_creds() -> DownloaderConfig:
    return DownloaderConfig(
        s3=S3Config(bucket_name="test"),
        instagram=InstagramCredentials(username="testuser", password="testpass"),
    )


# ======================================================================
# Auto mode (provider=None) — fallback chain
# ======================================================================


class TestAutoModeSssinstagram:
    """Auto mode: sssinstagram.com is tried first."""

    @pytest.mark.asyncio
    async def test_download_via_sssinstagram(
        self, config_no_creds: DownloaderConfig, tmp_path: Path
    ) -> None:
        downloader = InstagramDownloader(config_no_creds)

        video_file = tmp_path / "ABC123.mp4"
        video_file.write_bytes(b"fake instagram video")

        mock_metadata = MagicMock()
        mock_metadata.platform = Platform.INSTAGRAM

        with patch.object(
            downloader._sssinstagram,
            "download",
            new_callable=AsyncMock,
            return_value=(mock_metadata, [video_file]),
        ):
            metadata, files = await downloader.download("https://instagram.com/p/ABC123/", tmp_path)

        assert metadata.platform == Platform.INSTAGRAM
        assert len(files) == 1


class TestAutoModeSnapinstaFallback:
    """Auto mode: snapinsta.to is tried when sssinstagram fails."""

    @pytest.mark.asyncio
    async def test_fallback_to_snapinsta(
        self, config_no_creds: DownloaderConfig, tmp_path: Path
    ) -> None:
        downloader = InstagramDownloader(config_no_creds)

        video_file = tmp_path / "ABC123.mp4"
        video_file.write_bytes(b"fake instagram video")

        mock_metadata = MagicMock()
        mock_metadata.platform = Platform.INSTAGRAM

        with (
            patch.object(
                downloader._sssinstagram,
                "download",
                new_callable=AsyncMock,
                side_effect=ScraperError("sssinstagram.com failed"),
            ),
            patch.object(
                downloader._snapinsta,
                "download",
                new_callable=AsyncMock,
                return_value=(mock_metadata, [video_file]),
            ),
        ):
            metadata, files = await downloader.download("https://instagram.com/p/ABC123/", tmp_path)

        assert metadata.platform == Platform.INSTAGRAM
        assert len(files) == 1


class TestAutoModeInstagrapi:
    """Auto mode: instagrapi is last resort when both scrapers fail."""

    @pytest.mark.asyncio
    async def test_fallback_to_instagrapi_no_creds(
        self, config_no_creds: DownloaderConfig, tmp_path: Path
    ) -> None:
        downloader = InstagramDownloader(config_no_creds)

        with (
            patch.object(
                downloader._sssinstagram,
                "download",
                new_callable=AsyncMock,
                side_effect=ScraperError("sssinstagram.com failed"),
            ),
            patch.object(
                downloader._snapinsta,
                "download",
                new_callable=AsyncMock,
                side_effect=ScraperError("snapinsta.to failed"),
            ),
            pytest.raises(InstagramAuthRequiredError),
        ):
            await downloader.download("https://instagram.com/p/ABC123/", tmp_path)

    @pytest.mark.asyncio
    async def test_fallback_to_instagrapi_with_creds(
        self, config_with_creds: DownloaderConfig, tmp_path: Path
    ) -> None:
        downloader = InstagramDownloader(config_with_creds)

        mock_media = MagicMock()
        mock_media.media_type = 2
        mock_media.pk = 12345
        mock_media.caption_text = "Test caption"
        mock_media.video_duration = 15.0
        mock_media.view_count = 100
        mock_media.like_count = 10
        mock_media.taken_at = None
        mock_media.thumbnail_url = None
        mock_media.user = MagicMock(username="testuser", pk=999)

        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        with (
            patch.object(
                downloader._sssinstagram,
                "download",
                new_callable=AsyncMock,
                side_effect=ScraperError("sssinstagram.com failed"),
            ),
            patch.object(
                downloader._snapinsta,
                "download",
                new_callable=AsyncMock,
                side_effect=ScraperError("snapinsta.to failed"),
            ),
            patch.object(
                downloader,
                "_ensure_instagrapi_client",
                new_callable=AsyncMock,
            ) as mock_ensure,
        ):
            mock_client = MagicMock()
            mock_client.media_pk_from_url = MagicMock(return_value=12345)
            mock_client.media_info = MagicMock(return_value=mock_media)
            mock_client.video_download = MagicMock(return_value=str(video_path))
            mock_ensure.return_value = mock_client

            metadata, files = await downloader.download("https://instagram.com/p/ABC123/", tmp_path)

        assert metadata.platform == Platform.INSTAGRAM
        assert metadata.content_type == ContentType.VIDEO
        assert len(files) == 1


# ======================================================================
# Explicit provider mode — NO fallback
# ======================================================================


class TestExplicitSssinstagramProvider:
    """provider=SSSINSTAGRAM: only sssinstagram.com, no fallback."""

    @pytest.mark.asyncio
    async def test_download_success(
        self, config_no_creds: DownloaderConfig, tmp_path: Path
    ) -> None:
        downloader = InstagramDownloader(config_no_creds, provider=DownloadProvider.SSSINSTAGRAM)

        video_file = tmp_path / "ABC123.mp4"
        video_file.write_bytes(b"video data")

        mock_metadata = MagicMock()
        mock_metadata.platform = Platform.INSTAGRAM

        with patch.object(
            downloader._sssinstagram,
            "download",
            new_callable=AsyncMock,
            return_value=(mock_metadata, [video_file]),
        ):
            metadata, files = await downloader.download(
                "https://instagram.com/reel/ABC123/", tmp_path
            )

        assert metadata.platform == Platform.INSTAGRAM
        assert len(files) == 1

    @pytest.mark.asyncio
    async def test_download_failure_no_fallback(
        self, config_no_creds: DownloaderConfig, tmp_path: Path
    ) -> None:
        """When sssinstagram fails with explicit provider, error propagates — no fallback."""
        downloader = InstagramDownloader(config_no_creds, provider=DownloadProvider.SSSINSTAGRAM)

        with (
            patch.object(
                downloader._sssinstagram,
                "download",
                new_callable=AsyncMock,
                side_effect=ScraperError("sssinstagram.com API error"),
            ),
            pytest.raises(ScraperError, match=r"sssinstagram\.com API error"),
        ):
            await downloader.download("https://instagram.com/p/ABC123/", tmp_path)


class TestExplicitSnapinstaProvider:
    """provider=SNAPINSTA: only snapinsta.to, no fallback."""

    @pytest.mark.asyncio
    async def test_download_success(
        self, config_no_creds: DownloaderConfig, tmp_path: Path
    ) -> None:
        downloader = InstagramDownloader(config_no_creds, provider=DownloadProvider.SNAPINSTA)

        video_file = tmp_path / "ABC123.mp4"
        video_file.write_bytes(b"video data")

        mock_metadata = MagicMock()
        mock_metadata.platform = Platform.INSTAGRAM

        with patch.object(
            downloader._snapinsta,
            "download",
            new_callable=AsyncMock,
            return_value=(mock_metadata, [video_file]),
        ):
            metadata, _files = await downloader.download(
                "https://instagram.com/p/ABC123/", tmp_path
            )

        assert metadata.platform == Platform.INSTAGRAM

    @pytest.mark.asyncio
    async def test_download_failure_no_fallback(
        self, config_no_creds: DownloaderConfig, tmp_path: Path
    ) -> None:
        downloader = InstagramDownloader(config_no_creds, provider=DownloadProvider.SNAPINSTA)

        with (
            patch.object(
                downloader._snapinsta,
                "download",
                new_callable=AsyncMock,
                side_effect=ScraperError("snapinsta.to blocked"),
            ),
            pytest.raises(ScraperError, match=r"snapinsta\.to blocked"),
        ):
            await downloader.download("https://instagram.com/p/ABC123/", tmp_path)


class TestExplicitInstagrapiProvider:
    """provider=INSTAGRAPI: only instagrapi, no fallback."""

    @pytest.mark.asyncio
    async def test_download_with_creds(
        self, config_with_creds: DownloaderConfig, tmp_path: Path
    ) -> None:
        downloader = InstagramDownloader(config_with_creds, provider=DownloadProvider.INSTAGRAPI)

        mock_media = MagicMock()
        mock_media.media_type = 2
        mock_media.pk = 12345
        mock_media.caption_text = "Test"
        mock_media.video_duration = 10.0
        mock_media.view_count = 50
        mock_media.like_count = 5
        mock_media.taken_at = None
        mock_media.thumbnail_url = None
        mock_media.user = MagicMock(username="u", pk=1)

        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        with patch.object(
            downloader,
            "_ensure_instagrapi_client",
            new_callable=AsyncMock,
        ) as mock_ensure:
            mock_client = MagicMock()
            mock_client.media_pk_from_url = MagicMock(return_value=12345)
            mock_client.media_info = MagicMock(return_value=mock_media)
            mock_client.video_download = MagicMock(return_value=str(video_path))
            mock_ensure.return_value = mock_client

            metadata, files = await downloader.download("https://instagram.com/p/ABC123/", tmp_path)

        assert metadata.content_type == ContentType.VIDEO
        assert len(files) == 1


# ======================================================================
# Metadata helpers
# ======================================================================


class TestMediaToMetadata:
    def test_video_metadata(self) -> None:
        mock_media = MagicMock()
        mock_media.media_type = 2
        mock_media.pk = 12345
        mock_media.caption_text = "A cool video"
        mock_media.video_duration = 30.0
        mock_media.view_count = 500
        mock_media.like_count = 25
        mock_media.taken_at = None
        mock_media.thumbnail_url = "https://example.com/thumb.jpg"
        mock_media.user = MagicMock(username="creator", pk=42)

        meta = InstagramDownloader._media_to_metadata(mock_media, "https://instagram.com/reel/XYZ/")
        assert meta.platform == Platform.INSTAGRAM
        assert meta.content_type == ContentType.VIDEO
        assert meta.author == "creator"

    def test_carousel_metadata(self) -> None:
        mock_media = MagicMock()
        mock_media.media_type = 8
        mock_media.pk = 99999
        mock_media.caption_text = None
        mock_media.video_duration = None
        mock_media.view_count = None
        mock_media.like_count = None
        mock_media.taken_at = None
        mock_media.thumbnail_url = None
        mock_media.user = None

        meta = InstagramDownloader._media_to_metadata(mock_media, "https://instagram.com/p/ABC/")
        assert meta.content_type == ContentType.CAROUSEL
        assert meta.author is None
        assert meta.title is None

    def test_image_metadata(self) -> None:
        mock_media = MagicMock()
        mock_media.media_type = 1
        mock_media.pk = 11111
        mock_media.caption_text = "Photo post"
        mock_media.video_duration = None
        mock_media.view_count = None
        mock_media.like_count = 5
        mock_media.taken_at = None
        mock_media.thumbnail_url = None
        mock_media.user = MagicMock(username="photographer", pk=7)

        meta = InstagramDownloader._media_to_metadata(mock_media, "https://instagram.com/p/IMG/")
        assert meta.content_type == ContentType.IMAGE
