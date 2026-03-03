from pathlib import Path

import pytest

from inoue_downloader import DownloaderConfig, DownloadStatus, InoueDownloader, Platform

# Stable public Instagram posts/reels (official accounts, backup URLs)
INSTAGRAM_URLS = [
    "https://www.instagram.com/reel/DVZRlGvkdWg/",
    "https://www.instagram.com/p/CsC0Y_1u_bA/",
    "https://www.instagram.com/p/CsJEFnLuU5N/",
]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_instagram_download_to_local(tmp_path: Path) -> None:
    """Download an Instagram post to local storage via sssinstagram.com/snapinsta.to/instagrapi."""
    config = DownloaderConfig(local_output_dir=str(tmp_path))

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
                for kw in ("login", "cookie", "auth", "credentials", "empty media", "captcha")
            ):
                pytest.skip("Instagram requires auth and scrapers unavailable in this environment")
            pytest.fail(f"All Instagram URLs failed. Last error: {last_err}")

    assert result.status == DownloadStatus.SUCCESS
    assert result.platform == Platform.INSTAGRAM
    assert len(result.files) >= 1
    assert result.files[0].file_size_bytes > 0
    assert result.files[0].local_path is not None
    assert Path(result.files[0].local_path).exists()
    assert result.elapsed_seconds > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_instagram_extract_metadata() -> None:
    """Extract metadata from an Instagram post."""
    config = DownloaderConfig(local_output_dir="/tmp/unused")

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
                kw in err_msg for kw in ("login", "cookie", "auth", "credentials", "empty media")
            ):
                pytest.skip("Instagram requires auth and scrapers unavailable in this environment")
            pytest.fail(f"All Instagram metadata URLs failed. Last error: {last_err}")

    assert meta.platform == Platform.INSTAGRAM
    assert meta.source_id is not None
    assert len(meta.source_id) > 0
