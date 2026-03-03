"""End-to-end tests for Apify download provider.

These tests hit the real Apify API using the configured API key.
Run with: APIFY_API_KEY=apify_api_... uv run pytest tests/e2e/test_apify_download.py -v -m e2e
"""

import os
from pathlib import Path

import pytest

from inoue_downloader import (
    ApifyConfig,
    DownloaderConfig,
    DownloadProvider,
    DownloadStatus,
    InoueDownloader,
    Platform,
)

APIFY_API_KEY = os.environ.get("APIFY_API_KEY", "")

# Short, stable public content for testing
YOUTUBE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo"
TIKTOK_URLS = [
    "https://www.tiktok.com/@scout2015/video/6718335390845095173",
    "https://www.tiktok.com/@tiktok/video/7106594312292453675",
]
INSTAGRAM_URLS = [
    "https://www.instagram.com/p/CsC0Y_1u_bA/",
    "https://www.instagram.com/p/CsJEFnLuU5N/",
]


pytestmark = pytest.mark.skipif(not APIFY_API_KEY, reason="APIFY_API_KEY not set")


def _apify_config(tmp_path: Path) -> DownloaderConfig:
    return DownloaderConfig(
        provider=DownloadProvider.APIFY,
        apify=ApifyConfig(api_key=APIFY_API_KEY),
        local_output_dir=str(tmp_path),
    )


# --- YouTube via Apify ---


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_apify_youtube_download(tmp_path: Path) -> None:
    """Download a YouTube video via Apify provider."""
    config = _apify_config(tmp_path)

    async with InoueDownloader(config) as client:
        result = await client.download(YOUTUBE_URL)

    assert result.status == DownloadStatus.SUCCESS
    assert result.platform == Platform.YOUTUBE
    assert result.metadata.source_id is not None
    assert len(result.metadata.source_id) > 0
    assert len(result.files) >= 1
    assert result.files[0].file_size_bytes > 0
    assert result.files[0].local_path is not None
    assert Path(result.files[0].local_path).exists()
    assert result.elapsed_seconds > 0
    assert result.metadata.extra.get("provider") == "apify"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_apify_youtube_metadata(tmp_path: Path) -> None:
    """Extract metadata from a YouTube video via Apify."""
    config = _apify_config(tmp_path)

    async with InoueDownloader(config) as client:
        meta = await client.extract_metadata(YOUTUBE_URL)

    assert meta.platform == Platform.YOUTUBE
    assert meta.source_id is not None
    assert len(meta.source_id) > 0
    assert meta.title is not None
    assert meta.extra.get("provider") == "apify"


# --- TikTok via Apify ---


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_apify_tiktok_download(tmp_path: Path) -> None:
    """Download a TikTok video via Apify provider."""
    config = _apify_config(tmp_path)

    async with InoueDownloader(config) as client:
        last_err: Exception | None = None
        result = None
        for url in TIKTOK_URLS:
            try:
                result = await client.download(url)
                break
            except Exception as e:
                last_err = e
                continue

        if result is None:
            pytest.fail(f"All TikTok URLs failed via Apify. Last error: {last_err}")

    assert result.status == DownloadStatus.SUCCESS
    assert result.platform == Platform.TIKTOK
    assert len(result.files) >= 1
    assert result.files[0].file_size_bytes > 0
    assert result.files[0].local_path is not None
    assert Path(result.files[0].local_path).exists()
    assert result.elapsed_seconds > 0
    assert result.metadata.extra.get("provider") == "apify"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_apify_tiktok_metadata(tmp_path: Path) -> None:
    """Extract metadata from a TikTok video via Apify."""
    config = _apify_config(tmp_path)

    async with InoueDownloader(config) as client:
        last_err: Exception | None = None
        meta = None
        for url in TIKTOK_URLS:
            try:
                meta = await client.extract_metadata(url)
                break
            except Exception as e:
                last_err = e
                continue

        if meta is None:
            pytest.fail(f"All TikTok metadata URLs failed via Apify. Last error: {last_err}")

    assert meta.platform == Platform.TIKTOK
    assert meta.source_id is not None
    assert len(meta.source_id) > 0
    assert meta.extra.get("provider") == "apify"


# --- Instagram via Apify ---


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_apify_instagram_download(tmp_path: Path) -> None:
    """Download an Instagram post via Apify provider."""
    config = _apify_config(tmp_path)

    async with InoueDownloader(config) as client:
        last_err: Exception | None = None
        result = None
        for url in INSTAGRAM_URLS:
            try:
                result = await client.download(url)
                break
            except Exception as e:
                last_err = e
                continue

        if result is None:
            err_msg = str(last_err).lower() if last_err else ""
            if any(
                kw in err_msg
                for kw in ("restricted", "unavailable", "login", "auth", "not accessible")
            ):
                pytest.skip("Instagram restricted access via Apify (may need paid actor or proxy)")
            pytest.fail(f"All Instagram URLs failed via Apify. Last error: {last_err}")

    assert result.status == DownloadStatus.SUCCESS
    assert result.platform == Platform.INSTAGRAM
    assert len(result.files) >= 1
    assert result.files[0].file_size_bytes > 0
    assert result.files[0].local_path is not None
    assert Path(result.files[0].local_path).exists()
    assert result.elapsed_seconds > 0
    assert result.metadata.extra.get("provider") == "apify"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_apify_instagram_metadata(tmp_path: Path) -> None:
    """Extract metadata from an Instagram post via Apify."""
    config = _apify_config(tmp_path)

    async with InoueDownloader(config) as client:
        last_err: Exception | None = None
        meta = None
        for url in INSTAGRAM_URLS:
            try:
                meta = await client.extract_metadata(url)
                break
            except Exception as e:
                last_err = e
                continue

        if meta is None:
            err_msg = str(last_err).lower() if last_err else ""
            if any(
                kw in err_msg
                for kw in ("restricted", "unavailable", "login", "auth", "not accessible")
            ):
                pytest.skip("Instagram restricted access via Apify (may need paid actor or proxy)")
            pytest.fail(f"All Instagram metadata URLs failed via Apify. Last error: {last_err}")

    assert meta.platform == Platform.INSTAGRAM
    assert meta.source_id is not None
    assert len(meta.source_id) > 0
    assert meta.extra.get("provider") == "apify"


# --- Provider selection tests ---


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_apify_provider_requires_config() -> None:
    """Ensure APIFY provider fails without ApifyConfig."""
    with pytest.raises(ValueError, match="ApifyConfig must be provided"):
        DownloaderConfig(
            provider=DownloadProvider.APIFY,
            local_output_dir="/tmp/unused",
        )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_apify_session_cleanup(tmp_path: Path) -> None:
    """Verify that the aiohttp session is properly cleaned up on exit."""
    config = _apify_config(tmp_path)

    async with InoueDownloader(config) as client:
        meta = await client.extract_metadata(YOUTUBE_URL)
        assert meta.platform == Platform.YOUTUBE

    # After context manager exit, downloaders should be cleaned up
    assert len(client._downloaders) == 0
