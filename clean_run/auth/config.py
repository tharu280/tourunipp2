from __future__ import annotations

from dataclasses import dataclass
import os


class AuthConfigurationError(RuntimeError):
    pass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: str
    jwt_issuer: str = "touruni-api"
    jwt_audience: str = "touruni-pwa"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    refresh_cookie_name: str = "touruni_refresh_token"
    cookie_secure: bool = True
    cookie_domain: str | None = None

    @classmethod
    def from_env(cls) -> "AuthSettings":
        secret = (os.getenv("JWT_SECRET") or "").strip()
        if len(secret) < 32:
            raise AuthConfigurationError(
                "JWT_SECRET must be configured with at least 32 random characters."
            )
        return cls(
            jwt_secret=secret,
            jwt_issuer=os.getenv("JWT_ISSUER", "touruni-api"),
            jwt_audience=os.getenv("JWT_AUDIENCE", "touruni-pwa"),
            access_token_minutes=max(1, int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))),
            refresh_token_days=max(1, int(os.getenv("REFRESH_TOKEN_DAYS", "30"))),
            refresh_cookie_name=os.getenv("REFRESH_COOKIE_NAME", "touruni_refresh_token"),
            cookie_secure=_env_bool("COOKIE_SECURE", True),
            cookie_domain=(os.getenv("COOKIE_DOMAIN") or "").strip() or None,
        )

    @property
    def refresh_cookie_max_age(self) -> int:
        return self.refresh_token_days * 24 * 60 * 60

    @property
    def refresh_cookie_samesite(self) -> str:
        return "none" if self.cookie_secure else "lax"
