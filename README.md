# Inoue AI Content Downloader SDK

Async Python SDK for downloading social-media content (YouTube, TikTok, Instagram) with pluggable storage backends (S3, local filesystem) and explicit provider selection.

Built on `asyncio`, Pydantic v2, and a strategy/factory architecture that routes each URL to the correct platform downloader and scraper chain.

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [Provider System](#provider-system)
- [Platform Details](#platform-details)
- [Storage Backends](#storage-backends)
- [Data Models](#data-models)
- [Exception Hierarchy](#exception-hierarchy)
- [Usage Examples](#usage-examples)
- [Project Structure](#project-structure)
- [Development](#development)
- [License](#license)

---

## Features

- **Auto-detection** — resolves YouTube, TikTok, and Instagram URLs via regex-based platform detection
- **Pluggable providers** — choose a specific download backend per request or let the SDK pick the best one with automatic fallback
- **Fully async** — all I/O (HTTP, S3, filesystem) is non-blocking; blocking libraries (`yt-dlp`, `instagrapi`) are wrapped in `asyncio.to_thread()`
- **HTTP/2 + TLS fingerprinting** — Instagram scrapers use [noble-tls](https://github.com/AIO-SUSPENDED/noble-tls) with Chrome 131 TLS profiles to bypass Cloudflare
- **Pydantic v2 models** — typed, validated configuration (`DownloaderConfig`), metadata (`ContentMetadata`), and results (`DownloadResult`)
- **Dual storage** — upload to S3 (via `aioboto3`) or save to local disk; supports S3-compatible stores (MinIO, Cloudflare R2, DigitalOcean Spaces)
- **Batch downloads** — `download_many()` runs URLs concurrently, bounded by a configurable semaphore (`max_concurrent_downloads`)
- **Metadata-only extraction** — `extract_metadata()` returns structured metadata without downloading the media
- **Proxy support** — HTTP/HTTPS proxies propagated to all scrapers, `yt-dlp`, and `noble-tls` sessions

---

## Architecture Overview

```
                         InoueDownloader (client.py)
                                   │
                          detect_platform(url)
                                   │
                     DownloaderFactory.create(platform, config)
                        ┌──────────┼──────────┐
                        │          │          │
                   YtDlpDL    TikTokDL   InstagramDL
                   (YouTube)  (TikTok)   (Instagram)
                        │          │          │
                        │     SsstikScraper   ├── SssinstagramScraper  (primary)
                        │                     ├── SnapinstaScraper     (fallback)
                        │                     └── instagrapi Client    (auth fallback)
                        │
                   yt-dlp subprocess
                                   │
                     ┌─────────────┴─────────────┐
                     │                           │
              S3StorageBackend          LocalStorageBackend
              (aioboto3 → S3)           (shutil.copy2 → disk)
```

**Request lifecycle:**

1. `InoueDownloader.download(url)` calls `detect_platform(url)` to resolve the `Platform` enum.
2. `DownloaderFactory.create()` routes to the correct `AbstractDownloader` subclass based on `Platform` + `DownloadProvider`.
3. The downloader writes media files into an `AsyncTempDir`.
4. Each file is uploaded to the configured `StorageBackend` (S3 or local).
5. Temp files are cleaned up; a `DownloadResult` is returned.

---

## Installation

```bash
pip install inoue-ai-content-downloader
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add inoue-ai-content-downloader
```

### System requirements

- Python 3.11+
- `ffmpeg` on `$PATH` (required by `yt-dlp` for video merging)

### Optional: instagrapi

`instagrapi` is included as a dependency for Instagram authenticated downloads. If you only use the web scrapers (`SSSINSTAGRAM`, `SNAPINSTA`), it will never be imported at runtime — it is lazily loaded only when the `INSTAGRAPI` provider is selected or when the fallback chain reaches it.

---

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
        result = await downloader.download(
            "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        )
        print(result.status)          # "success"
        print(result.metadata.title)  # "Me at the zoo"
        print(result.s3_urls)         # ["s3://my-bucket/youtube/jNQXAC9IVRw/..."]

asyncio.run(main())
```

---

## Configuration Reference

All configuration uses Pydantic v2 `BaseModel` classes with validation.

### `DownloaderConfig`

Main configuration object. At least one of `s3` or `local_output_dir` must be set.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `DownloadProvider` | `"ytdlp"` | Download backend to use (see [Provider System](#provider-system)) |
| `s3` | `S3Config \| None` | `None` | S3 upload configuration |
| `local_output_dir` | `str \| None` | `None` | Local filesystem output directory |
| `instagram` | `InstagramCredentials \| None` | `None` | Instagram authentication credentials |
| `apify` | `ApifyConfig \| None` | `None` | Apify cloud actor configuration |
| `proxy` | `ProxyConfig \| None` | `None` | HTTP/HTTPS proxy settings |
| `max_concurrent_downloads` | `int` | `3` | Semaphore limit for `download_many()` (1-20) |
| `request_timeout` | `int` | `300` | Global request timeout in seconds (>= 10) |
| `max_file_size_mb` | `int \| None` | `None` | Maximum file size; raises `ContentTooLargeError` if exceeded |
| `preferred_video_quality` | `str` | `"best"` | yt-dlp format string (`"best"`, `"worst"`, `"bestvideo+bestaudio"`, etc.) |
| `temp_dir` | `str \| None` | `None` | Custom temp directory for intermediate downloads |
| `log_level` | `str` | `"INFO"` | Logging level |

**Validators:**

- `provider=APIFY` requires `apify` to be set
- `provider=INSTAGRAPI` requires `instagram` to be set
- Either `s3` or `local_output_dir` must be provided

### `S3Config`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `bucket_name` | `str` | *required* | S3 bucket name |
| `prefix` | `str` | `""` | Key prefix for all uploads |
| `aws_access_key_id` | `SecretStr \| None` | `None` | AWS access key (or use IAM role) |
| `aws_secret_access_key` | `SecretStr \| None` | `None` | AWS secret key |
| `aws_session_token` | `SecretStr \| None` | `None` | AWS session token |
| `region_name` | `str` | `"us-east-1"` | AWS region |
| `endpoint_url` | `str \| None` | `None` | Custom endpoint for S3-compatible stores |
| `storage_class` | `str` | `"STANDARD"` | S3 storage class |

### `InstagramCredentials`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `username` | `str` | *required* | Instagram username |
| `password` | `SecretStr` | *required* | Instagram password |
| `two_factor_seed` | `str \| None` | `None` | TOTP seed for 2FA |
| `session_file_path` | `str \| None` | `None` | Path to persist/restore instagrapi session |

### `ApifyConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `api_key` | `SecretStr` | *required* | Apify API token |
| `youtube_actor` | `str` | `"streamers/youtube-scraper"` | Apify actor ID for YouTube |
| `tiktok_actor` | `str` | `"clockworks/free-tiktok-scraper"` | Apify actor ID for TikTok |
| `instagram_actor` | `str` | `"apify/instagram-scraper"` | Apify actor ID for Instagram |
| `timeout` | `int` | `300` | Actor execution timeout in seconds (>= 10) |

### `ProxyConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `http` | `str \| None` | `None` | HTTP proxy URL |
| `https` | `str \| None` | `None` | HTTPS proxy URL (preferred by scrapers) |

---

## Provider System

The `DownloadProvider` enum controls which backend handles the download. Setting a specific provider bypasses all fallback logic — errors propagate directly.

### Provider routing

| Provider | Platforms | Backend | Fallback | Requirements |
|----------|-----------|---------|----------|-------------|
| `YTDLP` (default) | YouTube | yt-dlp | None | `ffmpeg` on PATH |
| `YTDLP` (default) | TikTok | ssstik.io scraper | None | — |
| `YTDLP` (default) | Instagram | sssinstagram.com -> snapinsta.to -> instagrapi | Three-level chain | Credentials for instagrapi |
| `SSSINSTAGRAM` | Instagram only | sssinstagram.com | None (error propagates) | — |
| `SNAPINSTA` | Instagram only | snapinsta.to | None (error propagates) | — |
| `INSTAGRAPI` | Instagram only | instagrapi | None (error propagates) | `InstagramCredentials` |
| `SSSTIK` | TikTok only | ssstik.io | None (error propagates) | — |
| `APIFY` | All platforms | Apify cloud actors | None (error propagates) | `ApifyConfig` |

**Platform-specific provider validation:** Using an Instagram-only provider (e.g., `SSSINSTAGRAM`) with a YouTube URL raises `ConfigurationError` at factory creation time.

### Explicit provider example

```python
from inoue_downloader import DownloaderConfig, DownloadProvider

# Force sssinstagram.com only — no fallback to snapinsta or instagrapi
config = DownloaderConfig(
    provider=DownloadProvider.SSSINSTAGRAM,
    local_output_dir="/tmp/downloads",
)
```

---

## Platform Details

### YouTube

**Downloader:** `YtDlpDownloader`
**Backend:** `yt-dlp` (called via `asyncio.to_thread()`)

- Supports: `youtube.com/watch`, `youtu.be/`, `youtube.com/shorts/`, `youtube.com/embed/`, `m.youtube.com/`
- Video quality controlled by `preferred_video_quality` (any valid yt-dlp format string)
- Output format forced to `mp4` via `merge_output_format`
- Proxy passed to yt-dlp via the `proxy` option

### TikTok

**Downloader:** `TikTokDownloader` -> `SsstikScraper`
**Backend:** ssstik.io web scraper

- Supports: `tiktok.com/@user/video/`, `vm.tiktok.com/`, `tiktok.com/t/`
- Flow: GET ssstik.io to extract form token -> POST with TikTok URL -> parse HTML for "Without watermark" download link -> download MP4 via `aiohttp`
- No authentication required

### Instagram

**Downloader:** `InstagramDownloader`
**Backends:** Three-level fallback chain (in default `YTDLP` mode)

- Supports: `instagram.com/p/`, `/reel/`, `/tv/`, `/stories/`, profile URLs

#### Fallback chain

| Priority | Scraper | Transport | Auth | Status |
|----------|---------|-----------|------|--------|
| 1 | **sssinstagram.com** | HTTP/2 via noble-tls (Chrome 131) | HMAC-SHA256 signed requests | Working |
| 2 | **snapinsta.to** | HTTP/2 via noble-tls (Chrome 131) | Cloudflare Turnstile token | Blocked by CAPTCHA |
| 3 | **instagrapi** | Instagram private API | Username + password | Working (requires credentials) |

#### sssinstagram.com — technical details

The scraper reverse-engineers the sssinstagram.com signing mechanism:

- **API endpoint:** `POST https://sssinstagram.com/api/convert`
- **Body encoding:** `application/x-www-form-urlencoded`
- **Signing algorithm:**
  1. `ts` = current Unix time in milliseconds
  2. `_s` = `HMAC-SHA256(key, url + ts)` as hex digest
  3. `_ts` = embedded timestamp constant from webpack chunk
  4. `_tsc` = `0` (counter)
  5. `_sv` = `2` (signing version)
- **HMAC key:** Extracted from `link.chunk.js` module 7027 — stored as `_HMAC_KEY` in the scraper. This key may rotate when the site updates its JS bundle.
- **Transport:** HTTP/2 required. Cloudflare rejects HTTP/1.1 with a captcha challenge. noble-tls with `Client.CHROME_131` provides the necessary TLS fingerprint.
- **Response format:** JSON object (single post) or JSON array (profile/multi-post)

#### snapinsta.to — technical details

- **Page config extraction:** GET `snapinsta.to/` -> extract `k_url_search`, `k_token`, `k_exp`, `k_ver` from inline JS
- **Search API:** POST to `/api/ajaxSearch` with URL and page config params
- **Response decoding:** The API returns an obfuscated JS function call. The scraper extracts parameters `(h, u, n, t, e, r)` and runs a deobfuscation routine to recover HTML containing download links.
- **Current limitation:** The search API requires a Cloudflare Turnstile CAPTCHA token that cannot be generated without a real browser. The scraper will fail at the search step in practice. It remains in the fallback chain architecturally but will always fall through to instagrapi.

#### instagrapi — technical details

- Lazily imported (`from instagrapi import Client`) only when needed
- Session persistence: loads/saves session state from `session_file_path` if configured
- Supports photo (media_type=1), video (media_type=2), and album/carousel (media_type=8)
- Login is wrapped in `asyncio.to_thread()` since instagrapi is synchronous

---

## Storage Backends

### S3 (`S3StorageBackend`)

- Uses `aioboto3` for fully async S3 operations
- Key format: `{prefix}{platform}/{source_id}/{filename}`
- Returns `s3://{bucket}/{key}` URI
- Supports any S3-compatible endpoint via `endpoint_url` (MinIO, R2, Spaces, etc.)
- `StorageClass` configurable (STANDARD, INTELLIGENT_TIERING, GLACIER, etc.)

### Local (`LocalStorageBackend`)

- Copies files via `shutil.copy2` (wrapped in `asyncio.to_thread()`)
- Creates parent directories automatically
- Returns the absolute path as a string

### Per-download override

The `save_locally` parameter on `download()` overrides the configured backend for a single call:

```python
# Config points to S3, but this one download goes to disk
result = await downloader.download(url, save_locally="/tmp/one-off/")
```

---

## Data Models

### `ContentMetadata`

Returned by `extract_metadata()` and included in every `DownloadResult`.

| Field | Type | Description |
|-------|------|-------------|
| `platform` | `Platform` | Source platform |
| `content_type` | `ContentType` | `VIDEO`, `IMAGE`, `CAROUSEL`, `AUDIO`, `STORY`, `REEL` |
| `title` | `str \| None` | Content title (truncated to 200 chars for scrapers) |
| `description` | `str \| None` | Full description/caption |
| `author` | `str \| None` | Creator username |
| `author_id` | `str \| None` | Creator platform ID |
| `duration_seconds` | `float \| None` | Video duration |
| `view_count` | `int \| None` | View count |
| `like_count` | `int \| None` | Like count |
| `upload_date` | `datetime \| None` | Original upload timestamp |
| `thumbnail_url` | `str \| None` | Thumbnail image URL |
| `original_url` | `str` | The URL that was passed to the SDK |
| `source_id` | `str` | Platform-specific content ID (auto-sanitized for filename/S3 key safety) |
| `tags` | `list[str]` | Content tags/hashtags |
| `extra` | `dict[str, str \| int \| float \| bool \| None]` | Provider-specific extra fields |

### `DownloadedFile`

One entry per file in the download result.

| Field | Type | Description |
|-------|------|-------------|
| `filename` | `str` | Output filename |
| `content_type` | `ContentType` | File content type |
| `file_size_bytes` | `int` | Size in bytes |
| `mime_type` | `str` | MIME type (e.g., `video/mp4`) |
| `s3_key` | `str \| None` | S3 object key (if uploaded to S3) |
| `s3_url` | `str \| None` | `s3://bucket/key` URI |
| `local_path` | `str \| None` | Local filesystem path |
| `checksum_sha256` | `str \| None` | SHA-256 hex digest |

### `DownloadResult`

Top-level return type from `download()` and `download_many()`.

| Field | Type | Description |
|-------|------|-------------|
| `status` | `DownloadStatus` | `SUCCESS`, `PARTIAL`, or `FAILED` |
| `source_url` | `str` | Original input URL |
| `platform` | `Platform` | Detected platform |
| `metadata` | `ContentMetadata` | Extracted metadata |
| `files` | `list[DownloadedFile]` | Downloaded files |
| `elapsed_seconds` | `float` | Wall-clock time |
| `error_message` | `str \| None` | Error details if failed |

**Properties:**

```python
result.primary_file  # -> DownloadedFile | None (first file)
result.s3_urls       # -> list[str] (all s3:// URIs)
```

---

## Exception Hierarchy

```
InoueDownloaderError
├── UnsupportedPlatformError          # URL doesn't match any known platform
├── ConfigurationError                # Invalid config (e.g., missing credentials for provider)
├── ContentTooLargeError              # File exceeds max_file_size_mb
├── MetadataExtractionError           # Failed to extract metadata
├── RateLimitError                    # Platform rate limit (has retry_after: float | None)
├── ScraperError                      # Web scraper failure (ssstik, snapinsta, sssinstagram)
├── DownloadError                     # Base for download failures
│   ├── YtDlpError                    # yt-dlp specific
│   ├── ApifyError                    # Apify API failure
│   └── InstagramError               # Instagram-specific
│       └── InstagramAuthRequiredError  # Credentials needed but not provided
└── StorageError                      # Base for storage failures
    └── S3UploadError                 # S3 upload specific
```

```python
from inoue_downloader import (
    InoueDownloaderError,
    UnsupportedPlatformError,
    ScraperError,
    InstagramAuthRequiredError,
    ContentTooLargeError,
    RateLimitError,
)

try:
    result = await downloader.download(url)
except UnsupportedPlatformError:
    ...  # URL not recognized
except ContentTooLargeError:
    ...  # File exceeds max_file_size_mb
except RateLimitError as e:
    await asyncio.sleep(e.retry_after or 60)
except ScraperError:
    ...  # Web scraper failed (all retries exhausted in fallback chain)
except InstagramAuthRequiredError:
    ...  # Scrapers failed and no credentials were provided
except InoueDownloaderError:
    ...  # Catch-all for any SDK error
```

---

## Usage Examples

### Download to S3

```python
from inoue_downloader import InoueDownloader, DownloaderConfig, S3Config

config = DownloaderConfig(
    s3=S3Config(
        bucket_name="media-bucket",
        prefix="downloads/",
        aws_access_key_id="AKID...",
        aws_secret_access_key="SECRET...",
        region_name="us-east-1",
    )
)

async with InoueDownloader(config) as dl:
    result = await dl.download("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    print(result.s3_urls)
    # ["s3://media-bucket/downloads/youtube/dQw4w9WgXcQ/dQw4w9WgXcQ.mp4"]
```

### Download to local filesystem

```python
config = DownloaderConfig(local_output_dir="/data/media")

async with InoueDownloader(config) as dl:
    result = await dl.download("https://www.tiktok.com/@user/video/7123456789")
    print(result.files[0].local_path)
    # "/data/media/tiktok/7123456789/video.mp4"
```

### S3-compatible storage (MinIO, R2, Spaces)

```python
config = DownloaderConfig(
    s3=S3Config(
        bucket_name="my-bucket",
        endpoint_url="http://localhost:9000",  # MinIO
        aws_access_key_id="minio",
        aws_secret_access_key="minio123",
    )
)
```

### Batch download with concurrency control

```python
config = DownloaderConfig(
    local_output_dir="/tmp/downloads",
    max_concurrent_downloads=5,
)

async with InoueDownloader(config) as dl:
    results = await dl.download_many([
        "https://www.youtube.com/watch?v=abc",
        "https://www.tiktok.com/@user/video/456",
        "https://www.instagram.com/reel/xyz/",
    ])
    for r in results:
        print(f"{r.platform}: {r.status} ({r.elapsed_seconds:.1f}s)")
```

### Metadata extraction (no download)

```python
async with InoueDownloader(config) as dl:
    meta = await dl.extract_metadata("https://www.youtube.com/watch?v=abc")
    print(meta.title)
    print(meta.duration_seconds)
    print(meta.view_count)
    print(meta.author)
```

### Explicit provider selection (no fallback)

```python
from inoue_downloader import DownloadProvider

# Instagram: force sssinstagram.com only
config = DownloaderConfig(
    provider=DownloadProvider.SSSINSTAGRAM,
    local_output_dir="/tmp/ig",
)

# TikTok: force ssstik.io
config = DownloaderConfig(
    provider=DownloadProvider.SSSTIK,
    local_output_dir="/tmp/tt",
)

# Instagram: force instagrapi with credentials
config = DownloaderConfig(
    provider=DownloadProvider.INSTAGRAPI,
    instagram=InstagramCredentials(
        username="your_user",
        password="your_pass",
        session_file_path="/tmp/ig_session.json",
    ),
    local_output_dir="/tmp/ig",
)
```

### Apify cloud provider

```python
from inoue_downloader import ApifyConfig, DownloadProvider

config = DownloaderConfig(
    provider=DownloadProvider.APIFY,
    apify=ApifyConfig(api_key="apify_api_..."),
    local_output_dir="/tmp/downloads",
)

async with InoueDownloader(config) as dl:
    # Works with any platform
    result = await dl.download("https://www.youtube.com/watch?v=abc")
```

### Proxy configuration

```python
from inoue_downloader import ProxyConfig

config = DownloaderConfig(
    proxy=ProxyConfig(
        https="http://user:pass@proxy.example.com:8080",
    ),
    local_output_dir="/tmp/downloads",
)
```

---

## Project Structure

```
src/inoue_downloader/
├── __init__.py                    # Public API exports
├── client.py                      # InoueDownloader — main entry point
├── config.py                      # Pydantic config models (DownloaderConfig, S3Config, etc.)
├── enums.py                       # Platform, DownloadProvider, ContentType, DownloadStatus
├── exceptions.py                  # Exception hierarchy (11 classes)
├── models.py                      # ContentMetadata, DownloadedFile, DownloadResult
├── platform_detection.py          # URL -> Platform regex resolver
├── downloaders/
│   ├── base.py                    # AbstractDownloader (ABC)
│   ├── factory.py                 # DownloaderFactory — routes platform+provider to implementation
│   ├── ytdlp_downloader.py        # YouTube via yt-dlp
│   ├── tiktok_downloader.py       # TikTok via SsstikScraper
│   ├── instagram_downloader.py    # Instagram with fallback chain + explicit provider modes
│   └── apify_downloader.py        # All platforms via Apify cloud actors
├── scrapers/
│   ├── base.py                    # AbstractScraper (ABC with proxy support)
│   ├── sssinstagram.py            # Instagram scraper — HMAC-SHA256 signed API, HTTP/2 noble-tls
│   ├── snapinsta.py               # Instagram scraper — noble-tls Cloudflare bypass, deobfuscation
│   └── ssstik.py                  # TikTok scraper — ssstik.io token extraction + HTML parsing
├── storage/
│   ├── base.py                    # AbstractStorageBackend (ABC)
│   ├── s3_storage.py              # S3 upload via aioboto3
│   └── local_storage.py           # Local filesystem copy
└── utils/
    └── temp_files.py              # AsyncTempDir context manager

tests/
├── unit/                          # 156 unit tests (all mocked, no network)
│   ├── test_client.py
│   ├── test_config.py
│   ├── test_factory.py
│   ├── test_instagram_downloader.py
│   ├── test_sssinstagram_scraper.py
│   ├── test_snapinsta_scraper.py
│   ├── test_ssstik_scraper.py
│   ├── test_ytdlp_downloader.py
│   ├── test_platform_detection.py
│   ├── test_models.py
│   ├── test_s3_storage.py
│   └── test_local_storage.py
└── e2e/                           # End-to-end tests (hit real APIs)
    ├── test_youtube_download.py
    ├── test_tiktok_download.py
    ├── test_instagram_download.py
    └── test_apify_download.py
```

---

## Development

### Setup

```bash
git clone https://github.com/inoue-ai/Inoue-AI-Content-Downloader-SDK.git
cd Inoue-AI-Content-Downloader-SDK
uv sync --dev
```

### Run tests

```bash
# Unit tests (no network, fast)
uv run pytest tests/unit/ -v

# E2e tests (requires internet, real API calls)
uv run pytest tests/e2e/ -v -m e2e

# With coverage
uv run pytest tests/unit/ --cov=inoue_downloader --cov-report=term-missing
```

### Lint and type check

```bash
uv run ruff check src/ tests/
uv run mypy src/
```

### Dependencies

**Runtime:**

| Package | Purpose |
|---------|---------|
| `yt-dlp` >= 2024.12.0 | YouTube downloading |
| `instagrapi` >= 2.1.0 | Instagram authenticated API (lazily imported) |
| `noble-tls` >= 0.1.9 | HTTP/2 + Chrome TLS fingerprinting (Cloudflare bypass) |
| `aiohttp` >= 3.9.0 | Async HTTP client for media downloads |
| `aioboto3` >= 13.0.0 | Async S3 uploads |
| `pydantic` >= 2.5.0 | Configuration and data model validation |
| `beautifulsoup4` >= 4.12.0 | HTML parsing for scrapers |
| `aiofiles` >= 23.2.0 | Async file operations |
| `brotli` >= 1.2.0 | Brotli decompression for HTTP responses |

**Dev:**

| Package | Purpose |
|---------|---------|
| `pytest` >= 8.0.0 | Test framework |
| `pytest-asyncio` >= 0.24.0 | Async test support |
| `pytest-cov` >= 5.0.0 | Coverage reporting |
| `moto[s3]` >= 5.0.0 | S3 mocking for unit tests |
| `ruff` >= 0.4.0 | Linting and formatting |
| `mypy` >= 1.10.0 | Static type checking |

---

## License

MIT
