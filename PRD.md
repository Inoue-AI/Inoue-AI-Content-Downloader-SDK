# Product Requirements Document (PRD)

## Inoue AI Content Downloader SDK

### Overview

The Inoue AI Content Downloader SDK is a public, async Python SDK that enables developers to download social media content (videos, posts, carousels) from YouTube, TikTok, and Instagram using a single URL. The SDK auto-detects the platform, downloads the content, and uploads it directly to an S3-compatible storage backend — without saving files locally by default.

### Problem Statement

Developers building content pipelines, archival tools, or media processing services need a unified way to download content from multiple social platforms. Existing solutions are fragmented (one library per platform), synchronous, and require manual file handling. There is no single async SDK that handles download + upload to cloud storage as a unified operation.

### Goals

1. **Single URL, any platform** — Accept a URL from YouTube, TikTok, or Instagram and automatically detect the platform and download the content.
2. **Direct-to-S3 pipeline** — Downloaded content goes directly to S3 (or S3-compatible storage) without persisting locally, minimizing disk usage and cleanup concerns.
3. **Fully async** — All operations are async-native using `asyncio`, suitable for high-throughput applications.
4. **Pydantic everywhere** — All configuration, metadata, and results use Pydantic v2 models for validation, serialization, and documentation.
5. **Extensible** — Adding new platforms requires implementing a single abstract class. Adding new storage backends is equally straightforward.
6. **Production-ready** — Comprehensive error handling, logging, file size limits, concurrent download throttling, and automatic temp file cleanup.
7. **Provider choice** — Users can select their download provider (yt-dlp or Apify) per configuration, allowing flexibility in how content is fetched.

### Target Users

- Backend developers building media processing pipelines
- Content archival and compliance teams
- AI/ML teams collecting training data from social platforms
- SaaS products that process user-submitted social media URLs

### Supported Platforms

| Platform   | Content Types              | Auth Required | Default Provider       | Alt Provider |
|-----------|---------------------------|---------------|------------------------|--------------|
| YouTube    | Videos, Shorts             | No            | yt-dlp                 | Apify        |
| TikTok     | Videos                     | No            | ssstik.io scraper      | Apify        |
| Instagram  | Posts, Reels, Carousels    | Optional*     | sssinstagram.com → snapinsta.to → instagrapi | Apify     |

*Instagram public posts are attempted via sssinstagram.com first (HMAC-signed API over HTTP/2, most reliable). If that fails, the SDK tries snapinsta.to (cloudscraper for Cloudflare bypass). If both scrapers fail, it falls back to `instagrapi` which requires credentials. When using the Apify provider, no auth is needed. Note: yt-dlp is used exclusively for YouTube.

### Download Providers

| Provider | Enum Value | Description |
|----------|-----------|-------------|
| yt-dlp   | `YTDLP`   | Default. Uses yt-dlp for YouTube, ssstik.io scraper for TikTok, sssinstagram.com + snapinsta.to + instagrapi for Instagram. |
| Apify    | `APIFY`   | Cloud-based. Runs Apify actors via REST API. Requires an Apify API key. |

### Core Features

#### 1. Platform Auto-Detection
- Parse any URL and determine which platform it belongs to
- Support all common URL formats (short URLs, mobile URLs, embeds)
- Raise `UnsupportedPlatformError` for unknown URLs

#### 2. Content Download
- Download video, image, and carousel content
- Extract rich metadata (title, author, duration, view/like counts, tags)
- Support configurable video quality (yt-dlp provider)
- Concurrent download throttling via semaphore

#### 3. Download Provider Selection
- Configure the download provider via `DownloaderConfig.provider`
- **YTDLP** (default): Uses yt-dlp for YouTube, ssstik.io for TikTok, snapinsta.to + instagrapi for Instagram
- **APIFY**: Uses Apify cloud actors via REST API with proper session management
- All Apify HTTP requests go through managed `aiohttp.ClientSession` instances that are properly closed on cleanup

#### 4. S3 Upload
- Upload downloaded files to S3 using `aioboto3`
- Support custom bucket, prefix, region, storage class
- Support S3-compatible endpoints (MinIO, Cloudflare R2, DigitalOcean Spaces)
- **Users pass their own S3 credentials** via `S3Config` (access key, secret key, session token)
- Credentials via explicit config or IAM role fallback

#### 5. Local Fallback
- Optional: save files to local filesystem instead of S3
- Activated per-call via `save_locally="/path/to/dir"` parameter
- Or globally via `local_output_dir` in config

#### 6. Metadata Extraction
- Extract metadata without downloading via `extract_metadata(url)`
- Returns `ContentMetadata` with platform, title, author, duration, counts, etc.

#### 7. Batch Downloads
- `download_many(urls)` for concurrent batch downloads
- Bounded by `max_concurrent_downloads` config
- Returns list of `DownloadResult` objects

### Non-Functional Requirements

- **Python 3.11+** minimum
- **Zero local disk footprint** in default mode (temp files cleaned automatically)
- **Bounded memory** — files are streamed to S3, not loaded into memory
- **Structured logging** via Python `logging` module
- **Type-safe** — full type hints, mypy-strict compatible
- **Testable** — 74+ unit tests with mocked external dependencies, e2e test suite
- **Session management** — all HTTP requests use managed sessions that are properly created and closed

### Configuration Model

```python
# Default provider (yt-dlp)
DownloaderConfig(
    s3=S3Config(bucket_name="...", region_name="..."),
    instagram=InstagramCredentials(username="...", password="..."),  # optional
    max_concurrent_downloads=3,
    request_timeout=300,
    max_file_size_mb=500,
    preferred_video_quality="best",
    log_level="INFO",
)

# Apify provider
DownloaderConfig(
    provider=DownloadProvider.APIFY,
    apify=ApifyConfig(api_key="apify_api_..."),
    s3=S3Config(
        bucket_name="my-bucket",
        aws_access_key_id="AKID...",
        aws_secret_access_key="SECRET...",
    ),
)
```

### Success Metrics

- All unit tests pass (74+)
- E2E tests successfully download from YouTube, TikTok, Instagram
- E2E tests pass for both yt-dlp and Apify providers
- Clean public API that can be explained in < 10 lines of code
- Zero file leaks (temp directories always cleaned up)
- All HTTP sessions properly created and closed

### Future Considerations

- Twitter/X support
- Reddit support
- Webhook/callback notifications on download completion
- Download progress callbacks
- Thumbnail extraction and upload
- Audio-only extraction mode
- Additional download providers
