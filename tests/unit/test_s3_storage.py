from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from inoue_downloader.config import S3Config
from inoue_downloader.exceptions import S3UploadError
from inoue_downloader.storage.s3_storage import S3StorageBackend


@pytest.fixture
def s3_config() -> S3Config:
    return S3Config(
        bucket_name="test-bucket",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )


@pytest.fixture
def s3_config_with_prefix() -> S3Config:
    return S3Config(
        bucket_name="test-bucket",
        prefix="downloads/",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )


def _mock_s3_session() -> MagicMock:
    """Create a mock aioboto3 session with an async S3 client."""
    mock_s3_client = AsyncMock()
    mock_s3_client.upload_fileobj = AsyncMock()

    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.client.return_value = mock_context
    return mock_session


@pytest.mark.asyncio
async def test_upload_to_s3(s3_config: S3Config, tmp_path: Path) -> None:
    backend = S3StorageBackend(s3_config)
    backend._session = _mock_s3_session()

    test_file = tmp_path / "test.mp4"
    test_file.write_bytes(b"fake video content")

    result = await backend.upload(test_file, "youtube/abc/test.mp4", "video/mp4")
    assert result == "s3://test-bucket/youtube/abc/test.mp4"

    mock_client = await backend._session.client.return_value.__aenter__()
    mock_client.upload_fileobj.assert_called_once()
    call_args = mock_client.upload_fileobj.call_args
    assert call_args[0][1] == "test-bucket"
    assert call_args[0][2] == "youtube/abc/test.mp4"
    assert call_args[1]["ExtraArgs"]["ContentType"] == "video/mp4"
    assert call_args[1]["ExtraArgs"]["StorageClass"] == "STANDARD"


@pytest.mark.asyncio
async def test_upload_with_prefix(s3_config_with_prefix: S3Config, tmp_path: Path) -> None:
    backend = S3StorageBackend(s3_config_with_prefix)
    backend._session = _mock_s3_session()

    test_file = tmp_path / "test.mp4"
    test_file.write_bytes(b"fake video content")

    result = await backend.upload(test_file, "youtube/abc/test.mp4", "video/mp4")
    assert result == "s3://test-bucket/downloads/youtube/abc/test.mp4"

    mock_client = await backend._session.client.return_value.__aenter__()
    call_args = mock_client.upload_fileobj.call_args
    assert call_args[0][2] == "downloads/youtube/abc/test.mp4"


@pytest.mark.asyncio
async def test_upload_content_type(s3_config: S3Config, tmp_path: Path) -> None:
    backend = S3StorageBackend(s3_config)
    backend._session = _mock_s3_session()

    test_file = tmp_path / "photo.jpg"
    test_file.write_bytes(b"fake image")

    result = await backend.upload(test_file, "instagram/123/photo.jpg", "image/jpeg")
    assert result == "s3://test-bucket/instagram/123/photo.jpg"

    mock_client = await backend._session.client.return_value.__aenter__()
    call_args = mock_client.upload_fileobj.call_args
    assert call_args[1]["ExtraArgs"]["ContentType"] == "image/jpeg"


@pytest.mark.asyncio
async def test_upload_client_kwargs(s3_config: S3Config) -> None:
    backend = S3StorageBackend(s3_config)
    kwargs = backend._build_client_kwargs()
    assert kwargs["region_name"] == "us-east-1"
    assert kwargs["aws_access_key_id"] == "testing"
    assert kwargs["aws_secret_access_key"] == "testing"


@pytest.mark.asyncio
async def test_upload_client_kwargs_minimal() -> None:
    config = S3Config(bucket_name="bucket")
    backend = S3StorageBackend(config)
    kwargs = backend._build_client_kwargs()
    assert kwargs == {"region_name": "us-east-1"}


@pytest.mark.asyncio
async def test_upload_client_kwargs_with_endpoint() -> None:
    config = S3Config(
        bucket_name="bucket",
        endpoint_url="http://localhost:4566",
        aws_access_key_id="key",
        aws_secret_access_key="secret",
    )
    backend = S3StorageBackend(config)
    kwargs = backend._build_client_kwargs()
    assert kwargs["endpoint_url"] == "http://localhost:4566"


@pytest.mark.asyncio
async def test_upload_nonexistent_file(s3_config: S3Config, tmp_path: Path) -> None:
    backend = S3StorageBackend(s3_config)
    nonexistent = tmp_path / "does_not_exist.mp4"

    with pytest.raises(S3UploadError, match="Failed to upload"):
        await backend.upload(nonexistent, "test/key.mp4", "video/mp4")


@pytest.mark.asyncio
async def test_upload_s3_error(s3_config: S3Config, tmp_path: Path) -> None:
    backend = S3StorageBackend(s3_config)
    mock_session = _mock_s3_session()
    mock_client = AsyncMock()
    mock_client.upload_fileobj = AsyncMock(side_effect=RuntimeError("S3 error"))
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    mock_session.client.return_value = mock_context
    backend._session = mock_session

    test_file = tmp_path / "test.mp4"
    test_file.write_bytes(b"content")

    with pytest.raises(S3UploadError, match="Failed to upload"):
        await backend.upload(test_file, "test/key.mp4", "video/mp4")
