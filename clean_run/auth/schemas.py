from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class PublicUser(BaseModel):
    user_id: str
    name: str
    email: str
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: PublicUser
