from __future__ import annotations

from ..config import DownloaderConfig
from ..enums import DownloadProvider, Platform
from ..exceptions import ConfigurationError, UnsupportedPlatformError
from .base import AbstractDownloader

# Providers that only work with a specific platform.
_INSTAGRAM_ONLY_PROVIDERS = frozenset({
    DownloadProvider.SSSINSTAGRAM,
    DownloadProvider.SNAPINSTA,
    DownloadProvider.INSTAGRAPI,
})
_TIKTOK_ONLY_PROVIDERS = frozenset({
    DownloadProvider.SSSTIK,
})


class DownloaderFactory:
    """Creates the appropriate downloader based on detected platform and provider."""

    @staticmethod
    def create(platform: Platform, config: DownloaderConfig) -> AbstractDownloader:
        provider = config.provider

        # --- Platform-specific provider validation ---
        if provider in _INSTAGRAM_ONLY_PROVIDERS and platform != Platform.INSTAGRAM:
            raise ConfigurationError(
                f"Provider '{provider}' only supports Instagram, "
                f"but the detected platform is '{platform}'."
            )
        if provider in _TIKTOK_ONLY_PROVIDERS and platform != Platform.TIKTOK:
            raise ConfigurationError(
                f"Provider '{provider}' only supports TikTok, "
                f"but the detected platform is '{platform}'."
            )

        # --- Apify (any platform) ---
        if provider == DownloadProvider.APIFY:
            from .apify_downloader import ApifyDownloader

            if platform not in (Platform.YOUTUBE, Platform.TIKTOK, Platform.INSTAGRAM):
                raise UnsupportedPlatformError(
                    f"Apify provider does not support platform: {platform}"
                )
            return ApifyDownloader(config, platform=platform)

        # --- Instagram-specific providers (no fallback) ---
        if provider in _INSTAGRAM_ONLY_PROVIDERS:
            from .instagram_downloader import InstagramDownloader

            return InstagramDownloader(config, provider=provider)

        # --- TikTok-specific provider (no fallback) ---
        if provider == DownloadProvider.SSSTIK:
            from .tiktok_downloader import TikTokDownloader

            return TikTokDownloader(config)

        # --- Default: YTDLP provider (with fallback chains) ---
        from .instagram_downloader import InstagramDownloader
        from .tiktok_downloader import TikTokDownloader
        from .ytdlp_downloader import YtDlpDownloader

        match platform:
            case Platform.YOUTUBE:
                return YtDlpDownloader(config, platform=Platform.YOUTUBE)
            case Platform.TIKTOK:
                return TikTokDownloader(config)
            case Platform.INSTAGRAM:
                return InstagramDownloader(config)
            case _:
                raise UnsupportedPlatformError(
                    f"No downloader registered for platform: {platform}"
                )
