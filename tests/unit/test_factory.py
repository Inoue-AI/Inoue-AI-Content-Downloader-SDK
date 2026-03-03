import pytest

from inoue_downloader.config import (
    DownloaderConfig,
    InstagramCredentials,
    S3Config,
)
from inoue_downloader.downloaders.factory import DownloaderFactory
from inoue_downloader.downloaders.instagram_downloader import InstagramDownloader
from inoue_downloader.downloaders.tiktok_downloader import TikTokDownloader
from inoue_downloader.downloaders.ytdlp_downloader import YtDlpDownloader
from inoue_downloader.enums import DownloadProvider, Platform
from inoue_downloader.exceptions import ConfigurationError


@pytest.fixture
def config() -> DownloaderConfig:
    return DownloaderConfig(s3=S3Config(bucket_name="test"))


class TestDownloaderFactory:
    # --- default YTDLP provider ---

    def test_youtube(self, config: DownloaderConfig) -> None:
        downloader = DownloaderFactory.create(Platform.YOUTUBE, config)
        assert isinstance(downloader, YtDlpDownloader)

    def test_tiktok(self, config: DownloaderConfig) -> None:
        downloader = DownloaderFactory.create(Platform.TIKTOK, config)
        assert isinstance(downloader, TikTokDownloader)

    def test_instagram(self, config: DownloaderConfig) -> None:
        downloader = DownloaderFactory.create(Platform.INSTAGRAM, config)
        assert isinstance(downloader, InstagramDownloader)
        assert downloader._provider is None  # auto mode

    # --- Explicit Instagram providers ---

    def test_sssinstagram_provider(self) -> None:
        cfg = DownloaderConfig(
            provider=DownloadProvider.SSSINSTAGRAM,
            s3=S3Config(bucket_name="test"),
        )
        dl = DownloaderFactory.create(Platform.INSTAGRAM, cfg)
        assert isinstance(dl, InstagramDownloader)
        assert dl._provider == DownloadProvider.SSSINSTAGRAM

    def test_snapinsta_provider(self) -> None:
        cfg = DownloaderConfig(
            provider=DownloadProvider.SNAPINSTA,
            s3=S3Config(bucket_name="test"),
        )
        dl = DownloaderFactory.create(Platform.INSTAGRAM, cfg)
        assert isinstance(dl, InstagramDownloader)
        assert dl._provider == DownloadProvider.SNAPINSTA

    def test_instagrapi_provider(self) -> None:
        cfg = DownloaderConfig(
            provider=DownloadProvider.INSTAGRAPI,
            s3=S3Config(bucket_name="test"),
            instagram=InstagramCredentials(username="u", password="p"),
        )
        dl = DownloaderFactory.create(Platform.INSTAGRAM, cfg)
        assert isinstance(dl, InstagramDownloader)
        assert dl._provider == DownloadProvider.INSTAGRAPI

    def test_ssstik_provider(self) -> None:
        cfg = DownloaderConfig(
            provider=DownloadProvider.SSSTIK,
            s3=S3Config(bucket_name="test"),
        )
        dl = DownloaderFactory.create(Platform.TIKTOK, cfg)
        assert isinstance(dl, TikTokDownloader)

    # --- Platform mismatch errors ---

    def test_instagram_provider_on_youtube_raises(self) -> None:
        cfg = DownloaderConfig(
            provider=DownloadProvider.SSSINSTAGRAM,
            s3=S3Config(bucket_name="test"),
        )
        with pytest.raises(ConfigurationError, match="only supports Instagram"):
            DownloaderFactory.create(Platform.YOUTUBE, cfg)

    def test_instagram_provider_on_tiktok_raises(self) -> None:
        cfg = DownloaderConfig(
            provider=DownloadProvider.SNAPINSTA,
            s3=S3Config(bucket_name="test"),
        )
        with pytest.raises(ConfigurationError, match="only supports Instagram"):
            DownloaderFactory.create(Platform.TIKTOK, cfg)

    def test_ssstik_provider_on_youtube_raises(self) -> None:
        cfg = DownloaderConfig(
            provider=DownloadProvider.SSSTIK,
            s3=S3Config(bucket_name="test"),
        )
        with pytest.raises(ConfigurationError, match="only supports TikTok"):
            DownloaderFactory.create(Platform.YOUTUBE, cfg)
