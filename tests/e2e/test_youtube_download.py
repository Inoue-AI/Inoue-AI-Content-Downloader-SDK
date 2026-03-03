from pathlib import Path

import pytest

from inoue_downloader import DownloaderConfig, DownloadStatus, InoueDownloader, Platform


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_youtube_download_to_local(tmp_path: Path) -> None:
    """Download a short, public YouTube video to local storage."""
    config = DownloaderConfig(local_output_dir=str(tmp_path))

    async with InoueDownloader(config) as client:
        # "Me at the zoo" - first YouTube video, very short
        result = await client.download("https://www.youtube.com/watch?v=jNQXAC9IVRw")

    assert result.status == DownloadStatus.SUCCESS
    assert result.platform == Platform.YOUTUBE
    assert result.metadata.title is not None
    assert result.metadata.source_id == "jNQXAC9IVRw"
    assert len(result.files) >= 1
    assert result.files[0].local_path is not None
    assert Path(result.files[0].local_path).exists()
    assert result.files[0].file_size_bytes > 0
    assert result.elapsed_seconds > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_youtube_extract_metadata() -> None:
    """Extract metadata from a YouTube video without downloading."""
    config = DownloaderConfig(local_output_dir="/tmp/unused")

    async with InoueDownloader(config) as client:
        meta = await client.extract_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")

    assert meta.platform == Platform.YOUTUBE
    assert meta.title is not None
    assert meta.source_id == "jNQXAC9IVRw"
    assert meta.duration_seconds is not None
    assert meta.duration_seconds > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_youtube_shorts_download(tmp_path: Path) -> None:
    """Download a YouTube Shorts video."""
    config = DownloaderConfig(local_output_dir=str(tmp_path))

    async with InoueDownloader(config) as client:
        meta = await client.extract_metadata("https://www.youtube.com/watch?v=jNQXAC9IVRw")

    assert meta.platform == Platform.YOUTUBE
