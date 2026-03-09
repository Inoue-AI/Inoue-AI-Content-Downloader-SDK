"""Tests for ContentMetadata.source_id sanitization.

Ensures that source_id is always safe for use in filenames and S3 keys,
regardless of what scrapers pass in.
"""

import re

from inoue_downloader.enums import ContentType, Platform
from inoue_downloader.models import ContentMetadata

_COMMON = dict(
    platform=Platform.TIKTOK,
    content_type=ContentType.VIDEO,
    original_url="https://example.com/video/123",
)

_SAFE_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class TestSourceIdSanitization:
    def test_normal_id_unchanged(self) -> None:
        meta = ContentMetadata(**_COMMON, source_id="7123456789")
        assert meta.source_id == "7123456789"

    def test_alphanumeric_with_hyphens_unchanged(self) -> None:
        meta = ContentMetadata(**_COMMON, source_id="ZNRufq2ex")
        assert meta.source_id == "ZNRufq2ex"

    def test_underscore_id_unchanged(self) -> None:
        meta = ContentMetadata(**_COMMON, source_id="ABC_123-def")
        assert meta.source_id == "ABC_123-def"

    def test_full_url_hashed(self) -> None:
        meta = ContentMetadata(**_COMMON, source_id="https://vm.tiktok.com/ZNRufq2ex/")
        assert _SAFE_RE.match(meta.source_id)
        assert len(meta.source_id) == 16

    def test_url_hash_is_deterministic(self) -> None:
        url = "https://www.instagram.com/reel/ABC123/"
        a = ContentMetadata(**_COMMON, source_id=url)
        b = ContentMetadata(**_COMMON, source_id=url)
        assert a.source_id == b.source_id

    def test_slashes_produce_hash(self) -> None:
        meta = ContentMetadata(**_COMMON, source_id="some/bad/id")
        assert "/" not in meta.source_id
        assert _SAFE_RE.match(meta.source_id)

    def test_special_characters_produce_hash(self) -> None:
        meta = ContentMetadata(**_COMMON, source_id="id?with&special=chars")
        assert _SAFE_RE.match(meta.source_id)

    def test_path_traversal_produces_hash(self) -> None:
        meta = ContentMetadata(**_COMMON, source_id="../../etc/passwd")
        assert "/" not in meta.source_id
        assert ".." not in meta.source_id
        assert _SAFE_RE.match(meta.source_id)

    def test_long_safe_id_unchanged(self) -> None:
        long_id = "a" * 200
        meta = ContentMetadata(**_COMMON, source_id=long_id)
        assert meta.source_id == long_id

    def test_over_200_chars_hashed(self) -> None:
        meta = ContentMetadata(**_COMMON, source_id="a" * 201)
        assert len(meta.source_id) == 16
