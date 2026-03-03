from pathlib import Path

import pytest

from inoue_downloader import DownloaderConfig, DownloadStatus, InoueDownloader, Platform

# Stable, popular public TikTok videos (backup URLs in case primary goes stale)
TIKTOK_URLS = [
    "https://www.tiktok.com/@scout2015/video/6718335390845095173",
    "https://www.tiktok.com/@tiktok/video/7106594312292453675",
]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tiktok_download_to_local(tmp_path: Path) -> None:
    """Download a TikTok video to local storage via yt-dlp or ssstik.io fallback."""
    config = DownloaderConfig(local_output_dir=str(tmp_path))

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
            err_msg = str(last_err).lower() if last_err else ""
            if "login" in err_msg or "cookie" in err_msg or "token" in err_msg:
                pytest.skip("TikTok requires auth and scrapers unavailable in this environment")
            pytest.fail(f"All TikTok URLs failed. Last error: {last_err}")

    assert result.status == DownloadStatus.SUCCESS
    assert result.platform == Platform.TIKTOK
    assert len(result.files) >= 1
    assert result.files[0].file_size_bytes > 0
    assert result.files[0].local_path is not None
    assert Path(result.files[0].local_path).exists()
    assert result.elapsed_seconds > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tiktok_extract_metadata() -> None:
    """Extract metadata from a TikTok video."""
    config = DownloaderConfig(local_output_dir="/tmp/unused")

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
            err_msg = str(last_err).lower() if last_err else ""
            if "login" in err_msg or "cookie" in err_msg or "token" in err_msg:
                pytest.skip("TikTok requires auth and scrapers unavailable in this environment")
            pytest.fail(f"All TikTok metadata URLs failed. Last error: {last_err}")

    assert meta.platform == Platform.TIKTOK
    assert meta.source_id is not None
    assert len(meta.source_id) > 0
