"""IoT MongoDB repository — device management, alert events, trip sessions.

Collections used (all in database tourunipp2):
    iot_devices         — registered devices owned by users
    iot_alert_events    — per-device alert history
    iot_trip_sessions   — trip records with biometric verification flag

SECURITY RULES:
    - Users can only read/write devices they own (owner_user_id check on every query)
    - registration_secret is one-time-use: consumed and cleared on first registration
    - device_secret is long-lived: it is how the ESP32 itself authenticates its
      telemetry POSTs, so it survives registration (unlike registration_secret)
      and is never returned to the mobile app
    - device_id defaults to a server-assigned UUID, but provisioning may pass the
      device's hardware MAC instead so the firmware can derive it without an NVM
      write step (see scripts/provision_device.py)
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
    device_id: str | None = None,
) -> dict[str, Any]:
    """Create a pending device slot with a one-time registration secret.

    Called by an admin / provisioning tool (not directly by the mobile app).
    The registration_secret is printed onto a QR code and consumed on first use.

    device_id defaults to a fresh UUID. Provisioning passes the device's
    MAC-derived id (``ESP32-MAC-<MAC>``) instead, so the firmware can compute the
    same value from its own MAC at boot with no NVM write step — see
    computeDeviceId() in the esp32-main sketch.

    The returned device_secret is what the ESP32 sends as X-Device-Secret on
    every telemetry POST. Unlike registration_secret it is long-lived and is
    never handed to the mobile app.
    """
    db = _db()
    device_id = device_id or str(uuid.uuid4())
    # 32-byte URL-safe secrets — registration is one-time, device is long-lived
    registration_secret = secrets.token_urlsafe(32)
    device_secret = secrets.token_urlsafe(32)

    doc = {
        "device_id": device_id,
        "label": label,
        "owner_user_id": owner_user_id,
        "registration_secret": registration_secret,  # one-time; cleared after use
        "device_secret": device_secret,  # long-lived; survives registration
        "registered": False,
        "created_at": _now_iso(),
        "registered_at": None,
        "last_seen": None,
    }
    db["iot_devices"].insert_one(doc)
    return {
        "device_id": device_id,
        "registration_secret": registration_secret,
        "device_secret": device_secret,
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
    result.pop("device_secret", None)  # belongs to the device, never to the app
    return result


# Projection shared by every user-facing device read. Both secrets are excluded:
# registration_secret is consumed at claim time, and device_secret belongs to the
# ESP32 alone — the mobile app has no use for either.
_PUBLIC_DEVICE_FIELDS = {"_id": 0, "registration_secret": 0, "device_secret": 0}


def list_devices_for_user(user_id: str) -> list[dict[str, Any]]:
    db = _db()
    cursor = db["iot_devices"].find(
        {"owner_user_id": user_id, "registered": True},
        _PUBLIC_DEVICE_FIELDS,
    )
    return list(cursor)


def get_device_for_user(device_id: str, user_id: str) -> dict[str, Any] | None:
    db = _db()
    doc = db["iot_devices"].find_one(
        {"device_id": device_id, "owner_user_id": user_id, "registered": True},
        _PUBLIC_DEVICE_FIELDS,
    )
    return doc


def get_device_by_secret(device_id: str, device_secret: str) -> dict[str, Any] | None:
    """Authenticate a telemetry POST coming from the ESP32 itself.

    This is the device-side counterpart to authenticated_user_id(): the ESP32
    holds no user JWT, only the device_secret burned into its secrets.h.

    Returns the device document (secrets stripped) or None if the id is unknown,
    the device was never claimed, or the secret does not match. Comparison is
    constant-time so a wrong secret leaks no timing information.
    """
    db = _db()
    doc = db["iot_devices"].find_one({"device_id": device_id})
    if doc is None:
        return None

    stored_secret = doc.get("device_secret")
    if not stored_secret or not secrets.compare_digest(stored_secret, device_secret):
        return None

    # An unclaimed device has no owner to attribute telemetry to, and its RTDB
    # subtree has no ownerUid for the rules to check — reject until registered.
    if not doc.get("registered"):
        return None

    doc.pop("_id", None)
    doc.pop("registration_secret", None)
    doc.pop("device_secret", None)
    return doc


def delete_device_for_user(device_id: str, user_id: str) -> bool:
    db = _db()
    result = db["iot_devices"].delete_one(
        {"device_id": device_id, "owner_user_id": user_id}
    )
    return result.deleted_count > 0


def update_device_last_seen(device_id: str) -> None:
    """Refresh last_seen for the device list.

    Two callers, both of which have already established who they are:
    the mobile heartbeat (checked against the user's JWT) and the ESP32's own
    telemetry POST (checked against its device_secret). No ownership check here.
    """
    db = _db()
    db["iot_devices"].update_one(
        {"device_id": device_id},
        {"$set": {"last_seen": _now_iso()}},
    )


def record_telemetry_tick(device_id: str, alert_tier: int) -> tuple[int, int]:
    """Stamp last_seen, advance the sequence, and remember the current tier.

    Returns ``(sequence_num, previous_alert_tier)``.

    One atomic find_one_and_update rather than several round trips: telemetry is
    the hot path (a POST every 3s per device) and $inc is the only way to get a
    sequence number that survives a uvicorn reload or a second worker.

    The previous tier is what makes alert history usable. Telemetry arrives every
    3 seconds, so a driver who stays drowsy for a minute would otherwise generate
    twenty identical alert rows; the caller logs only on a tier *increase*.
    Reading the pre-update document (return_document=False) gets the old tier and
    sets the new one in the same operation, with no read-then-write race.
    """
    db = _db()
    before = db["iot_devices"].find_one_and_update(
        {"device_id": device_id},
        {
            "$set": {"last_seen": _now_iso(), "last_alert_tier": alert_tier},
            "$inc": {"telemetry_seq": 1},
        },
        projection={"_id": 0, "telemetry_seq": 1, "last_alert_tier": 1},
        return_document=False,  # pre-update doc
    )
    if before is None:
        return 0, 0
    return int(before.get("telemetry_seq", 0)) + 1, int(before.get("last_alert_tier", 0) or 0)


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
    planning_session_id: str | None = None,
) -> dict[str, Any]:
    db = _db()
    trip_id = str(uuid.uuid4())
    doc = {
        "trip_id": trip_id,
        "device_id": device_id,
        "owner_user_id": owner_user_id,
        "biometric_verified": biometric_verified,
        "planning_session_id": planning_session_id,
        "started_at": _now_iso(),
        "ended_at": None,
        "status": "active",
    }
    db["iot_trip_sessions"].insert_one(doc)
    return {
        "trip_id": trip_id,
        "device_id": device_id,
        "started_at": doc["started_at"],
        "planning_session_id": planning_session_id,
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
        "planning_session_id": result.get("planning_session_id"),
    }
