from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from clean_run.api import app
from clean_run.auth.config import AuthSettings
from clean_run.auth.router import get_auth_service
from clean_run.auth.service import AuthService
from clean_run.tests.test_auth_service import FakeAuthRepository


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions_by_user: dict[str, dict] = {}

    def get_latest_session_for_user(self, user_id: str) -> dict | None:
        return self.sessions_by_user.get(user_id)


class AuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeAuthRepository()
        self.service = AuthService(
            self.repository,
            AuthSettings(
                jwt_secret="api-test-secret-that-is-longer-than-thirty-two-characters",
                refresh_cookie_name="custom_refresh_cookie",
                cookie_secure=False,
            ),
        )
        app.dependency_overrides[get_auth_service] = lambda: self.service
        # The router uses its local service factory rather than Depends, so replace its cache too.
        import clean_run.auth.router as auth_router_module

        self.auth_router_module = auth_router_module
        self.original_service_factory = auth_router_module.get_auth_service
        auth_router_module.get_auth_service = lambda: self.service

        import clean_run.api as api_module

        self.api_module = api_module
        self.session_repository = FakeSessionRepository()
        self.original_session_repository_factory = api_module.get_session_repository
        api_module.get_session_repository = lambda: self.session_repository
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.auth_router_module.get_auth_service = self.original_service_factory
        self.api_module.get_session_repository = self.original_session_repository_factory
        app.dependency_overrides.clear()

    def test_complete_browser_session_lifecycle(self) -> None:
        signup = self.client.post(
            "/auth/signup",
            json={
                "name": "Test Traveller",
                "email": "Traveller@Example.com",
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(signup.status_code, 201)
        self.assertEqual(signup.json()["user"]["email"], "traveller@example.com")
        cookie = signup.headers["set-cookie"].lower()
        self.assertIn("custom_refresh_cookie=", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertIn("path=/", cookie)

        access_token = signup.json()["access_token"]
        me = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["name"], "Test Traveller")

        refresh = self.client.post("/auth/refresh")
        self.assertEqual(refresh.status_code, 200)
        self.assertNotEqual(refresh.json()["access_token"], access_token)

        logout = self.client.post("/auth/logout")
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(self.client.post("/auth/refresh").status_code, 401)

    def test_duplicate_signup_and_wrong_password_are_rejected(self) -> None:
        body = {
            "name": "Test Traveller",
            "email": "traveller@example.com",
            "password": "correct horse battery staple",
        }
        self.assertEqual(self.client.post("/auth/signup", json=body).status_code, 201)
        self.assertEqual(self.client.post("/auth/signup", json=body).status_code, 409)
        wrong_login = self.client.post(
            "/auth/login",
            json={"email": body["email"], "password": "wrong password"},
        )
        self.assertEqual(wrong_login.status_code, 401)

    def test_latest_session_requires_authentication(self) -> None:
        response = self.client.get("/sessions/latest")

        self.assertEqual(response.status_code, 401)

    def test_latest_session_returns_current_users_saved_plan(self) -> None:
        signup = self.client.post(
            "/auth/signup",
            json={
                "name": "Returning Traveller",
                "email": "returning@example.com",
                "password": "correct horse battery staple",
            },
        )
        payload = signup.json()
        user_id = payload["user"]["user_id"]
        self.session_repository.sessions_by_user[user_id] = {
            "session_id": "saved-session-123",
            "status": "planned",
            "updated_at": "2026-07-16T08:30:00+00:00",
            "trip_requirements": {
                "origin": "Colombo",
                "destination": "Kandy",
            },
        }

        response = self.client.get(
            "/sessions/latest",
            headers={"Authorization": f"Bearer {payload['access_token']}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_id"], "saved-session-123")
        self.assertEqual(response.json()["trip_requirements"]["destination"], "Kandy")

    def test_latest_session_returns_null_when_user_has_no_plan(self) -> None:
        signup = self.client.post(
            "/auth/signup",
            json={
                "name": "New Traveller",
                "email": "new@example.com",
                "password": "correct horse battery staple",
            },
        )

        response = self.client.get(
            "/sessions/latest",
            headers={"Authorization": f"Bearer {signup.json()['access_token']}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["session_id"])


if __name__ == "__main__":
    unittest.main()
