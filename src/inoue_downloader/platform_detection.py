from __future__ import annotations

import re

from .enums import Platform
from .exceptions import UnsupportedPlatformError

_PLATFORM_PATTERNS: list[tuple[Platform, list[re.Pattern[str]]]] = [
    (
        Platform.YOUTUBE,
        [
            re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/"),
            re.compile(r"(?:https?://)?youtu\.be/"),
            re.compile(r"(?:https?://)?m\.youtube\.com/"),
        ],
    ),
    (
        Platform.TIKTOK,
        [
            re.compile(r"(?:https?://)?(?:www\.)?tiktok\.com/"),
            re.compile(r"(?:https?://)?vm\.tiktok\.com/"),
        ],
    ),
    (
        Platform.INSTAGRAM,
        [
            re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/"),
        ],
    ),
]


def detect_platform(url: str) -> Platform:
    """Detect which platform a URL belongs to.

    Raises:
        UnsupportedPlatformError: If the URL doesn't match any known platform.
    """
    normalized = url.strip()
    for platform, patterns in _PLATFORM_PATTERNS:
        for pattern in patterns:
            if pattern.search(normalized):
                return platform
    raise UnsupportedPlatformError(f"Cannot detect platform for URL: {url}")
