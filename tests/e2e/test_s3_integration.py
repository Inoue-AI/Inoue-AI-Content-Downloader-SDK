"""E2E test for S3 upload integration using moto (mocked S3)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from inoue_downloader import DownloaderConfig, DownloadStatus, InoueDownloader, S3Config
from inoue_downloader.enums import Platform


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_download_to_s3_mock(tmp_path: Path) -> None:
    """Test full download-to-S3 pipeline with mocked yt-dlp and mocked S3."""
    config = DownloaderConfig(
        s3=S3Config(
            bucket_name="test-bucket",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
            endpoint_url="http://localhost:5000",
        ),
    )

    mock_info = {
        "id": "test123",
        "title": "Test Video",
        "uploader": "TestUser",
        "duration": 30,
        "extractor": "youtube",
    }

    video_file_content = b"fake video content for s3 test"

    with patch("inoue_downloader.downloaders.ytdlp_downloader.YoutubeDL") as mock_ydl_cls:
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        def fake_extract_info(url: str, download: bool = False) -> dict:
            if download:
                # Simulate yt-dlp writing a file: we need to find the temp dir
                # from the outtmpl option that was set
                outtmpl = mock_ydl_cls.call_args[0][0]["outtmpl"]
                out_path = Path(outtmpl.replace("%(id)s", "test123").replace("%(ext)s", "mp4"))
                out_path.write_bytes(video_file_content)
            return mock_info

        mock_ydl.extract_info.side_effect = fake_extract_info
        mock_ydl_cls.return_value = mock_ydl

        # Mock S3 upload since we don't have a real S3 endpoint
        with patch("inoue_downloader.storage.s3_storage.S3StorageBackend.upload") as mock_upload:
            mock_upload.return_value = "s3://test-bucket/youtube/test123/test123.mp4"

            async with InoueDownloader(config) as client:
                result = await client.download("https://youtube.com/watch?v=test123")

    assert result.status == DownloadStatus.SUCCESS
    assert result.platform == Platform.YOUTUBE
    assert result.metadata.title == "Test Video"
    assert len(result.files) == 1
    assert result.files[0].s3_url == "s3://test-bucket/youtube/test123/test123.mp4"
    assert result.files[0].s3_key == "youtube/test123/test123.mp4"
