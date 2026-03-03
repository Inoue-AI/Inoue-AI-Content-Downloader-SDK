from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from inoue_downloader import DownloaderConfig, DownloadStatus, InoueDownloader, S3Config
from inoue_downloader.enums import ContentType, Platform
from inoue_downloader.exceptions import ContentTooLargeError
from inoue_downloader.models import ContentMetadata


def _make_metadata(
    platform: Platform = Platform.YOUTUBE, source_id: str = "abc"
) -> ContentMetadata:
    return ContentMetadata(
        platform=platform,
        content_type=ContentType.VIDEO,
        original_url="https://youtube.com/watch?v=abc",
        source_id=source_id,
        title="Test Video",
        author="Test Author",
        duration_seconds=120.0,
    )


class TestInoueDownloader:
    @pytest.mark.asyncio
    async def test_download_to_s3(self, tmp_path: Path) -> None:
        config = DownloaderConfig(s3=S3Config(bucket_name="test"))
        video_file = tmp_path / "abc.mp4"
        video_file.write_bytes(b"fake video")

        mock_downloader = AsyncMock()
        mock_downloader.download.return_value = (_make_metadata(), [video_file])

        mock_storage = AsyncMock()
        mock_storage.upload.return_value = "s3://test/youtube/abc/abc.mp4"

        with (
            patch(
                "inoue_downloader.client.DownloaderFactory.create",
                return_value=mock_downloader,
            ),
            patch(
                "inoue_downloader.client.S3StorageBackend",
                return_value=mock_storage,
            ),
            patch("inoue_downloader.client.AsyncTempDir") as mock_temp,
        ):
            mock_temp.return_value.__aenter__ = AsyncMock(return_value=tmp_path)
            mock_temp.return_value.__aexit__ = AsyncMock(return_value=None)

            async with InoueDownloader(config) as client:
                result = await client.download("https://youtube.com/watch?v=abc")

        assert result.status == DownloadStatus.SUCCESS
        assert result.platform == Platform.YOUTUBE
        assert len(result.files) == 1
        assert result.files[0].s3_url == "s3://test/youtube/abc/abc.mp4"
        assert result.files[0].s3_key == "youtube/abc/abc.mp4"

    @pytest.mark.asyncio
    async def test_download_locally(self, tmp_path: Path) -> None:
        config = DownloaderConfig(local_output_dir=str(tmp_path / "default"))
        video_file = tmp_path / "abc.mp4"
        video_file.write_bytes(b"fake video")

        mock_downloader = AsyncMock()
        mock_downloader.download.return_value = (_make_metadata(), [video_file])

        mock_storage = AsyncMock()
        mock_storage.upload.return_value = str(tmp_path / "custom" / "youtube" / "abc" / "abc.mp4")

        with (
            patch(
                "inoue_downloader.client.DownloaderFactory.create",
                return_value=mock_downloader,
            ),
            patch(
                "inoue_downloader.client.LocalStorageBackend",
                return_value=mock_storage,
            ),
            patch("inoue_downloader.client.AsyncTempDir") as mock_temp,
        ):
            mock_temp.return_value.__aenter__ = AsyncMock(return_value=tmp_path)
            mock_temp.return_value.__aexit__ = AsyncMock(return_value=None)

            async with InoueDownloader(config) as client:
                result = await client.download(
                    "https://youtube.com/watch?v=abc",
                    save_locally=str(tmp_path / "custom"),
                )

        assert result.status == DownloadStatus.SUCCESS
        assert len(result.files) == 1
        assert result.files[0].local_path is not None

    @pytest.mark.asyncio
    async def test_content_too_large(self, tmp_path: Path) -> None:
        config = DownloaderConfig(s3=S3Config(bucket_name="test"), max_file_size_mb=1)
        large_file = tmp_path / "large.mp4"
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))

        mock_downloader = AsyncMock()
        mock_downloader.download.return_value = (_make_metadata(), [large_file])

        with (
            patch(
                "inoue_downloader.client.DownloaderFactory.create",
                return_value=mock_downloader,
            ),
            patch("inoue_downloader.client.AsyncTempDir") as mock_temp,
            pytest.raises(ContentTooLargeError),
        ):
            mock_temp.return_value.__aenter__ = AsyncMock(return_value=tmp_path)
            mock_temp.return_value.__aexit__ = AsyncMock(return_value=None)

            async with InoueDownloader(config) as client:
                await client.download("https://youtube.com/watch?v=abc")

    @pytest.mark.asyncio
    async def test_download_many(self, tmp_path: Path) -> None:
        config = DownloaderConfig(s3=S3Config(bucket_name="test"), max_concurrent_downloads=2)

        video1 = tmp_path / "vid1.mp4"
        video1.write_bytes(b"video 1")
        video2 = tmp_path / "vid2.mp4"
        video2.write_bytes(b"video 2")

        call_count = 0

        async def mock_download(url: str, output_dir: Path) -> tuple:
            nonlocal call_count
            call_count += 1
            f = video1 if call_count % 2 else video2
            return _make_metadata(source_id=f"vid{call_count}"), [f]

        mock_downloader = AsyncMock()
        mock_downloader.download.side_effect = mock_download

        mock_storage = AsyncMock()
        mock_storage.upload.return_value = "s3://test/video.mp4"

        with (
            patch(
                "inoue_downloader.client.DownloaderFactory.create",
                return_value=mock_downloader,
            ),
            patch(
                "inoue_downloader.client.S3StorageBackend",
                return_value=mock_storage,
            ),
            patch("inoue_downloader.client.AsyncTempDir") as mock_temp,
        ):
            mock_temp.return_value.__aenter__ = AsyncMock(return_value=tmp_path)
            mock_temp.return_value.__aexit__ = AsyncMock(return_value=None)

            async with InoueDownloader(config) as client:
                results = await client.download_many(
                    [
                        "https://youtube.com/watch?v=1",
                        "https://youtube.com/watch?v=2",
                    ]
                )

        assert len(results) == 2
        assert all(r.status == DownloadStatus.SUCCESS for r in results)

    @pytest.mark.asyncio
    async def test_extract_metadata(self) -> None:
        config = DownloaderConfig(s3=S3Config(bucket_name="test"))

        mock_downloader = AsyncMock()
        mock_downloader.extract_metadata.return_value = _make_metadata()

        with patch(
            "inoue_downloader.client.DownloaderFactory.create",
            return_value=mock_downloader,
        ):
            async with InoueDownloader(config) as client:
                meta = await client.extract_metadata("https://youtube.com/watch?v=abc")

        assert meta.platform == Platform.YOUTUBE
        assert meta.title == "Test Video"

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self) -> None:
        config = DownloaderConfig(s3=S3Config(bucket_name="test"))

        mock_downloader = AsyncMock()
        mock_downloader.extract_metadata.return_value = _make_metadata()

        with patch(
            "inoue_downloader.client.DownloaderFactory.create",
            return_value=mock_downloader,
        ):
            async with InoueDownloader(config) as client:
                await client.extract_metadata("https://youtube.com/watch?v=abc")

            mock_downloader.cleanup.assert_called_once()
