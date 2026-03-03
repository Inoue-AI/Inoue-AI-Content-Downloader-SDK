# SKILL.md — Inoue AI Content Downloader SDK

## What This SDK Does

Downloads social media content (videos, images, carousels) from YouTube, TikTok, and Instagram using a single URL, then uploads it to S3. Everything is async, everything uses Pydantic models. Users can choose between download providers (yt-dlp or Apify).

## Quick Start

```python
import asyncio
from inoue_downloader import InoueDownloader, DownloaderConfig, S3Config

async def main():
    config = DownloaderConfig(
        s3=S3Config(
            bucket_name="my-bucket",
            aws_access_key_id="AKID...",
            aws_secret_access_key="SECRET...",
            region_name="us-east-1",
        )
    )

    async with InoueDownloader(config) as downloader:
        result = await downloader.download("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        print(result.status)          # "success"
        print(result.metadata.title)  # "Me at the zoo"
        print(result.s3_urls)         # ["s3://my-bucket/youtube/jNQXAC9IVRw/..."]

asyncio.run(main())
```

### Using Apify Provider

```python
from inoue_downloader import (
    InoueDownloader, DownloaderConfig, DownloadProvider, ApifyConfig, S3Config
)

config = DownloaderConfig(
    provider=DownloadProvider.APIFY,
    apify=ApifyConfig(api_key="apify_api_..."),
    s3=S3Config(
        bucket_name="my-bucket",
        aws_access_key_id="YOUR_KEY",
        aws_secret_access_key="YOUR_SECRET",
    ),
)

async with InoueDownloader(config) as downloader:
    result = await downloader.download("https://www.tiktok.com/@user/video/123")
```

## Architecture

```
URL → detect_platform() → DownloaderFactory → Platform Downloader → temp dir
  → StorageBackend.upload() → S3 or Local → DownloadResult
```

### Provider Routing

```
DownloaderFactory.create(platform, config)
  ├─ config.provider == APIFY  → ApifyDownloader(platform)
  └─ config.provider == YTDLP
       ├─ YouTube   → YtDlpDownloader
       ├─ TikTok    → TikTokDownloader (ssstik.io scraper)
       └─ Instagram → InstagramDownloader (sssinstagram.com → snapinsta.to → instagrapi)
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `InoueDownloader` | `client.py` | Main public API. Async context manager. |
| `DownloaderConfig` | `config.py` | Pydantic config with provider, S3, Apify, Instagram creds, limits. |
| `detect_platform()` | `platform_detection.py` | URL → Platform enum via regex. |
| `DownloaderFactory` | `downloaders/factory.py` | Platform + Provider → concrete downloader. |
| `ApifyDownloader` | `downloaders/apify_downloader.py` | YouTube, TikTok, Instagram via Apify actors. |
| `YtDlpDownloader` | `downloaders/ytdlp_downloader.py` | YouTube only via yt-dlp. |
| `TikTokDownloader` | `downloaders/tiktok_downloader.py` | TikTok via ssstik.io scraper. |
| `InstagramDownloader` | `downloaders/instagram_downloader.py` | Instagram: sssinstagram.com → snapinsta.to → instagrapi fallback. |
| `SsstikScraper` | `scrapers/ssstik.py` | TikTok video download via ssstik.io. |
| `SssinstagramScraper` | `scrapers/sssinstagram.py` | Instagram download via sssinstagram.com (HMAC-signed API, HTTP/2). |
| `SnapinstaScraper` | `scrapers/snapinsta.py` | Instagram download via snapinsta.to (uses cloudscraper). |
| `S3StorageBackend` | `storage/s3_storage.py` | Async S3 upload via aioboto3. |
| `LocalStorageBackend` | `storage/local_storage.py` | Local filesystem fallback. |

### Design Patterns

- **Strategy Pattern** — `AbstractDownloader` base class with platform-specific implementations
- **Factory Pattern** — `DownloaderFactory.create(platform, config)` returns the right downloader based on provider
- **Async Context Manager** — `InoueDownloader` manages downloader lifecycle
- **Temp File Pipeline** — Download to tempdir → upload to S3 → cleanup tempdir
- **Session Management** — All HTTP requests go through managed `aiohttp.ClientSession` instances

## Public API Reference

### `InoueDownloader(config: DownloaderConfig)`

Main SDK client. Use as an async context manager.

#### Methods

- **`download(url, save_locally=None) → DownloadResult`** — Download content and upload to storage.
- **`download_many(urls, save_locally=None) → list[DownloadResult]`** — Download multiple URLs concurrently.
- **`extract_metadata(url) → ContentMetadata`** — Extract metadata without downloading.

### Configuration Models

#### `DownloaderConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `DownloadProvider` | `YTDLP` | Download provider selection |
| `s3` | `S3Config \| None` | `None` | S3 upload configuration |
| `local_output_dir` | `str \| None` | `None` | Default local save directory |
| `apify` | `ApifyConfig \| None` | `None` | Apify provider config (required if provider=APIFY) |
| `instagram` | `InstagramCredentials \| None` | `None` | Instagram auth (optional, yt-dlp provider) |
| `max_concurrent_downloads` | `int` | `3` | Max parallel downloads |
| `request_timeout` | `int` | `300` | Download timeout in seconds |
| `max_file_size_mb` | `int \| None` | `None` | Max file size limit |
| `preferred_video_quality` | `str` | `"best"` | yt-dlp format string |
| `temp_dir` | `str \| None` | `None` | Custom temp directory |
| `log_level` | `str` | `"INFO"` | Logging level |

**Validation**: Either `s3` or `local_output_dir` must be set. If provider is `APIFY`, `apify` must be set.

#### `S3Config`

| Field | Type | Default |
|-------|------|---------|
| `bucket_name` | `str` | required |
| `prefix` | `str` | `""` |
| `aws_access_key_id` | `SecretStr \| None` | `None` (uses IAM) |
| `aws_secret_access_key` | `SecretStr \| None` | `None` |
| `aws_session_token` | `SecretStr \| None` | `None` |
| `region_name` | `str` | `"us-east-1"` |
| `endpoint_url` | `str \| None` | `None` (for S3-compatible) |
| `storage_class` | `str` | `"STANDARD"` |

Users pass their own S3 credentials through this config.

#### `ApifyConfig`

| Field | Type | Default |
|-------|------|---------|
| `api_key` | `SecretStr` | required |
| `youtube_actor` | `str` | `"streamers/youtube-scraper"` |
| `tiktok_actor` | `str` | `"clockworks/free-tiktok-scraper"` |
| `instagram_actor` | `str` | `"apify/instagram-scraper"` |
| `timeout` | `int` | `300` |

#### `DownloadProvider` (enum)

| Value | Description |
|-------|-------------|
| `YTDLP` | Default. Uses yt-dlp with web scraper fallbacks. |
| `APIFY` | Uses Apify cloud actors via REST API. |

### Result Models

#### `DownloadResult`

| Field | Type | Description |
|-------|------|-------------|
| `status` | `DownloadStatus` | `"success"`, `"partial"`, or `"failed"` |
| `source_url` | `str` | Original URL |
| `platform` | `Platform` | Detected platform |
| `metadata` | `ContentMetadata` | Rich metadata |
| `files` | `list[DownloadedFile]` | Downloaded files |
| `elapsed_seconds` | `float` | Time taken |
| `error_message` | `str \| None` | Error details if failed |

Properties: `primary_file`, `s3_urls`

#### `ContentMetadata`

Title, description, author, duration, view/like counts, upload date, thumbnail URL, tags, source ID, and a platform-specific `extra` dict. When using Apify, `extra["provider"]` is set to `"apify"`.

### Exceptions

```
InoueDownloaderError
├── UnsupportedPlatformError
├── DownloadError
│   ├── YtDlpError
│   ├── ApifyError
│   └── InstagramError
│       └── InstagramAuthRequiredError
├── StorageError
│   └── S3UploadError
├── ContentTooLargeError
├── MetadataExtractionError
├── ConfigurationError
└── RateLimitError
```

## Adding a New Platform

1. Create `src/inoue_downloader/downloaders/new_platform_downloader.py`
2. Implement `AbstractDownloader` (methods: `extract_metadata`, `download`, optionally `cleanup`)
3. Add new value to `Platform` enum in `enums.py`
4. Register in `DownloaderFactory.create()` in `factory.py`
5. Add URL patterns to `_PLATFORM_PATTERNS` in `platform_detection.py`
6. Add tests

## Adding a New Provider

1. Add new value to `DownloadProvider` enum in `enums.py`
2. Add provider config model to `config.py`
3. Create the downloader in `downloaders/`
4. Route in `DownloaderFactory.create()` in `factory.py`
5. Add tests

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run unit tests
uv run pytest tests/unit/ -v

# Run e2e tests (requires internet)
uv run pytest tests/e2e/ -v -m e2e

# Run Apify e2e tests only
uv run pytest tests/e2e/test_apify_download.py -v -m e2e

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/
```

## Key Technical Decisions

1. **yt-dlp is YouTube-only** — yt-dlp is used exclusively for YouTube. All yt-dlp calls are wrapped in `asyncio.to_thread()` to avoid blocking the event loop.
2. **Platform-specific scrapers** — TikTok uses ssstik.io scraper, Instagram uses sssinstagram.com (primary) + snapinsta.to + instagrapi fallback. No yt-dlp dependency for TikTok/Instagram.
3. **Temp files, not memory** — yt-dlp requires disk output. We download to a temp directory, upload to S3, then clean up. Files are never loaded fully into memory.
4. **Instagram triple-fallback** — Try sssinstagram.com first (HMAC-signed API via HTTP/2, most reliable). If it fails, try snapinsta.to (cloudscraper for Cloudflare bypass). If that also fails, fall back to instagrapi (needs credentials). For guaranteed Instagram access, use the Apify provider.
5. **sssinstagram.com signing** — Uses HMAC-SHA256 with a key extracted from the site's obfuscated JS bundle. The key may change when the site updates; if requests start returning `invalid_request`, the key needs re-extraction.
6. **Pydantic SecretStr** — AWS credentials, Apify API keys, and Instagram passwords are stored as `SecretStr` to prevent accidental logging.
7. **Provider pattern** — `DownloadProvider` enum lets users choose between yt-dlp (local) and Apify (cloud) without changing their download code.
8. **Session management** — All HTTP requests (Apify API calls, media downloads) go through managed `aiohttp.ClientSession` instances that are created on first use and properly closed during cleanup.
9. **S3 credential pass-through** — Users provide their own S3 credentials via `S3Config`. The SDK never manages or stores credentials beyond what's passed in config.
10. **Cloudflare handling** — snapinsta.to uses `cloudscraper` library to bypass Cloudflare JS challenges. However, Cloudflare Turnstile CAPTCHA tokens cannot be automated headlessly. sssinstagram.com requires HTTP/2 (Cloudflare rejects HTTP/1.1 with captcha).
