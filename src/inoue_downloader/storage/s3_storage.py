from __future__ import annotations

import logging
from pathlib import Path

import aioboto3

from ..config import S3Config
from ..exceptions import S3UploadError
from .base import AbstractStorageBackend

logger = logging.getLogger(__name__)


class S3StorageBackend(AbstractStorageBackend):
    """Storage backend that uploads files to S3 using aioboto3."""

    def __init__(self, config: S3Config) -> None:
        self._config = config
        self._session = aioboto3.Session()

    def _build_client_kwargs(self) -> dict[str, str]:
        kwargs: dict[str, str] = {
            "region_name": self._config.region_name,
        }
        if self._config.aws_access_key_id:
            kwargs["aws_access_key_id"] = self._config.aws_access_key_id.get_secret_value()
        if self._config.aws_secret_access_key:
            kwargs["aws_secret_access_key"] = self._config.aws_secret_access_key.get_secret_value()
        if self._config.aws_session_token:
            kwargs["aws_session_token"] = self._config.aws_session_token.get_secret_value()
        if self._config.endpoint_url:
            kwargs["endpoint_url"] = self._config.endpoint_url
        return kwargs

    async def upload(self, local_path: Path, key: str, mime_type: str) -> str:
        full_key = f"{self._config.prefix}{key}" if self._config.prefix else key
        try:
            async with self._session.client("s3", **self._build_client_kwargs()) as s3:
                with open(local_path, "rb") as fp:
                    await s3.upload_fileobj(
                        fp,
                        self._config.bucket_name,
                        full_key,
                        ExtraArgs={
                            "ContentType": mime_type,
                            "StorageClass": self._config.storage_class,
                        },
                    )
            s3_url = f"s3://{self._config.bucket_name}/{full_key}"
            logger.info("Uploaded %s to %s", local_path.name, s3_url)
            return s3_url
        except S3UploadError:
            raise
        except Exception as e:
            raise S3UploadError(f"Failed to upload {local_path} to S3: {e}") from e
