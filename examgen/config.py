"""Runtime configuration for EXAMGEN AI.

Configuration is environment driven so the same code runs in tests, local
development and deployment without modification.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    """Application settings resolved from the environment."""

    data_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("EXAMGEN_DATA_DIR", "./data")).resolve())
    database_url: str = field(default_factory=lambda: os.environ.get(
        "EXAMGEN_DATABASE_URL", ""))
    secret_key: str = field(default_factory=lambda: os.environ.get(
        "EXAMGEN_SECRET_KEY", ""))
    access_token_ttl_minutes: int = field(
        default_factory=lambda: _env_int("EXAMGEN_TOKEN_TTL_MINUTES", 720))
    max_upload_mb: int = field(
        default_factory=lambda: _env_int("EXAMGEN_MAX_UPLOAD_MB", 50))

    # LLM integration is optional. When no key is configured the platform uses
    # a deterministic, offline generation engine so the full workflow remains
    # functional without external services.
    llm_api_key: str = field(default_factory=lambda: os.environ.get(
        "EXAMGEN_LLM_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.environ.get(
        "EXAMGEN_LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_model: str = field(default_factory=lambda: os.environ.get(
        "EXAMGEN_LLM_MODEL", "gpt-4o-mini"))
    allow_supplementary_knowledge: bool = field(
        default_factory=lambda: _env_bool("EXAMGEN_ALLOW_SUPPLEMENTARY", False))

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "assets").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "pdf").mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'examgen.db'}"
        if not self.secret_key:
            # A per-process key keeps local/dev sessions working. Deployments
            # must set EXAMGEN_SECRET_KEY so tokens survive restarts.
            import secrets

            self.secret_key = os.environ.get(
                "EXAMGEN_SECRET_KEY") or secrets.token_urlsafe(48)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Testing helper — forces settings to be re-read from the environment."""
    global _settings
    _settings = None
