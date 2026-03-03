import pytest
from pydantic import ValidationError

from inoue_downloader.config import (
    DownloaderConfig,
    InstagramCredentials,
    ProxyConfig,
    S3Config,
)
from inoue_downloader.enums import DownloadProvider


class TestS3Config:
    def test_minimal_config(self) -> None:
        config = S3Config(bucket_name="my-bucket")
        assert config.bucket_name == "my-bucket"
        assert config.region_name == "us-east-1"
        assert config.prefix == ""
        assert config.storage_class == "STANDARD"

    def test_full_config(self) -> None:
        config = S3Config(
            bucket_name="my-bucket",
            prefix="downloads/",
            aws_access_key_id="AKID",
            aws_secret_access_key="SECRET",
            region_name="eu-west-1",
            endpoint_url="http://localhost:4566",
            storage_class="STANDARD_IA",
        )
        assert config.aws_access_key_id.get_secret_value() == "AKID"  # type: ignore[union-attr]
        assert config.endpoint_url == "http://localhost:4566"


class TestInstagramCredentials:
    def test_minimal(self) -> None:
        creds = InstagramCredentials(username="user", password="pass")
        assert creds.username == "user"
        assert creds.password.get_secret_value() == "pass"
        assert creds.session_file_path is None

    def test_with_session_file(self) -> None:
        creds = InstagramCredentials(
            username="user", password="pass", session_file_path="/tmp/session.json"
        )
        assert creds.session_file_path == "/tmp/session.json"


class TestDownloaderConfig:
    def test_requires_storage_target(self) -> None:
        with pytest.raises(ValidationError, match="Either 's3' or 'local_output_dir'"):
            DownloaderConfig()

    def test_s3_config_valid(self) -> None:
        config = DownloaderConfig(s3=S3Config(bucket_name="test"))
        assert config.s3 is not None
        assert config.s3.bucket_name == "test"
        assert config.max_concurrent_downloads == 3
        assert config.request_timeout == 300

    def test_local_config_valid(self) -> None:
        config = DownloaderConfig(local_output_dir="/tmp/output")
        assert config.local_output_dir == "/tmp/output"
        assert config.s3 is None

    def test_both_s3_and_local(self) -> None:
        config = DownloaderConfig(s3=S3Config(bucket_name="test"), local_output_dir="/tmp/output")
        assert config.s3 is not None
        assert config.local_output_dir is not None

    def test_defaults(self) -> None:
        config = DownloaderConfig(s3=S3Config(bucket_name="test"))
        assert config.preferred_video_quality == "best"
        assert config.log_level == "INFO"
        assert config.max_file_size_mb is None
        assert config.temp_dir is None
        assert config.instagram is None

    def test_concurrent_downloads_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DownloaderConfig(s3=S3Config(bucket_name="test"), max_concurrent_downloads=0)
        with pytest.raises(ValidationError):
            DownloaderConfig(s3=S3Config(bucket_name="test"), max_concurrent_downloads=21)

    def test_request_timeout_minimum(self) -> None:
        with pytest.raises(ValidationError):
            DownloaderConfig(s3=S3Config(bucket_name="test"), request_timeout=5)

    def test_proxy_config(self) -> None:
        config = DownloaderConfig(
            s3=S3Config(bucket_name="test"),
            proxy=ProxyConfig(http="http://proxy:8080", https="https://proxy:8443"),
        )
        assert config.proxy is not None
        assert config.proxy.http == "http://proxy:8080"
        assert config.proxy.https == "https://proxy:8443"

    def test_proxy_config_none_by_default(self) -> None:
        config = DownloaderConfig(s3=S3Config(bucket_name="test"))
        assert config.proxy is None

    def test_instagrapi_provider_requires_credentials(self) -> None:
        with pytest.raises(ValidationError, match="InstagramCredentials"):
            DownloaderConfig(
                provider=DownloadProvider.INSTAGRAPI,
                s3=S3Config(bucket_name="test"),
            )

    def test_instagrapi_provider_with_credentials_ok(self) -> None:
        config = DownloaderConfig(
            provider=DownloadProvider.INSTAGRAPI,
            s3=S3Config(bucket_name="test"),
            instagram=InstagramCredentials(username="u", password="p"),
        )
        assert config.provider == DownloadProvider.INSTAGRAPI

    def test_apify_provider_requires_apify_config(self) -> None:
        with pytest.raises(ValidationError, match="ApifyConfig"):
            DownloaderConfig(
                provider=DownloadProvider.APIFY,
                s3=S3Config(bucket_name="test"),
            )

    def test_sssinstagram_provider_no_extra_config_needed(self) -> None:
        config = DownloaderConfig(
            provider=DownloadProvider.SSSINSTAGRAM,
            s3=S3Config(bucket_name="test"),
        )
        assert config.provider == DownloadProvider.SSSINSTAGRAM

    def test_snapinsta_provider_no_extra_config_needed(self) -> None:
        config = DownloaderConfig(
            provider=DownloadProvider.SNAPINSTA,
            s3=S3Config(bucket_name="test"),
        )
        assert config.provider == DownloadProvider.SNAPINSTA

    def test_ssstik_provider_no_extra_config_needed(self) -> None:
        config = DownloaderConfig(
            provider=DownloadProvider.SSSTIK,
            s3=S3Config(bucket_name="test"),
        )
        assert config.provider == DownloadProvider.SSSTIK


class TestProxyConfig:
    def test_minimal(self) -> None:
        proxy = ProxyConfig()
        assert proxy.http is None
        assert proxy.https is None

    def test_http_only(self) -> None:
        proxy = ProxyConfig(http="http://proxy:8080")
        assert proxy.http == "http://proxy:8080"
        assert proxy.https is None

    def test_both(self) -> None:
        proxy = ProxyConfig(http="http://proxy:8080", https="https://proxy:8443")
        assert proxy.http == "http://proxy:8080"
        assert proxy.https == "https://proxy:8443"
