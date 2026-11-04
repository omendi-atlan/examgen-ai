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
    document_storage_path: str = "./data/documents"
    max_document_upload_bytes: int = 26214400

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
        if not 1 <= self.access_token_ttl_minutes <= 60:
            raise ValueError("ACCESS_TOKEN_TTL_MINUTES must be between 1 and 60.")
        if not 1024 <= self.max_document_upload_bytes <= 104857600:
            raise ValueError("MAX_DOCUMENT_UPLOAD_BYTES must be between 1 KiB and 100 MiB.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()
