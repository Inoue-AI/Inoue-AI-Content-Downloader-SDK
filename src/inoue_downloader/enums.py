from enum import StrEnum


class Platform(StrEnum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"


class DownloadProvider(StrEnum):
    YTDLP = "ytdlp"
    APIFY = "apify"
    SSSINSTAGRAM = "sssinstagram"
    SNAPINSTA = "snapinsta"
    INSTAGRAPI = "instagrapi"
    SSSTIK = "ssstik"


class ContentType(StrEnum):
    VIDEO = "video"
    IMAGE = "image"
    CAROUSEL = "carousel"
    AUDIO = "audio"
    STORY = "story"
    REEL = "reel"


class DownloadStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
