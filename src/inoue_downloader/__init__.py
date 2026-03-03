"""Inoue AI Content Downloader SDK - download social media content to S3."""

from .client import InoueDownloader
from .config import ApifyConfig, DownloaderConfig, InstagramCredentials, ProxyConfig, S3Config
from .enums import ContentType, DownloadProvider, DownloadStatus, Platform
from .exceptions import (
    ApifyError,
    ConfigurationError,
    ContentTooLargeError,
    DownloadError,
    InoueDownloaderError,
    InstagramAuthRequiredError,
    InstagramError,
    MetadataExtractionError,
    RateLimitError,
    S3UploadError,
    ScraperError,
    StorageError,
    UnsupportedPlatformError,
    YtDlpError,
)
from .models import ContentMetadata, DownloadedFile, DownloadResult

__all__ = [
    "ApifyConfig",
    "ApifyError",
    "ConfigurationError",
    "ContentMetadata",
    "ContentTooLargeError",
    "ContentType",
    "DownloadError",
    "DownloadProvider",
    "DownloadResult",
    "DownloadStatus",
    "DownloadedFile",
    "DownloaderConfig",
    "InoueDownloader",
    "InoueDownloaderError",
    "InstagramAuthRequiredError",
    "InstagramCredentials",
    "InstagramError",
    "MetadataExtractionError",
    "Platform",
    "ProxyConfig",
    "RateLimitError",
    "S3Config",
    "S3UploadError",
    "ScraperError",
    "StorageError",
    "UnsupportedPlatformError",
    "YtDlpError",
]

__version__ = "0.1.0"
