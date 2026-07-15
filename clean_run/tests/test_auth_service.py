from __future__ import annotations

from datetime import datetime
import unittest

from clean_run.auth.config import AuthSettings
from clean_run.auth.repository import DuplicateEmailError
from clean_run.auth.security import InvalidAccessTokenError, decode_access_token
from clean_run.auth.service import AuthService, InvalidCredentialsError, InvalidRefreshTokenError


class FakeAuthRepository:
    def __init__(self) -> None:
        self.users_by_email: dict[str, dict] = {}
        self.users_by_id: dict[str, dict] = {}
        self.tokens: dict[str, dict] = {}

    def create_user(self, document: dict) -> dict:
        if document["email"] in self.users_by_email:
            raise DuplicateEmailError("An account already exists for this email.")
        self.users_by_email[document["email"]] = document
        self.users_by_id[document["user_id"]] = document
        return document

    def find_user_by_email(self, email: str):
        return self.users_by_email.get(email)

    def find_user_by_id(self, user_id: str):
        return self.users_by_id.get(user_id)

    def update_password_hash(self, user_id: str, password_hash: str) -> None:
        self.users_by_id[user_id]["password_hash"] = password_hash

    def store_refresh_token(self, document: dict) -> None:
        self.tokens[document["token_hash"]] = document

    def consume_refresh_token(self, token_hash: str, now: datetime):
        document = self.tokens.get(token_hash)
        if (
            document is None
            or document.get("revoked_at") is not None
            or document["expires_at"] <= now
        ):
            return None
        document["revoked_at"] = now
        return document

    def revoke_refresh_token(self, token_hash: str) -> None:
        document = self.tokens.get(token_hash)
        if document is not None and document.get("revoked_at") is None:
            document["revoked_at"] = datetime.now(document["expires_at"].tzinfo)


def build_service() -> tuple[AuthService, FakeAuthRepository]:
    repository = FakeAuthRepository()
    settings = AuthSettings(
        jwt_secret="test-secret-that-is-longer-than-thirty-two-characters",
        cookie_secure=False,
    )
    return AuthService(repository, settings), repository


class AuthServiceTests(unittest.TestCase):
    def test_signup_login_access_token_and_duplicate_email(self) -> None:
        service, repository = build_service()

        signup, _ = service.signup(
            name="Test Traveller",
            email="traveller@example.com",
            password="correct horse battery staple",
        )

        self.assertEqual(signup["user"]["email"], "traveller@example.com")
        self.assertNotIn("password_hash", signup["user"])
        self.assertNotEqual(
            repository.users_by_email["traveller@example.com"]["password_hash"],
            "correct horse battery staple",
        )
        payload = decode_access_token(signup["access_token"], service.settings)
        self.assertEqual(payload["sub"], signup["user"]["user_id"])
        self.assertEqual(
            service.user_from_access_token(signup["access_token"])["email"],
            "traveller@example.com",
        )

        login, _ = service.login(
            email="traveller@example.com",
            password="correct horse battery staple",
        )
        self.assertEqual(login["user"]["user_id"], signup["user"]["user_id"])

        with self.assertRaises(DuplicateEmailError):
            service.signup(
                name="Duplicate",
                email="traveller@example.com",
                password="another secure password",
            )
        with self.assertRaises(InvalidCredentialsError):
            service.login(email="traveller@example.com", password="wrong")

    def test_refresh_tokens_rotate_and_logout_revokes(self) -> None:
        service, _ = build_service()
        _, original_refresh = service.signup(
            name="Test Traveller",
            email="traveller@example.com",
            password="correct horse battery staple",
        )

        refreshed, rotated_refresh = service.refresh(original_refresh)
        self.assertTrue(refreshed["access_token"])
        self.assertNotEqual(original_refresh, rotated_refresh)
        with self.assertRaises(InvalidRefreshTokenError):
            service.refresh(original_refresh)

        service.logout(rotated_refresh)
        with self.assertRaises(InvalidRefreshTokenError):
            service.refresh(rotated_refresh)

    def test_invalid_access_token_is_rejected(self) -> None:
        service, _ = build_service()
        with self.assertRaises(InvalidAccessTokenError):
            service.user_from_access_token("not-a-jwt")


if __name__ == "__main__":
    unittest.main()
