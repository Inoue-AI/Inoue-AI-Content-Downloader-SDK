from pathlib import Path

import pytest

from inoue_downloader.storage.local_storage import LocalStorageBackend


@pytest.mark.asyncio
async def test_local_upload(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    backend = LocalStorageBackend(str(output_dir))

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video bytes")

    result = await backend.upload(source, "youtube/abc/video.mp4", "video/mp4")
    dest = Path(result)

    assert dest.exists()
    assert dest.read_bytes() == b"video bytes"
    assert "youtube/abc/video.mp4" in result


@pytest.mark.asyncio
async def test_local_upload_creates_dirs(tmp_path: Path) -> None:
    output_dir = tmp_path / "deep" / "nested" / "output"
    backend = LocalStorageBackend(str(output_dir))

    source = tmp_path / "source.jpg"
    source.write_bytes(b"image bytes")

    result = await backend.upload(source, "instagram/123/photo.jpg", "image/jpeg")
    assert Path(result).exists()


@pytest.mark.asyncio
async def test_local_upload_overwrites(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    backend = LocalStorageBackend(str(output_dir))

    source = tmp_path / "source.mp4"
    source.write_bytes(b"original")
    await backend.upload(source, "test.mp4", "video/mp4")

    source.write_bytes(b"updated")
    result = await backend.upload(source, "test.mp4", "video/mp4")
    assert Path(result).read_bytes() == b"updated"
