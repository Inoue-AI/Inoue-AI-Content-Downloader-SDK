from datetime import UTC, datetime

from inoue_downloader.enums import ContentType, DownloadStatus, Platform
from inoue_downloader.models import ContentMetadata, DownloadedFile, DownloadResult


class TestContentMetadata:
    def test_minimal(self) -> None:
        meta = ContentMetadata(
            platform=Platform.YOUTUBE,
            content_type=ContentType.VIDEO,
            original_url="https://youtube.com/watch?v=test",
            source_id="test",
        )
        assert meta.platform == Platform.YOUTUBE
        assert meta.title is None
        assert meta.tags == []
        assert meta.extra == {}

    def test_full(self) -> None:
        meta = ContentMetadata(
            platform=Platform.TIKTOK,
            content_type=ContentType.VIDEO,
            title="Test Video",
            description="A test",
            author="testuser",
            author_id="123",
            duration_seconds=30.5,
            view_count=1000,
            like_count=50,
            upload_date=datetime(2024, 1, 1, tzinfo=UTC),
            thumbnail_url="https://example.com/thumb.jpg",
            original_url="https://tiktok.com/@user/video/123",
            source_id="123",
            tags=["test", "video"],
            extra={"extractor": "TikTok"},
        )
        assert meta.duration_seconds == 30.5
        assert len(meta.tags) == 2


class TestDownloadedFile:
    def test_s3_file(self) -> None:
        f = DownloadedFile(
            filename="video.mp4",
            content_type=ContentType.VIDEO,
            file_size_bytes=1024,
            mime_type="video/mp4",
            s3_key="youtube/abc/video.mp4",
            s3_url="s3://bucket/youtube/abc/video.mp4",
        )
        assert f.s3_url is not None
        assert f.local_path is None

    def test_local_file(self) -> None:
        f = DownloadedFile(
            filename="video.mp4",
            content_type=ContentType.VIDEO,
            file_size_bytes=1024,
            mime_type="video/mp4",
            local_path="/tmp/output/video.mp4",
        )
        assert f.local_path is not None
        assert f.s3_url is None


class TestDownloadResult:
    def _make_result(self, files: list[DownloadedFile] | None = None) -> DownloadResult:
        meta = ContentMetadata(
            platform=Platform.YOUTUBE,
            content_type=ContentType.VIDEO,
            original_url="https://youtube.com/watch?v=test",
            source_id="test",
        )
        return DownloadResult(
            status=DownloadStatus.SUCCESS,
            source_url="https://youtube.com/watch?v=test",
            platform=Platform.YOUTUBE,
            metadata=meta,
            files=files or [],
            elapsed_seconds=1.5,
        )

    def test_primary_file_empty(self) -> None:
        result = self._make_result()
        assert result.primary_file is None

    def test_primary_file(self) -> None:
        f = DownloadedFile(
            filename="video.mp4",
            content_type=ContentType.VIDEO,
            file_size_bytes=1024,
            mime_type="video/mp4",
            s3_url="s3://bucket/test.mp4",
        )
        result = self._make_result(files=[f])
        assert result.primary_file is not None
        assert result.primary_file.filename == "video.mp4"

    def test_s3_urls(self) -> None:
        files = [
            DownloadedFile(
                filename="1.jpg",
                content_type=ContentType.IMAGE,
                file_size_bytes=100,
                mime_type="image/jpeg",
                s3_url="s3://bucket/1.jpg",
            ),
            DownloadedFile(
                filename="2.jpg",
                content_type=ContentType.IMAGE,
                file_size_bytes=200,
                mime_type="image/jpeg",
                s3_url="s3://bucket/2.jpg",
            ),
        ]
        result = self._make_result(files=files)
        assert len(result.s3_urls) == 2

    def test_failed_result(self) -> None:
        meta = ContentMetadata(
            platform=Platform.YOUTUBE,
            content_type=ContentType.VIDEO,
            original_url="https://youtube.com/watch?v=test",
            source_id="test",
        )
        result = DownloadResult(
            status=DownloadStatus.FAILED,
            source_url="https://youtube.com/watch?v=test",
            platform=Platform.YOUTUBE,
            metadata=meta,
            files=[],
            elapsed_seconds=0.5,
            error_message="Something went wrong",
        )
        assert result.error_message is not None
        assert result.status == DownloadStatus.FAILED
