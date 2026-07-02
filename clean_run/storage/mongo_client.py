from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / "atlas-credentials.env")
load_dotenv(PACKAGE_ROOT / "atlas-credentials.env")
load_dotenv(PROJECT_ROOT / ".env")

def build_mongo_collection_from_env() -> Any | None:
    mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    if not mongo_uri:
        return None

    database_name = os.getenv("MONGODB_DATABASE", "tourunipp2")
    collection_name = os.getenv("MONGODB_COLLECTION", "trip_sessions")

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

    client = MongoClient(mongo_uri, **client_options)
    database = client[database_name]
    return database[collection_name]
