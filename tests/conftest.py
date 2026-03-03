import tempfile
from pathlib import Path

import pytest

from inoue_downloader import DownloaderConfig, S3Config


@pytest.fixture
def s3_config() -> S3Config:
    return S3Config(
        bucket_name="test-bucket",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )


@pytest.fixture
def downloader_config(s3_config: S3Config) -> DownloaderConfig:
    return DownloaderConfig(s3=s3_config)


@pytest.fixture
def local_config(tmp_path: Path) -> DownloaderConfig:
    return DownloaderConfig(local_output_dir=str(tmp_path / "output"))


@pytest.fixture
def temp_dir() -> Path:
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)  # type: ignore[misc]
