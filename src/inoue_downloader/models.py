from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import ContentType, DownloadStatus, Platform


class ContentMetadata(BaseModel):
    """Metadata extracted from the content URL."""

    platform: Platform
    content_type: ContentType
    title: str | None = None
    description: str | None = None
    author: str | None = None
    author_id: str | None = None
    duration_seconds: float | None = None
    view_count: int | None = None
    like_count: int | None = None
    upload_date: datetime | None = None
    thumbnail_url: str | None = None
    original_url: str
    source_id: str
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class DownloadedFile(BaseModel):
    """Represents a single downloaded file."""

    filename: str
    content_type: ContentType
    file_size_bytes: int
    mime_type: str
    s3_key: str | None = None
    s3_url: str | None = None
    local_path: str | None = None
    checksum_sha256: str | None = None


class DownloadResult(BaseModel):
    """The main result object returned from a download operation."""

    status: DownloadStatus
    source_url: str
    platform: Platform
    metadata: ContentMetadata
    files: list[DownloadedFile]
    elapsed_seconds: float
    error_message: str | None = None

    @property
    def primary_file(self) -> DownloadedFile | None:
        return self.files[0] if self.files else None

    @property
    def s3_urls(self) -> list[str]:
        return [f.s3_url for f in self.files if f.s3_url]
