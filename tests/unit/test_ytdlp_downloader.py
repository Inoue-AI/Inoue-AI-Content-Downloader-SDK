from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from inoue_downloader.config import DownloaderConfig, S3Config
from inoue_downloader.downloaders.ytdlp_downloader import YtDlpDownloader
from inoue_downloader.enums import ContentType, Platform
from inoue_downloader.exceptions import YtDlpError


@pytest.fixture
def config() -> DownloaderConfig:
    return DownloaderConfig(s3=S3Config(bucket_name="test"))


@pytest.fixture
def downloader(config: DownloaderConfig) -> YtDlpDownloader:
    return YtDlpDownloader(config, platform=Platform.YOUTUBE)


MOCK_YT_INFO = {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up",
    "description": "The official video",
    "uploader": "Rick Astley",
    "uploader_id": "@RickAstley",
    "duration": 212,
    "view_count": 1500000000,
    "like_count": 15000000,
    "upload_date": "20091025",
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "tags": ["rick astley", "never gonna give you up"],
    "extractor": "youtube",
    "format": "248 - 1920x1080",
    "resolution": "1920x1080",
}


class TestYtDlpDownloaderMetadata:
    @pytest.mark.asyncio
    async def test_extract_metadata(self, downloader: YtDlpDownloader) -> None:
        with patch("inoue_downloader.downloaders.ytdlp_downloader.YoutubeDL") as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
            mock_ydl.__exit__ = MagicMock(return_value=False)
            mock_ydl.extract_info.return_value = MOCK_YT_INFO
            mock_ydl_cls.return_value = mock_ydl

            meta = await downloader.extract_metadata("https://youtube.com/watch?v=dQw4w9WgXcQ")

        assert meta.platform == Platform.YOUTUBE
        assert meta.content_type == ContentType.VIDEO
        assert meta.title == "Rick Astley - Never Gonna Give You Up"
        assert meta.author == "Rick Astley"
        assert meta.duration_seconds == 212.0
        assert meta.source_id == "dQw4w9WgXcQ"
        assert meta.view_count == 1500000000
        assert meta.upload_date is not None

    @pytest.mark.asyncio
    async def test_extract_metadata_none_info(self, downloader: YtDlpDownloader) -> None:
        with (
            patch("inoue_downloader.downloaders.ytdlp_downloader.YoutubeDL") as mock_ydl_cls,
            pytest.raises(YtDlpError, match="returned no info"),
        ):
            mock_ydl = MagicMock()
            mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
            mock_ydl.__exit__ = MagicMock(return_value=False)
            mock_ydl.extract_info.return_value = None
            mock_ydl_cls.return_value = mock_ydl

            await downloader.extract_metadata("https://youtube.com/watch?v=bad")

    @pytest.mark.asyncio
    async def test_extract_metadata_exception(self, downloader: YtDlpDownloader) -> None:
        with (
            patch("inoue_downloader.downloaders.ytdlp_downloader.YoutubeDL") as mock_ydl_cls,
            pytest.raises(YtDlpError, match="Failed to extract metadata"),
        ):
            mock_ydl = MagicMock()
            mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
            mock_ydl.__exit__ = MagicMock(return_value=False)
            mock_ydl.extract_info.side_effect = RuntimeError("Network error")
            mock_ydl_cls.return_value = mock_ydl

            await downloader.extract_metadata("https://youtube.com/watch?v=bad")


class TestYtDlpDownloaderDownload:
    @pytest.mark.asyncio
    async def test_download_success(self, downloader: YtDlpDownloader, tmp_path: Path) -> None:
        video_file = tmp_path / "dQw4w9WgXcQ.mp4"
        video_file.write_bytes(b"fake video content")

        with patch("inoue_downloader.downloaders.ytdlp_downloader.YoutubeDL") as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
            mock_ydl.__exit__ = MagicMock(return_value=False)
            mock_ydl.extract_info.return_value = MOCK_YT_INFO
            mock_ydl_cls.return_value = mock_ydl

            metadata, files = await downloader.download(
                "https://youtube.com/watch?v=dQw4w9WgXcQ", tmp_path
            )

        assert metadata.source_id == "dQw4w9WgXcQ"
        assert len(files) == 1
        assert files[0].name == "dQw4w9WgXcQ.mp4"

    @pytest.mark.asyncio
    async def test_download_no_files(self, downloader: YtDlpDownloader, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with (
            patch("inoue_downloader.downloaders.ytdlp_downloader.YoutubeDL") as mock_ydl_cls,
            pytest.raises(YtDlpError, match="no files were written"),
        ):
            mock_ydl = MagicMock()
            mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
            mock_ydl.__exit__ = MagicMock(return_value=False)
            mock_ydl.extract_info.return_value = MOCK_YT_INFO
            mock_ydl_cls.return_value = mock_ydl

            await downloader.download("https://youtube.com/watch?v=dQw4w9WgXcQ", empty_dir)

    @pytest.mark.asyncio
    async def test_download_exception(self, downloader: YtDlpDownloader, tmp_path: Path) -> None:
        with (
            patch("inoue_downloader.downloaders.ytdlp_downloader.YoutubeDL") as mock_ydl_cls,
            pytest.raises(YtDlpError, match="Download failed"),
        ):
            mock_ydl = MagicMock()
            mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
            mock_ydl.__exit__ = MagicMock(return_value=False)
            mock_ydl.extract_info.side_effect = RuntimeError("Download error")
            mock_ydl_cls.return_value = mock_ydl

            await downloader.download("https://youtube.com/watch?v=bad", tmp_path)


class TestInfoToMetadata:
    def test_image_content_type(self, downloader: YtDlpDownloader) -> None:
        info = {"id": "test", "title": "Photo"}
        meta = downloader._info_to_metadata(info, "https://test.com")
        assert meta.content_type == ContentType.IMAGE

    def test_missing_optional_fields(self, downloader: YtDlpDownloader) -> None:
        info = {"id": "test", "duration": 10}
        meta = downloader._info_to_metadata(info, "https://test.com")
        assert meta.title is None
        assert meta.author is None
        assert meta.tags == []
