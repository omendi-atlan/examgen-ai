"""Typed environment configuration for the Python API."""

from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings; secrets are read from the environment, never source code."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "EXAMGEN AI API"
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./examgen.db"
    api_v1_prefix: str = "/api/v1"
    auth_secret_key: SecretStr = SecretStr(
        "development-only-change-this-secret-before-deploy"
    )
    access_token_ttl_minutes: int = 15
    jwt_issuer: str = "examgen-ai"
    document_storage_path: str = "./data/documents"\n    document_storage_backend: str = "local"\n    object_storage_bucket: str | None = None\n    object_storage_region: str = "af-south-1"\n    object_storage_endpoint_url: str | None = None\n    object_storage_access_key: SecretStr | None = None\n    object_storage_secret_key: SecretStr | None = None
    max_document_upload_bytes: int = 20000000
    cors_allowed_origins: str = "http://localhost:3000"
    malware_scan_enabled: bool = False
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 30
    document_job_lease_seconds: int = 3600
    max_pdf_pages: int = 100
    max_pdf_page_pixels: int = 20000000
    ocr_page_timeout_seconds: int = 15
    max_extracted_characters: int = 10000000
    max_office_archive_ratio: int = 100

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        """Reject insecure signing and upload configuration."""
        secret = self.auth_secret_key.get_secret_value()
        if len(secret) < 32:
            raise ValueError("AUTH_SECRET_KEY must contain at least 32 characters.")
        if self.environment.lower() == "production" and secret.startswith(
            "development-only-"
        ):
            raise ValueError("A production AUTH_SECRET_KEY must be explicitly configured.")
        if self.document_storage_backend not in {"local", "s3"}:\n            raise ValueError("DOCUMENT_STORAGE_BACKEND must be local or s3.")\n        if self.document_storage_backend == "s3" and not self.object_storage_bucket:\n            raise ValueError("OBJECT_STORAGE_BUCKET is required when S3 storage is enabled.")\n        if self.document_storage_backend == "s3" and bool(self.object_storage_access_key) != bool(self.object_storage_secret_key):\n            raise ValueError("S3 access key and secret key must be configured together.")\n        if not 1 <= self.access_token_ttl_minutes <= 60:
            raise ValueError("ACCESS_TOKEN_TTL_MINUTES must be between 1 and 60.")
        if not 1024 <= self.max_document_upload_bytes <= 104857600:
            raise ValueError("MAX_DOCUMENT_UPLOAD_BYTES must be between 1 KiB and 100 MiB.")
        if self.environment.lower() == "production" and not self.malware_scan_enabled:
            raise ValueError("MALWARE_SCAN_ENABLED must be enabled in production.")
        if not 1 <= self.clamav_port <= 65535 or not 1 <= self.clamav_timeout_seconds <= 120:
            raise ValueError("ClamAV connection settings are outside permitted bounds.")
        if not 60 <= self.document_job_lease_seconds <= 86400:
            raise ValueError("DOCUMENT_JOB_LEASE_SECONDS must be between 60 and 86400.")
        if not 1 <= self.max_pdf_pages <= 500 or not 100000 <= self.max_pdf_page_pixels <= 50000000:
            raise ValueError("PDF processing limits are outside permitted bounds.")
        if not 1 <= self.ocr_page_timeout_seconds <= 120:
            raise ValueError("OCR_PAGE_TIMEOUT_SECONDS must be between 1 and 120.")
        if not 1000 <= self.max_extracted_characters <= 50000000:
            raise ValueError("MAX_EXTRACTED_CHARACTERS must be between 1,000 and 50 million.")
        if not 1 <= self.max_office_archive_ratio <= 1000:
            raise ValueError("MAX_OFFICE_ARCHIVE_RATIO must be between 1 and 1,000.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
