from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / "atlas-credentials.env")
load_dotenv(PACKAGE_ROOT / "atlas-credentials.env")
load_dotenv(PROJECT_ROOT / ".env")


@lru_cache(maxsize=1)
def _build_mongo_client_from_env() -> Any | None:
    """Build (and cache) the process-wide MongoClient.

    A `mongodb+srv://` URI re-resolves a DNS SRV record on every
    `MongoClient(...)` construction. Building a fresh client per request
    (the old behavior) re-does that lookup on every call, adding latency and
    turning any transient DNS hiccup into a request failure. Caching the
    client for the lifetime of the process — same as any real connection
    pool — means the SRV lookup happens once.
    """
    mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    if not mongo_uri:
        return None

    try:
        from pymongo import MongoClient
    except ImportError as exc:  # pragma: no cover - depends on runtime install
        raise RuntimeError(
            "MongoDB is configured but pymongo is not installed. Add pymongo to requirements first."
        ) from exc

    client_options: dict[str, Any] = {"serverSelectionTimeoutMS": 5000}
    try:
        import certifi
    except ImportError:
        certifi = None
    if certifi is not None:
        client_options["tlsCAFile"] = certifi.where()

    return MongoClient(mongo_uri, **client_options)


def build_mongo_database_from_env() -> Any | None:
    client = _build_mongo_client_from_env()
    if client is None:
        return None

    database_name = os.getenv("MONGODB_DATABASE", "tourunipp2")
    return client[database_name]


def build_mongo_collection_from_env() -> Any | None:
    database = build_mongo_database_from_env()
    if database is None:
        return None
    collection_name = os.getenv("MONGODB_COLLECTION", "trip_sessions")
    return database[collection_name]
