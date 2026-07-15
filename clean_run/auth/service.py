from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from .config import AuthSettings
from .repository import AuthRepository, DuplicateEmailError
from .security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)


class InvalidCredentialsError(ValueError):
    pass


class InvalidRefreshTokenError(ValueError):
    pass


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    created_at = user.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return {
        "user_id": user["user_id"],
        "name": user["name"],
        "email": user["email"],
        "created_at": str(created_at),
    }


class AuthService:
    def __init__(self, repository: AuthRepository, settings: AuthSettings) -> None:
        self.repository = repository
        self.settings = settings

    def signup(self, *, name: str, email: str, password: str) -> tuple[dict[str, Any], str]:
        now = datetime.now(timezone.utc)
        user = self.repository.create_user(
            {
                "user_id": str(uuid.uuid4()),
                "name": name,
                "email": email,
                "password_hash": hash_password(password),
                "created_at": now,
                "updated_at": now,
                "is_active": True,
            }
        )
        return self._issue_session(user)

    def login(self, *, email: str, password: str) -> tuple[dict[str, Any], str]:
        user = self.repository.find_user_by_email(email)
        if user is None or not user.get("is_active", True):
            raise InvalidCredentialsError("Email or password is incorrect.")
        password_hash = str(user.get("password_hash") or "")
        if not verify_password(password_hash, password):
            raise InvalidCredentialsError("Email or password is incorrect.")
        if password_needs_rehash(password_hash):
            self.repository.update_password_hash(user["user_id"], hash_password(password))
        return self._issue_session(user)

    def refresh(self, raw_refresh_token: str) -> tuple[dict[str, Any], str]:
        now = datetime.now(timezone.utc)
        token_document = self.repository.consume_refresh_token(
            hash_refresh_token(raw_refresh_token), now
        )
        if token_document is None:
            raise InvalidRefreshTokenError("Refresh session is invalid or expired.")
        user = self.repository.find_user_by_id(token_document["user_id"])
        if user is None or not user.get("is_active", True):
            raise InvalidRefreshTokenError("Refresh session is invalid or expired.")
        return self._issue_session(user, family_id=token_document.get("family_id"))

    def logout(self, raw_refresh_token: str | None) -> None:
        if raw_refresh_token:
            self.repository.revoke_refresh_token(hash_refresh_token(raw_refresh_token))

    def user_from_access_token(self, token: str) -> dict[str, Any] | None:
        payload = decode_access_token(token, self.settings)
        user = self.repository.find_user_by_id(str(payload["sub"]))
        if user is None or not user.get("is_active", True):
            return None
        return user

    def _issue_session(
        self,
        user: dict[str, Any],
        *,
        family_id: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        now = datetime.now(timezone.utc)
        access_token, expires_in = create_access_token(user["user_id"], self.settings)
        raw_refresh_token = create_refresh_token()
        self.repository.store_refresh_token(
            {
                "token_hash": hash_refresh_token(raw_refresh_token),
                "user_id": user["user_id"],
                "family_id": family_id or str(uuid.uuid4()),
                "created_at": now,
                "expires_at": now + timedelta(days=self.settings.refresh_token_days),
                "revoked_at": None,
            }
        )
        return (
            {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": expires_in,
                "user": public_user(user),
            },
            raw_refresh_token,
        )


__all__ = [
    "AuthService",
    "DuplicateEmailError",
    "InvalidCredentialsError",
    "InvalidRefreshTokenError",
    "public_user",
]
