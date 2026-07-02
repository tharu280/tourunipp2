from __future__ import annotations

from .mongo_client import build_mongo_collection_from_env
from .session_loader import SessionLoaderService
from .session_repository import SessionRepository


def build_session_repository_from_env() -> SessionRepository | None:
    collection = build_mongo_collection_from_env()
    if collection is None:
        return None
    return SessionRepository(collection)


__all__ = [
    "build_mongo_collection_from_env",
    "build_session_repository_from_env",
    "SessionLoaderService",
    "SessionRepository",
]
