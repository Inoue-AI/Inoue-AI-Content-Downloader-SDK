from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inoue_downloader.enums import ContentType, Platform
from inoue_downloader.exceptions import ScraperError
from inoue_downloader.scrapers.snapinsta import (
    SnapinstaScraper,
    _deobfuscate,
    _extract_media_urls_from_html,
)

FAKE_DECODED_HTML_VIDEO = """
<div class="download-items">
  <a href="https://scontent.cdninstagram.com/v/video123.mp4?token=abc">Download Video</a>
</div>
"""

FAKE_DECODED_HTML_IMAGES = """
<div class="download-items">
  <img src="https://scontent.cdninstagram.com/image1.jpg">
  <img src="https://scontent.cdninstagram.com/image2.jpg">
</div>
"""

FAKE_DECODED_HTML_MIXED = """
<div class="download-items">
  <a href="https://scontent.cdninstagram.com/v/video.mp4?token=abc">Download Video</a>
  <img src="https://scontent.cdninstagram.com/photo.jpg">
</div>
"""

FAKE_PAGE_CONFIG = {
    "k_url_search": "https://snapinsta.to/api/ajaxSearch",
    "k_url_convert": "https://download.ig-12-data.xyz/api/json/convert",
    "k_lang": "en",
    "k_ver": "v2",
    "k_token": "fake_token_abc123",
    "k_exp": "1772166766",
}


class TestDeobfuscate:
    def test_basic_deobfuscation(self) -> None:
        result = _deobfuscate("", 0, "0123456789a", 10, 0)
        assert result == ""


class TestExtractMediaUrls:
    def test_extract_video(self) -> None:
        urls = _extract_media_urls_from_html(FAKE_DECODED_HTML_VIDEO)
        assert len(urls) >= 1
        assert any("video123" in u for u, _ in urls)

    def test_extract_images(self) -> None:
        urls = _extract_media_urls_from_html(FAKE_DECODED_HTML_IMAGES)
        assert len(urls) == 2
        assert all(t == "image" for _, t in urls)

    def test_extract_mixed(self) -> None:
        urls = _extract_media_urls_from_html(FAKE_DECODED_HTML_MIXED)
        assert len(urls) == 2
        types = {t for _, t in urls}
        assert "video" in types
        assert "image" in types

    def test_extract_empty(self) -> None:
        urls = _extract_media_urls_from_html("<html><body>no media</body></html>")
        assert urls == []


class TestSnapinstaScraper:
    def test_extract_download_urls_video(self) -> None:
        urls = SnapinstaScraper._extract_download_urls(FAKE_DECODED_HTML_VIDEO)
        assert len(urls) >= 1
        assert any("video123" in u for u, _ in urls)

    def test_decode_response_plain_html(self) -> None:
        html = '<div><a href="https://example.com/download">Download</a></div>'
        result = SnapinstaScraper._decode_response(html)
        assert "href=" in result

    def test_decode_response_no_params(self) -> None:
        with pytest.raises(ScraperError, match="Could not extract obfuscated"):
            SnapinstaScraper._decode_response("some random javascript without pattern")

    def test_extract_download_urls_from_result_with_html(self) -> None:
        result = {"status": "ok", "data": FAKE_DECODED_HTML_VIDEO}
        urls = SnapinstaScraper._extract_download_urls_from_result(result)
        assert len(urls) >= 1
        assert any("video123" in u for u, _ in urls)

    def test_extract_download_urls_from_result_with_direct_url(self) -> None:
        result = {
            "status": "ok",
            "data": "",
            "video_url": "https://cdn.example.com/video.mp4",
        }
        urls = SnapinstaScraper._extract_download_urls_from_result(result)
        assert len(urls) == 1
        assert urls[0][1] == "video"

    def test_extract_download_urls_from_result_empty(self) -> None:
        result = {"status": "ok", "data": "<html>no media</html>"}
        urls = SnapinstaScraper._extract_download_urls_from_result(result)
        assert urls == []

    @pytest.mark.asyncio
    async def test_download_success_video(self, tmp_path: Path) -> None:
        scraper = SnapinstaScraper()

        # Mock noble-tls session
        mock_session = AsyncMock()

        search_result = {
            "status": "ok",
            "data": FAKE_DECODED_HTML_VIDEO,
        }

        # Mock the download response for the media file
        mock_download_resp = AsyncMock()
        mock_download_resp.__aenter__ = AsyncMock(return_value=mock_download_resp)
        mock_download_resp.__aexit__ = AsyncMock(return_value=False)
        mock_download_resp.status = 200
        mock_download_resp.read = AsyncMock(return_value=b"fake video data")

        mock_dl_session = MagicMock()
        mock_dl_session.get = MagicMock(return_value=mock_download_resp)
        mock_dl_session.__aenter__ = AsyncMock(return_value=mock_dl_session)
        mock_dl_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(
                scraper, "_create_session", new_callable=AsyncMock, return_value=mock_session
            ),
            patch.object(
                scraper,
                "_fetch_page_config",
                new_callable=AsyncMock,
                return_value=FAKE_PAGE_CONFIG,
            ),
            patch.object(
                scraper, "_search", new_callable=AsyncMock, return_value=search_result
            ),
            patch(
                "inoue_downloader.scrapers.snapinsta.aiohttp.ClientSession",
                return_value=mock_dl_session,
            ),
        ):
            metadata, files = await scraper.download(
                "https://www.instagram.com/reel/CsC0Y_1u_bA/", tmp_path
            )

        assert metadata.platform == Platform.INSTAGRAM
        assert metadata.content_type == ContentType.VIDEO
        assert metadata.source_id == "CsC0Y_1u_bA"
        assert len(files) == 1
        assert files[0].exists()
        assert files[0].read_bytes() == b"fake video data"

    @pytest.mark.asyncio
    async def test_download_success_carousel(self, tmp_path: Path) -> None:
        scraper = SnapinstaScraper()

        search_result = {
            "status": "ok",
            "data": FAKE_DECODED_HTML_IMAGES,
        }

        mock_dl_1 = AsyncMock()
        mock_dl_1.__aenter__ = AsyncMock(return_value=mock_dl_1)
        mock_dl_1.__aexit__ = AsyncMock(return_value=False)
        mock_dl_1.status = 200
        mock_dl_1.read = AsyncMock(return_value=b"image1 bytes")

        mock_dl_2 = AsyncMock()
        mock_dl_2.__aenter__ = AsyncMock(return_value=mock_dl_2)
        mock_dl_2.__aexit__ = AsyncMock(return_value=False)
        mock_dl_2.status = 200
        mock_dl_2.read = AsyncMock(return_value=b"image2 bytes")

        mock_dl_session = MagicMock()
        mock_dl_session.get = MagicMock(side_effect=[mock_dl_1, mock_dl_2])
        mock_dl_session.__aenter__ = AsyncMock(return_value=mock_dl_session)
        mock_dl_session.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()

        with (
            patch.object(
                scraper, "_create_session", new_callable=AsyncMock, return_value=mock_session
            ),
            patch.object(
                scraper,
                "_fetch_page_config",
                new_callable=AsyncMock,
                return_value=FAKE_PAGE_CONFIG,
            ),
            patch.object(
                scraper, "_search", new_callable=AsyncMock, return_value=search_result
            ),
            patch(
                "inoue_downloader.scrapers.snapinsta.aiohttp.ClientSession",
                return_value=mock_dl_session,
            ),
        ):
            metadata, files = await scraper.download(
                "https://www.instagram.com/p/ABC123/", tmp_path
            )

        assert metadata.content_type == ContentType.CAROUSEL
        assert len(files) == 2

    @pytest.mark.asyncio
    async def test_download_page_config_failure(self, tmp_path: Path) -> None:
        scraper = SnapinstaScraper()
        mock_session = AsyncMock()

        with (
            patch.object(
                scraper, "_create_session", new_callable=AsyncMock, return_value=mock_session
            ),
            patch.object(
                scraper,
                "_fetch_page_config",
                new_callable=AsyncMock,
                side_effect=ScraperError("Cloudflare challenge could not be bypassed"),
            ),
            pytest.raises(ScraperError, match="Cloudflare"),
        ):
            await scraper.download("https://www.instagram.com/p/ABC/", tmp_path)

    @pytest.mark.asyncio
    async def test_download_no_media_urls(self, tmp_path: Path) -> None:
        scraper = SnapinstaScraper()

        search_result = {
            "status": "ok",
            "data": "<html>no media here</html>",
        }
        mock_session = AsyncMock()

        with (
            patch.object(
                scraper, "_create_session", new_callable=AsyncMock, return_value=mock_session
            ),
            patch.object(
                scraper,
                "_fetch_page_config",
                new_callable=AsyncMock,
                return_value=FAKE_PAGE_CONFIG,
            ),
            patch.object(
                scraper, "_search", new_callable=AsyncMock, return_value=search_result
            ),
            pytest.raises(ScraperError, match="No download URLs"),
        ):
            await scraper.download("https://www.instagram.com/p/ABC/", tmp_path)

    @pytest.mark.asyncio
    async def test_fetch_page_config_success(self) -> None:
        scraper = SnapinstaScraper()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html>
        <script>
        var k_url_search="https://snapinsta.to/api/ajaxSearch",k_lang="en",k_ver="v2";
        </script>
        </html>
        """

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_resp)

        config = await scraper._fetch_page_config(mock_session)
        assert config["k_url_search"] == "https://snapinsta.to/api/ajaxSearch"
        assert config["k_lang"] == "en"

    @pytest.mark.asyncio
    async def test_fetch_page_config_cloudflare_blocked(self) -> None:
        scraper = SnapinstaScraper()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><title>Just a moment...</title></html>"

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(ScraperError, match="Cloudflare"):
            await scraper._fetch_page_config(mock_session)

    @pytest.mark.asyncio
    async def test_search_success(self) -> None:
        scraper = SnapinstaScraper()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "ok",
            "data": FAKE_DECODED_HTML_VIDEO,
        }

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_resp)

        result = await scraper._search(
            mock_session, FAKE_PAGE_CONFIG, "https://instagram.com/p/ABC/"
        )
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_search_turnstile_required(self) -> None:
        scraper = SnapinstaScraper()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "ok",
            "mess": "The authentication token is invalid.",
        }

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(ScraperError, match="Turnstile"):
            await scraper._search(
                mock_session, FAKE_PAGE_CONFIG, "https://instagram.com/p/ABC/"
            )


class TestSnapinstaWithProxy:
    def test_proxy_url_https(self) -> None:
        from inoue_downloader.config import ProxyConfig

        proxy = ProxyConfig(https="https://proxy.example.com:8080")
        scraper = SnapinstaScraper(proxy=proxy)
        assert scraper._proxy_url() == "https://proxy.example.com:8080"

    def test_proxy_url_http_fallback(self) -> None:
        from inoue_downloader.config import ProxyConfig

        proxy = ProxyConfig(http="http://proxy.example.com:8080")
        scraper = SnapinstaScraper(proxy=proxy)
        assert scraper._proxy_url() == "http://proxy.example.com:8080"

    def test_proxy_url_none(self) -> None:
        scraper = SnapinstaScraper()
        assert scraper._proxy_url() is None
