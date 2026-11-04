"""Fail-closed production configuration validation tests."""

import pytest
from app.core.config import Settings
from pydantic import SecretStr, ValidationError


def test_production_rejects_default_signing_secret() -> None:
    with pytest.raises(ValidationError, match="production AUTH_SECRET_KEY"):
        Settings(environment="production", malware_scan_enabled=True)


def test_production_requires_malware_scanning() -> None:
    with pytest.raises(ValidationError, match="MALWARE_SCAN_ENABLED"):
        Settings(
            environment="production",
            auth_secret_key=SecretStr("a" * 48),
            malware_scan_enabled=False,
        )


def test_s3_requires_bucket_and_paired_credentials() -> None:
    with pytest.raises(ValidationError, match="OBJECT_STORAGE_BUCKET"):
        Settings(document_storage_backend="s3")

    with pytest.raises(ValidationError, match="configured together"):
        Settings(
            document_storage_backend="s3",
            object_storage_bucket="private-examgen",
            object_storage_access_key=SecretStr("access"),
        )


def test_production_accepts_explicit_secret_and_required_scanner() -> None:
    settings = Settings(
        environment="production",
        auth_secret_key=SecretStr("production-signing-secret-" + "x" * 32),
        malware_scan_enabled=True,
    )
    assert settings.environment == "production"
    assert settings.malware_scan_enabled is True


def test_production_rejects_s3_without_server_side_encryption() -> None:
    with pytest.raises(ValidationError, match="server-side encryption"):
        Settings(
            environment="production",
            auth_secret_key=SecretStr("production-signing-secret-" + "x" * 32),
            malware_scan_enabled=True,
            document_storage_backend="s3",
            object_storage_bucket="private-examgen",
            object_storage_server_side_encryption="",
        )


def test_development_allows_minio_without_kms_encryption_header() -> None:
    settings = Settings(
        document_storage_backend="s3",
        object_storage_bucket="local-examgen",
        object_storage_server_side_encryption="",
    )
    assert settings.object_storage_server_side_encryption == ""
