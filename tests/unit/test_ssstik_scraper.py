from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inoue_downloader.enums import ContentType, Platform
from inoue_downloader.exceptions import ScraperError
from inoue_downloader.scrapers.ssstik import SsstikScraper

FAKE_PAGE_HTML = """
<html>
<script>s_tt = 'abc123token'</script>
</html>
"""

FAKE_DOWNLOAD_HTML = """
<div id="mainpicture">
  <p class="maintext">Funny dance video #fyp</p>
  <p class="subtext">@coolcreator</p>
</div>
<a href="https://tikcdn.io/ssstik/123456?st=abc&e=999">Without watermark</a>
<a href="https://tikcdn.io/ssstik/m/base64encoded">Download MP3</a>
"""


class TestSsstikScraper:
    def test_extract_download_url(self) -> None:
        url = SsstikScraper._extract_download_url(FAKE_DOWNLOAD_HTML)
        assert url == "https://tikcdn.io/ssstik/123456?st=abc&e=999"

    def test_extract_download_url_no_links(self) -> None:
        with pytest.raises(ScraperError, match="No download URL"):
            SsstikScraper._extract_download_url("<html><body>no links</body></html>")

    def test_extract_metadata_from_html(self) -> None:
        meta = SsstikScraper._extract_metadata_from_html(
            FAKE_DOWNLOAD_HTML,
            "https://www.tiktok.com/@user/video/7123456789",
        )
        assert meta.platform == Platform.TIKTOK
        assert meta.content_type == ContentType.VIDEO
        assert meta.title == "Funny dance video #fyp"
        assert meta.author == "@coolcreator"
        assert meta.source_id == "7123456789"

    def test_extract_metadata_no_video_id(self) -> None:
        meta = SsstikScraper._extract_metadata_from_html(
            FAKE_DOWNLOAD_HTML,
            "https://vm.tiktok.com/abcdef/",
        )
        assert meta.source_id == "abcdef"

    @pytest.mark.asyncio
    async def test_download_success(self, tmp_path: Path) -> None:
        scraper = SsstikScraper()

        mock_get_page = AsyncMock()
        mock_get_page.__aenter__ = AsyncMock(return_value=mock_get_page)
        mock_get_page.__aexit__ = AsyncMock(return_value=False)
        mock_get_page.status = 200
        mock_get_page.text = AsyncMock(return_value=FAKE_PAGE_HTML)

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_post)
        mock_post.__aexit__ = AsyncMock(return_value=False)
        mock_post.status = 200
        mock_post.text = AsyncMock(return_value=FAKE_DOWNLOAD_HTML)

        mock_download = AsyncMock()
        mock_download.__aenter__ = AsyncMock(return_value=mock_download)
        mock_download.__aexit__ = AsyncMock(return_value=False)
        mock_download.status = 200
        mock_download.read = AsyncMock(return_value=b"fake video bytes")

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=[mock_get_page, mock_download])
        mock_session.post = MagicMock(return_value=mock_post)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "inoue_downloader.scrapers.ssstik.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            metadata, files = await scraper.download(
                "https://www.tiktok.com/@user/video/7123456789", tmp_path
            )

        assert metadata.platform == Platform.TIKTOK
        assert metadata.source_id == "7123456789"
        assert len(files) == 1
        assert files[0].exists()
        assert files[0].read_bytes() == b"fake video bytes"

    @pytest.mark.asyncio
    async def test_download_token_extraction_failure(self, tmp_path: Path) -> None:
        scraper = SsstikScraper()

        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value="<html>no token here</html>")

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "inoue_downloader.scrapers.ssstik.aiohttp.ClientSession",
                return_value=mock_session,
            ),
            pytest.raises(ScraperError, match=r"Could not extract ssstik\.io token"),
        ):
            await scraper.download("https://www.tiktok.com/@user/video/123", tmp_path)

    @pytest.mark.asyncio
    async def test_download_empty_content(self, tmp_path: Path) -> None:
        scraper = SsstikScraper()

        mock_get_page = AsyncMock()
        mock_get_page.__aenter__ = AsyncMock(return_value=mock_get_page)
        mock_get_page.__aexit__ = AsyncMock(return_value=False)
        mock_get_page.status = 200
        mock_get_page.text = AsyncMock(return_value=FAKE_PAGE_HTML)

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_post)
        mock_post.__aexit__ = AsyncMock(return_value=False)
        mock_post.status = 200
        mock_post.text = AsyncMock(return_value=FAKE_DOWNLOAD_HTML)

        mock_download = AsyncMock()
        mock_download.__aenter__ = AsyncMock(return_value=mock_download)
        mock_download.__aexit__ = AsyncMock(return_value=False)
        mock_download.status = 200
        mock_download.read = AsyncMock(return_value=b"")

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=[mock_get_page, mock_download])
        mock_session.post = MagicMock(return_value=mock_post)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "inoue_downloader.scrapers.ssstik.aiohttp.ClientSession",
                return_value=mock_session,
            ),
            pytest.raises(ScraperError, match="Downloaded empty file"),
        ):
            await scraper.download("https://www.tiktok.com/@user/video/123", tmp_path)


class TestSsstikWithProxy:
    def test_proxy_url_https(self) -> None:
        from inoue_downloader.config import ProxyConfig

        proxy = ProxyConfig(http="http://proxy:8080", https="https://proxy:8443")
        scraper = SsstikScraper(proxy=proxy)
        assert scraper._proxy_url() == "https://proxy:8443"

    def test_proxy_url_http_fallback(self) -> None:
        from inoue_downloader.config import ProxyConfig

        proxy = ProxyConfig(http="http://proxy:8080")
        scraper = SsstikScraper(proxy=proxy)
        assert scraper._proxy_url() == "http://proxy:8080"

    def test_proxy_url_none(self) -> None:
        scraper = SsstikScraper()
        assert scraper._proxy_url() is None
