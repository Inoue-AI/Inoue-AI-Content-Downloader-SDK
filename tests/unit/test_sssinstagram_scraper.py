from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inoue_downloader.enums import ContentType, Platform
from inoue_downloader.exceptions import ScraperError
from inoue_downloader.scrapers.sssinstagram import (
    SssinstagramScraper,
    _guess_ext,
    _parse_response,
    _sign_request,
)

# ---------------------------------------------------------------------------
# Fixtures: representative API responses
# ---------------------------------------------------------------------------

SINGLE_VIDEO_RESPONSE: dict = {
    "url": [
        {
            "url": "https://scontent.cdninstagram.com/v/video123.mp4?token=abc",
            "type": "video",
            "ext": "mp4",
        }
    ],
    "meta": {
        "title": "Cool reel",
        "username": "testuser",
        "like_count": 42,
    },
    "thumb": "https://scontent.cdninstagram.com/thumb.jpg",
}

SINGLE_IMAGE_RESPONSE: dict = {
    "url": [
        {
            "url": "https://scontent.cdninstagram.com/image.jpg",
            "type": "image",
            "ext": "jpg",
        }
    ],
    "meta": {
        "title": "A photo",
        "username": "photographer",
    },
    "thumb": "https://scontent.cdninstagram.com/thumb.jpg",
}

CAROUSEL_RESPONSE: dict = {
    "url": [
        {"url": "https://cdn.example.com/img1.jpg", "type": "image", "ext": "jpg"},
        {"url": "https://cdn.example.com/img2.jpg", "type": "image", "ext": "jpg"},
        {"url": "https://cdn.example.com/vid1.mp4", "type": "video", "ext": "mp4"},
    ],
    "meta": {
        "title": "Carousel post",
        "username": "multi_poster",
    },
}

MULTI_ITEM_RESPONSE: list = [
    {
        "url": [{"url": "https://cdn.example.com/a.mp4", "type": "video", "ext": "mp4"}],
        "meta": {"title": "First post", "username": "user1"},
    },
    {
        "url": [{"url": "https://cdn.example.com/b.jpg", "type": "image", "ext": "jpg"}],
        "meta": {"title": "Second post", "username": "user1"},
    },
]

ERROR_RESPONSE: dict = {
    "success": False,
    "message": "Content not found",
}


# ===========================================================================
# _sign_request
# ===========================================================================


class TestSignRequest:
    def test_returns_required_fields(self) -> None:
        params = _sign_request("https://instagram.com/p/ABC123/")
        assert "sf_url" in params
        assert "ts" in params
        assert "_ts" in params
        assert "_tsc" in params
        assert "_sv" in params
        assert "_s" in params

    def test_sf_url_matches_input(self) -> None:
        url = "https://instagram.com/reel/XYZ/"
        params = _sign_request(url)
        assert params["sf_url"] == url

    def test_signature_is_hex_digest(self) -> None:
        params = _sign_request("https://instagram.com/p/ABC/")
        sig = params["_s"]
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_signing_version(self) -> None:
        params = _sign_request("https://instagram.com/p/ABC/")
        assert params["_sv"] == "2"
        assert params["_tsc"] == "0"

    def test_different_urls_different_signatures(self) -> None:
        p1 = _sign_request("https://instagram.com/p/AAA/")
        p2 = _sign_request("https://instagram.com/p/BBB/")
        # Signatures should differ (extremely unlikely collision)
        assert p1["_s"] != p2["_s"]


# ===========================================================================
# _parse_response
# ===========================================================================


class TestParseResponse:
    def test_single_video(self) -> None:
        meta, media = _parse_response(SINGLE_VIDEO_RESPONSE, "https://instagram.com/reel/XYZ123/")
        assert meta.platform == Platform.INSTAGRAM
        assert meta.content_type == ContentType.VIDEO
        assert meta.source_id == "XYZ123"
        assert meta.author == "testuser"
        assert meta.title == "Cool reel"
        assert meta.thumbnail_url == "https://scontent.cdninstagram.com/thumb.jpg"
        assert len(media) == 1
        assert "video123" in media[0][0]

    def test_single_image(self) -> None:
        meta, media = _parse_response(SINGLE_IMAGE_RESPONSE, "https://instagram.com/p/IMG001/")
        assert meta.content_type == ContentType.IMAGE
        assert meta.source_id == "IMG001"
        assert len(media) == 1

    def test_carousel(self) -> None:
        meta, media = _parse_response(CAROUSEL_RESPONSE, "https://instagram.com/p/CAR001/")
        assert meta.content_type == ContentType.CAROUSEL
        assert len(media) == 3

    def test_multi_item_list(self) -> None:
        meta, media = _parse_response(
            MULTI_ITEM_RESPONSE, "https://instagram.com/testuser/"
        )
        assert meta.content_type == ContentType.CAROUSEL
        assert meta.author == "user1"
        assert len(media) == 2

    def test_error_response(self) -> None:
        with pytest.raises(ScraperError, match="Content not found"):
            _parse_response(ERROR_RESPONSE, "https://instagram.com/p/ABC/")

    def test_empty_list(self) -> None:
        with pytest.raises(ScraperError, match="empty result"):
            _parse_response([], "https://instagram.com/p/ABC/")

    def test_no_downloadable_media(self) -> None:
        resp = {"url": [], "meta": {}}
        with pytest.raises(ScraperError, match="No downloadable media"):
            _parse_response(resp, "https://instagram.com/p/ABC/")

    def test_profile_url_source_id(self) -> None:
        meta, _ = _parse_response(SINGLE_VIDEO_RESPONSE, "https://instagram.com/someuser/")
        assert meta.source_id == "someuser"

    def test_long_title_truncated(self) -> None:
        resp = dict(SINGLE_VIDEO_RESPONSE)
        resp["meta"] = {"title": "X" * 300, "username": "u"}
        meta, _ = _parse_response(resp, "https://instagram.com/reel/ABC/")
        assert len(meta.title) <= 200


# ===========================================================================
# _guess_ext
# ===========================================================================


class TestGuessExt:
    def test_video_url(self) -> None:
        assert _guess_ext("https://cdn.example.com/v/video.mp4?token=abc", "video") == "mp4"

    def test_image_url(self) -> None:
        assert _guess_ext("https://cdn.example.com/photo.jpg", "image") == "jpg"

    def test_no_extension_video(self) -> None:
        assert _guess_ext("https://cdn.example.com/media/12345", "video") == "mp4"

    def test_no_extension_image(self) -> None:
        assert _guess_ext("https://cdn.example.com/media/12345", "image") == "jpg"

    def test_long_extension_ignored(self) -> None:
        assert _guess_ext("https://cdn.example.com/file.toolongext", "video") == "mp4"

    def test_webm_extension(self) -> None:
        assert _guess_ext("https://cdn.example.com/video.webm", "video") == "webm"


# ===========================================================================
# SssinstagramScraper
# ===========================================================================


class TestSssinstagramScraper:
    @pytest.mark.asyncio
    async def test_download_single_video(self, tmp_path: Path) -> None:
        scraper = SssinstagramScraper()

        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b"fake video data")

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "inoue_downloader.scrapers.sssinstagram._api_post",
                new_callable=AsyncMock,
                return_value=SINGLE_VIDEO_RESPONSE,
            ),
            patch(
                "inoue_downloader.scrapers.sssinstagram.aiohttp.ClientSession",
                return_value=mock_session,
            ),
        ):
            metadata, files = await scraper.download(
                "https://www.instagram.com/reel/ABC123/", tmp_path
            )

        assert metadata.platform == Platform.INSTAGRAM
        assert metadata.content_type == ContentType.VIDEO
        assert metadata.source_id == "ABC123"
        assert len(files) == 1
        assert files[0].exists()
        assert files[0].read_bytes() == b"fake video data"

    @pytest.mark.asyncio
    async def test_download_carousel(self, tmp_path: Path) -> None:
        scraper = SssinstagramScraper()

        responses = [
            _make_download_mock(b"img1 data"),
            _make_download_mock(b"img2 data"),
            _make_download_mock(b"vid1 data"),
        ]

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=responses)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "inoue_downloader.scrapers.sssinstagram._api_post",
                new_callable=AsyncMock,
                return_value=CAROUSEL_RESPONSE,
            ),
            patch(
                "inoue_downloader.scrapers.sssinstagram.aiohttp.ClientSession",
                return_value=mock_session,
            ),
        ):
            metadata, files = await scraper.download(
                "https://www.instagram.com/p/CAR001/", tmp_path
            )

        assert metadata.content_type == ContentType.CAROUSEL
        assert len(files) == 3

    @pytest.mark.asyncio
    async def test_download_api_failure(self, tmp_path: Path) -> None:
        scraper = SssinstagramScraper()

        with (
            patch(
                "inoue_downloader.scrapers.sssinstagram._api_post",
                new_callable=AsyncMock,
                side_effect=ScraperError("API error"),
            ),
            pytest.raises(ScraperError, match="API error"),
        ):
            await scraper.download("https://instagram.com/p/ABC/", tmp_path)

    @pytest.mark.asyncio
    async def test_download_no_media_files(self, tmp_path: Path) -> None:
        """All media downloads fail -> ScraperError."""
        scraper = SssinstagramScraper()

        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.status = 404
        mock_resp.read = AsyncMock(return_value=b"")

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "inoue_downloader.scrapers.sssinstagram._api_post",
                new_callable=AsyncMock,
                return_value=SINGLE_VIDEO_RESPONSE,
            ),
            patch(
                "inoue_downloader.scrapers.sssinstagram.aiohttp.ClientSession",
                return_value=mock_session,
            ),
            pytest.raises(ScraperError, match="Failed to download any files"),
        ):
            await scraper.download("https://instagram.com/reel/ABC/", tmp_path)

    @pytest.mark.asyncio
    async def test_download_output_dir_created(self, tmp_path: Path) -> None:
        scraper = SssinstagramScraper()
        nested = tmp_path / "nested" / "deep"

        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b"data")

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "inoue_downloader.scrapers.sssinstagram._api_post",
                new_callable=AsyncMock,
                return_value=SINGLE_IMAGE_RESPONSE,
            ),
            patch(
                "inoue_downloader.scrapers.sssinstagram.aiohttp.ClientSession",
                return_value=mock_session,
            ),
        ):
            _, files = await scraper.download(
                "https://instagram.com/p/IMG001/", nested
            )

        assert nested.exists()
        assert len(files) == 1


class TestSssinstagramWithProxy:
    def test_proxy_url_https(self) -> None:
        from inoue_downloader.config import ProxyConfig

        proxy = ProxyConfig(https="https://proxy.example.com:8080")
        scraper = SssinstagramScraper(proxy=proxy)
        assert scraper._proxy_url() == "https://proxy.example.com:8080"

    def test_proxy_url_none(self) -> None:
        scraper = SssinstagramScraper()
        assert scraper._proxy_url() is None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_download_mock(content: bytes) -> MagicMock:
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.status = 200
    mock.read = AsyncMock(return_value=content)
    return mock
