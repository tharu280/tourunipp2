from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from clean_run.storage import build_mongo_database_from_env


class DuplicateEmailError(ValueError):
    pass


class AuthRepository:
    def __init__(self, database: Any) -> None:
        self.users = database["users"]
        self.refresh_tokens = database["refresh_tokens"]
        self._indexes_ensured = False

    def ensure_indexes(self) -> None:
        if self._indexes_ensured:
            return
        self.users.create_index("user_id", unique=True)
        self.users.create_index("email", unique=True)
        self.refresh_tokens.create_index("token_hash", unique=True)
        self.refresh_tokens.create_index("user_id")
        self.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)
        self._indexes_ensured = True

    def create_user(self, document: dict[str, Any]) -> dict[str, Any]:
        self.ensure_indexes()
        try:
            self.users.insert_one(document)
        except Exception as exc:
            if exc.__class__.__name__ == "DuplicateKeyError" or "duplicate key" in str(exc).lower():
                raise DuplicateEmailError("An account already exists for this email.") from exc
            raise
        return document

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        self.ensure_indexes()
        return self.users.find_one({"email": email})

    def find_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        self.ensure_indexes()
        return self.users.find_one({"user_id": user_id})

    def update_password_hash(self, user_id: str, password_hash: str) -> None:
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {"password_hash": password_hash}},
        )

    def store_refresh_token(self, document: dict[str, Any]) -> None:
        self.ensure_indexes()
        self.refresh_tokens.insert_one(document)

    def consume_refresh_token(self, token_hash: str, now: datetime) -> dict[str, Any] | None:
        self.ensure_indexes()
        document = self.refresh_tokens.find_one(
            {"token_hash": token_hash, "revoked_at": None, "expires_at": {"$gt": now}}
        )
        if document is None:
            return None
        result = self.refresh_tokens.update_one(
            {"token_hash": token_hash, "revoked_at": None},
            {"$set": {"revoked_at": now}},
        )
        if not getattr(result, "matched_count", 0):
            return None
        return document

    def revoke_refresh_token(self, token_hash: str) -> None:
        self.ensure_indexes()
        self.refresh_tokens.update_one(
            {"token_hash": token_hash, "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(timezone.utc)}},
        )


def build_auth_repository_from_env() -> AuthRepository | None:
    database = build_mongo_database_from_env()
    if database is None:
        return None
    return AuthRepository(database)
