from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr, model_validator

from .enums import DownloadProvider


class S3Config(BaseModel):
    """Configuration for S3 upload destination."""

    bucket_name: str
    prefix: str = ""
    aws_access_key_id: SecretStr | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_session_token: SecretStr | None = None
    region_name: str = "us-east-1"
    endpoint_url: str | None = None
    storage_class: str = "STANDARD"


class InstagramCredentials(BaseModel):
    """Optional Instagram authentication credentials."""

    username: str
    password: SecretStr
    two_factor_seed: str | None = None
    session_file_path: str | None = None


class ApifyConfig(BaseModel):
    """Configuration for Apify download provider."""

    api_key: SecretStr
    youtube_actor: str = "streamers/youtube-scraper"
    tiktok_actor: str = "clockworks/free-tiktok-scraper"
    instagram_actor: str = "apify/instagram-scraper"
    timeout: int = Field(default=300, ge=10, description="Actor run timeout in seconds")


class ProxyConfig(BaseModel):
    """Proxy configuration for web scraping requests."""

    http: str | None = None
    https: str | None = None


class DownloaderConfig(BaseModel):
    """Main SDK configuration."""

    provider: DownloadProvider = DownloadProvider.YTDLP
    s3: S3Config | None = None
    local_output_dir: str | None = None
    instagram: InstagramCredentials | None = None
    apify: ApifyConfig | None = None
    proxy: ProxyConfig | None = None
    max_concurrent_downloads: int = Field(default=3, ge=1, le=20)
    request_timeout: int = Field(default=300, ge=10)
    max_file_size_mb: int | None = None
    preferred_video_quality: str = "best"
    temp_dir: str | None = None
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_storage_target(self) -> DownloaderConfig:
        if self.s3 is None and self.local_output_dir is None:
            raise ValueError(
                "Either 's3' or 'local_output_dir' must be configured. "
                "The SDK needs a storage destination for downloaded files."
            )
        return self

    @model_validator(mode="after")
    def validate_apify_config(self) -> DownloaderConfig:
        if self.provider == DownloadProvider.APIFY and self.apify is None:
            raise ValueError(
                "ApifyConfig must be provided when using the APIFY provider. "
                "Set 'apify=ApifyConfig(api_key=\"...\")' in your config."
            )
        return self

    @model_validator(mode="after")
    def validate_instagrapi_config(self) -> DownloaderConfig:
        if self.provider == DownloadProvider.INSTAGRAPI and self.instagram is None:
            raise ValueError(
                "InstagramCredentials must be provided when using the INSTAGRAPI provider. "
                'Set \'instagram=InstagramCredentials(username="...", password="...")\' '
                "in your config."
            )
        return self
