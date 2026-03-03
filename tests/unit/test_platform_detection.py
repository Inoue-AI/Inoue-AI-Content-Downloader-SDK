import pytest

from inoue_downloader.enums import Platform
from inoue_downloader.exceptions import UnsupportedPlatformError
from inoue_downloader.platform_detection import detect_platform


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", Platform.YOUTUBE),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", Platform.YOUTUBE),
        ("https://youtu.be/dQw4w9WgXcQ", Platform.YOUTUBE),
        ("https://youtube.com/shorts/abc123", Platform.YOUTUBE),
        ("https://m.youtube.com/watch?v=test", Platform.YOUTUBE),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", Platform.YOUTUBE),
        ("http://youtube.com/watch?v=test", Platform.YOUTUBE),
        ("https://www.tiktok.com/@user/video/123456", Platform.TIKTOK),
        ("https://tiktok.com/@user/video/123", Platform.TIKTOK),
        ("https://vm.tiktok.com/ZMxxxx/", Platform.TIKTOK),
        ("https://www.tiktok.com/t/ZTtest/", Platform.TIKTOK),
        ("https://www.instagram.com/p/ABC123/", Platform.INSTAGRAM),
        ("https://instagram.com/p/ABC123/", Platform.INSTAGRAM),
        ("https://www.instagram.com/reel/XYZ789/", Platform.INSTAGRAM),
        ("https://www.instagram.com/stories/user/123/", Platform.INSTAGRAM),
        ("https://www.instagram.com/tv/ABC123/", Platform.INSTAGRAM),
    ],
)
def test_detect_platform(url: str, expected: Platform) -> None:
    assert detect_platform(url) == expected


def test_detect_platform_with_whitespace() -> None:
    assert detect_platform("  https://youtu.be/test  ") == Platform.YOUTUBE


def test_detect_platform_unsupported() -> None:
    with pytest.raises(UnsupportedPlatformError, match="Cannot detect platform"):
        detect_platform("https://example.com/video")


def test_detect_platform_empty_string() -> None:
    with pytest.raises(UnsupportedPlatformError):
        detect_platform("")


def test_detect_platform_random_text() -> None:
    with pytest.raises(UnsupportedPlatformError):
        detect_platform("not a url at all")
