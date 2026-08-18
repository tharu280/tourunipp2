"""Firebase Realtime Database writer — the backend half of the live data path.

Until now nothing in this codebase ever wrote to RTDB. The mobile app subscribed
to /devices/{id}/safetyData/live (see useFirebaseDevice.ts) and the security
rules described that subtree, but no code created it, so every IoT screen sat
empty regardless of what the hardware was doing.

Writes here use Admin SDK credentials, which bypass security rules by design.
That is exactly why firebase_rules.json keeps every client write set to false:
the only writer is this module, and it has already authenticated the device.

Tree written:

    /devices/{deviceId}/
        meta/       label, ownerUid, hardwareId, provisionedAt   (registration)
        status/     online, lastSeenAt, linkType, csq            (every POST)
        safetyData/
            live/       overwritten every telemetry POST (~3s)
            snapshots/  push-keys, throttled — history for charts
        alerts/     push-keys, tier >= 1 only
"""
from __future__ import annotations

import os
from typing import Any

from .firebase_admin_service import _get_firebase_app

# A snapshot every telemetry cycle would be ~1200 writes/hour/device, which
# burns through the RTDB free tier during a long demo and gives the charts more
# resolution than they can draw. One snapshot per this many POSTs (~10s at the
# firmware's 3s cycle) is plenty for a trip history graph.
SNAPSHOT_EVERY_N_TICKS = 3


def _db_module():
    """Return firebase_admin.db, after asserting the app can actually reach RTDB.

    initialize_app() succeeds without a databaseURL — token minting does not need
    one — so a missing URL only surfaces at the first db.reference() call, as an
    opaque SDK error. Fail with a message that names the env var instead.
    """
    if not os.getenv("FIREBASE_DATABASE_URL"):
        raise RuntimeError(
            "FIREBASE_DATABASE_URL is not set — the backend cannot write live "
            "telemetry to Firebase. Set it to the RTDB URL "
            "(https://<project>-default-rtdb.firebaseio.com)."
        )
    _get_firebase_app()
    try:
        from firebase_admin import db
    except ImportError as exc:
        raise RuntimeError("firebase-admin is not installed.") from exc
    return db


def _device_ref(device_id: str, path: str):
    return _db_module().reference(f"/devices/{device_id}/{path}")


# ── Registration-time metadata ────────────────────────────────────────────────

def write_device_meta(
    device_id: str,
    *,
    label: str,
    owner_uid: str,
    registered_at: str | None = None,
) -> None:
    """Publish the ownership record the security rules read.

    ownerUid is the whole access-control story for this device's subtree: the
    rules compare it against auth.uid. If this write is skipped the owner can
    authenticate perfectly well and still be denied every read, which looks
    exactly like a broken token. Called on registration.
    """
    _device_ref(device_id, "meta").update(
        {
            "label": label,
            "ownerUid": owner_uid,
            "hardwareId": device_id,
            "provisionedAt": registered_at,
        }
    )


# ── Per-telemetry writes ──────────────────────────────────────────────────────

def write_live(device_id: str, live: dict[str, Any]) -> None:
    """Overwrite the live node the app's onValue() listener is attached to."""
    _device_ref(device_id, "safetyData/live").set(live)


def write_status(device_id: str, *, online: bool, csq: int | None = None) -> None:
    """Update the device's connection status.

    The ESP32 holds no Firebase connection in the backend-relay architecture, so
    RTDB's onDisconnect() is unavailable and `online` here can only ever latch
    true. The app therefore treats a stale timestampMs as offline (see
    useFirebaseDevice.ts); this node exists for the device list's "last seen".
    """
    payload: dict[str, Any] = {
        "online": online,
        "lastSeenAt": {".sv": "timestamp"},  # server clock, not ours
        "linkType": "cellular",
    }
    if csq is not None:
        payload["csq"] = csq
    _device_ref(device_id, "status").update(payload)


def append_snapshot(device_id: str, live: dict[str, Any]) -> None:
    """Append to the trip history ring. Caller decides when, via should_snapshot()."""
    _device_ref(device_id, "safetyData/snapshots").push(live)


def should_snapshot(sequence_num: int) -> bool:
    """Throttle history writes without keeping any per-device state in memory.

    Driven off the Mongo-backed sequence number so the cadence survives a worker
    restart and stays consistent across processes.
    """
    return sequence_num % SNAPSHOT_EVERY_N_TICKS == 0


def append_alert(device_id: str, live: dict[str, Any]) -> None:
    """Record a tier>=1 event under the device's alerts node.

    This is the real-time feed the app renders; the durable, queryable copy goes
    to MongoDB via insert_alert_event().
    """
    _device_ref(device_id, "alerts").push(
        {
            "alertTier": live["alertTier"],
            "riskScore": live["riskScore"],
            "timestampMs": live["timestampMs"],
            "gps": live["gps"],
            "driver": live["driver"],
        }
    )
