"""Web scraper fallbacks for platforms where yt-dlp requires authentication."""

from .base import AbstractScraper
from .snapinsta import SnapinstaScraper
from .sssinstagram import SssinstagramScraper
from .ssstik import SsstikScraper

__all__ = ["AbstractScraper", "SnapinstaScraper", "SssinstagramScraper", "SsstikScraper"]
