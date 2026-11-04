"""Password hashing and signed access-token primitives."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_password_hash = PasswordHash.recommended()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plaintext password using the configured Argon2id recommendation."""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its stored Argon2id hash."""
    return _password_hash.verify(password, password_hash)


def create_access_token(user_id: UUID) -> tuple[str, int]:
    """Issue a short-lived JWT; identity and expiry are server-controlled."""
    settings = get_settings()
    expires_in = settings.access_token_ttl_minutes * 60
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "type": "access",
    }
    token = jwt.encode(
        payload,
        settings.auth_secret_key.get_secret_value(),
        algorithm=_ALGORITHM,
    )
    return token, expires_in


def decode_access_token(token: str) -> UUID:
    """Validate signature, issuer, expiry and token purpose before returning the subject."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.auth_secret_key.get_secret_value(),
        algorithms=[_ALGORITHM],
        issuer=settings.jwt_issuer,
        options={"require": ["sub", "iss", "iat", "exp", "type"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Unsupported token type.")
    return UUID(payload["sub"])
