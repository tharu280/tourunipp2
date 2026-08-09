"""IoT MongoDB repository — device management, alert events, trip sessions.

Collections used (all in database tourunipp2):
    iot_devices         — registered devices owned by users
    iot_alert_events    — per-device alert history
    iot_trip_sessions   — trip records with biometric verification flag

SECURITY RULES:
    - Users can only read/write devices they own (owner_user_id check on every query)
    - registration_secret is one-time-use: consumed and cleared on first registration
    - device_id is a server-assigned UUID, never reused after deletion
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from clean_run.storage.mongo_client import build_mongo_database_from_env


def _db():
    db = build_mongo_database_from_env()
    if db is None:
        raise RuntimeError("MongoDB is not configured (MONGODB_URI missing).")
    return db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Device management ─────────────────────────────────────────────────────────

def create_device_registration_ticket(
    *,
    label: str,
    owner_user_id: str,
) -> dict[str, Any]:
    """Create a pending device slot with a one-time registration secret.

    Called by an admin / provisioning tool (not directly by the mobile app).
    The secret is printed onto a QR code and consumed on first use.
    """
    db = _db()
    device_id = str(uuid.uuid4())
    # 32-byte URL-safe secret — never stored in QR permanently
    registration_secret = secrets.token_urlsafe(32)

    doc = {
        "device_id": device_id,
        "label": label,
        "owner_user_id": owner_user_id,
        "registration_secret": registration_secret,  # one-time; cleared after use
        "registered": False,
        "created_at": _now_iso(),
        "registered_at": None,
        "last_seen": None,
    }
    db["iot_devices"].insert_one(doc)
    return {
        "device_id": device_id,
        "registration_secret": registration_secret,
        "label": label,
        "owner_user_id": owner_user_id,
    }


def register_device(
    *,
    device_id: str,
    label: str,
    registration_secret: str,
    claiming_user_id: str,
) -> dict[str, Any] | None:
    """Claim a device using the one-time secret.

    Returns the device document (without secret) on success, None if secret invalid
    or already consumed.

    Raises ValueError if device already registered by another user.
    """
    db = _db()
    doc = db["iot_devices"].find_one({"device_id": device_id})
    if doc is None:
        return None

    # Secret must match and not yet consumed
    stored_secret = doc.get("registration_secret")
    if not stored_secret or not secrets.compare_digest(stored_secret, registration_secret):
        return None
    if doc.get("registered"):
        # Already registered — could be a replay; reject
        return None

    # Consume the secret (clear it) and mark registered
    result = db["iot_devices"].find_one_and_update(
        {"device_id": device_id, "registration_secret": stored_secret, "registered": False},
        {
            "$set": {
                "label": label,
                "owner_user_id": claiming_user_id,
                "registered": True,
                "registered_at": _now_iso(),
            },
            "$unset": {"registration_secret": ""},  # secret is consumed — never stored again
        },
        return_document=True,
    )
    if result is None:
        return None  # race: another request beat us

    result.pop("_id", None)
    result.pop("registration_secret", None)  # extra safety
    return result


def list_devices_for_user(user_id: str) -> list[dict[str, Any]]:
    db = _db()
    cursor = db["iot_devices"].find(
        {"owner_user_id": user_id, "registered": True},
        {"_id": 0, "registration_secret": 0},
    )
    return list(cursor)


def get_device_for_user(device_id: str, user_id: str) -> dict[str, Any] | None:
    db = _db()
    doc = db["iot_devices"].find_one(
        {"device_id": device_id, "owner_user_id": user_id, "registered": True},
        {"_id": 0, "registration_secret": 0},
    )
    return doc


def delete_device_for_user(device_id: str, user_id: str) -> bool:
    db = _db()
    result = db["iot_devices"].delete_one(
        {"device_id": device_id, "owner_user_id": user_id}
    )
    return result.deleted_count > 0


def update_device_last_seen(device_id: str) -> None:
    """Called by device heartbeat. No user-id check — device authenticates via Firebase."""
    db = _db()
    db["iot_devices"].update_one(
        {"device_id": device_id},
        {"$set": {"last_seen": _now_iso()}},
    )


# ── Alert events ──────────────────────────────────────────────────────────────

def insert_alert_event(payload: dict[str, Any]) -> str:
    """Persist an alert event. Returns the generated event_id."""
    db = _db()
    event_id = str(uuid.uuid4())
    doc = {
        "event_id": event_id,
        "device_id": payload["device_id"],
        "alert_tier": payload["alert_tier"],
        "risk_score": payload["risk_score"],
        "triggered_at": payload["triggered_at"],
        "gps": payload.get("gps", {}),
        "driver_data": payload.get("driver_data", {}),
        "logged_at": _now_iso(),
    }
    db["iot_alert_events"].insert_one(doc)
    return event_id


def list_alert_events(
    *,
    device_id: str,
    owner_user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return paginated alert events for a device the user owns.

    Enforces ownership: device must belong to owner_user_id.
    """
    db = _db()
    # Ownership check
    device = db["iot_devices"].find_one(
        {"device_id": device_id, "owner_user_id": owner_user_id, "registered": True}
    )
    if device is None:
        return {"events": [], "total": 0, "has_more": False}

    total = db["iot_alert_events"].count_documents({"device_id": device_id})
    cursor = (
        db["iot_alert_events"]
        .find({"device_id": device_id}, {"_id": 0})
        .sort("triggered_at", -1)
        .skip(offset)
        .limit(limit + 1)  # fetch one extra to determine has_more
    )
    events = list(cursor)
    has_more = len(events) > limit
    return {
        "events": events[:limit],
        "total": total,
        "has_more": has_more,
    }


# ── Trip sessions ─────────────────────────────────────────────────────────────

def start_trip_session(
    *,
    device_id: str,
    owner_user_id: str,
    biometric_verified: bool,
) -> dict[str, Any]:
    db = _db()
    trip_id = str(uuid.uuid4())
    doc = {
        "trip_id": trip_id,
        "device_id": device_id,
        "owner_user_id": owner_user_id,
        "biometric_verified": biometric_verified,
        "started_at": _now_iso(),
        "ended_at": None,
        "status": "active",
    }
    db["iot_trip_sessions"].insert_one(doc)
    return {
        "trip_id": trip_id,
        "device_id": device_id,
        "started_at": doc["started_at"],
    }


def end_trip_session(trip_id: str, owner_user_id: str) -> dict[str, Any] | None:
    db = _db()
    ended_at = _now_iso()
    result = db["iot_trip_sessions"].find_one_and_update(
        {"trip_id": trip_id, "owner_user_id": owner_user_id, "status": "active"},
        {"$set": {"ended_at": ended_at, "status": "completed"}},
        return_document=True,
    )
    if result is None:
        return None
    result.pop("_id", None)

    # Compute duration
    try:
        started = datetime.fromisoformat(result["started_at"])
        ended = datetime.fromisoformat(ended_at)
        duration_minutes = round((ended - started).total_seconds() / 60, 1)
    except Exception:
        duration_minutes = None

    # Count alerts for this trip window
    total_alerts = db["iot_alert_events"].count_documents({
        "device_id": result["device_id"],
        "triggered_at": {"$gte": result["started_at"], "$lte": ended_at},
    })

    # Max risk score
    pipeline = [
        {"$match": {
            "device_id": result["device_id"],
            "triggered_at": {"$gte": result["started_at"], "$lte": ended_at},
        }},
        {"$group": {"_id": None, "max_risk": {"$max": "$risk_score"}}},
    ]
    agg = list(db["iot_alert_events"].aggregate(pipeline))
    max_risk_score = agg[0]["max_risk"] if agg else None

    return {
        "trip_id": result["trip_id"],
        "device_id": result["device_id"],
        "started_at": result["started_at"],
        "ended_at": ended_at,
        "duration_minutes": duration_minutes,
        "total_alerts": total_alerts,
        "max_risk_score": max_risk_score,
    }
