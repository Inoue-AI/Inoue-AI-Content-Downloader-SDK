class InoueDownloaderError(Exception):
    """Base exception for all SDK errors."""


class UnsupportedPlatformError(InoueDownloaderError):
    """URL does not match any supported platform."""


class DownloadError(InoueDownloaderError):
    """Failed to download content from the source platform."""


class YtDlpError(DownloadError):
    """yt-dlp specific download failure."""


class InstagramError(DownloadError):
    """Instagram-specific download failure."""


class InstagramAuthRequiredError(InstagramError):
    """Instagram content requires authentication but no credentials were provided."""


class ApifyError(DownloadError):
    """Apify-specific download failure."""


class ScraperError(DownloadError):
    """Web scraper fallback failure."""


class StorageError(InoueDownloaderError):
    """Failed to upload/save downloaded content."""


class S3UploadError(StorageError):
    """S3-specific upload failure."""


class ContentTooLargeError(InoueDownloaderError):
    """Downloaded content exceeds configured max_file_size_mb."""


class MetadataExtractionError(InoueDownloaderError):
    """Failed to extract metadata from the URL."""


class ConfigurationError(InoueDownloaderError):
    """Invalid SDK configuration."""


class RateLimitError(InoueDownloaderError):
    """Platform rate limit hit."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
