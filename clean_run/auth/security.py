from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
import jwt

from .config import AuthSettings


PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


class InvalidAccessTokenError(ValueError):
    pass


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, candidate: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, candidate)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def create_access_token(user_id: str, settings: AuthSettings) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, settings.access_token_minutes * 60


def decode_access_token(token: str, settings: AuthSettings) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "type", "iat", "exp", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError("Access token is invalid or expired.") from exc
    if payload.get("type") != "access":
        raise InvalidAccessTokenError("Access token has the wrong token type.")
    return payload


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
