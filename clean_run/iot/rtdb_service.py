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
        commands/   demoMode (bool) — polled by the device itself, not pushed;
                    the one node this module writes for the device to READ,
                    not for the app to read

Devices are reclaimable (repository.unclaim_device_for_user) — this whole
subtree is wiped via clear_device_data() when a device is unclaimed, so a
future owner starts clean and the previous owner's still-valid Firebase
token loses read access immediately rather than after up to an hour.
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

_LIVE_PATH = "safetyData/live"


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


# ── Remote commands ────────────────────────────────────────────────────────────

def write_demo_mode_command(device_id: str, enabled: bool) -> None:
    """Live-toggle the device's own GPS/speed demo simulation.

    The firmware only ever writes to RTDB — it has no way to receive a push,
    so it polls this leaf on its own telemetry cadence
    (checkDemoModeCommand() in the main-hub sketch). This is the only write
    path: client writes are disabled everywhere by security rules (see the
    module docstring), so the app can't set this directly.
    """
    _device_ref(device_id, "commands/demoMode").set(enabled)


# ── Per-telemetry writes ──────────────────────────────────────────────────────

def write_live(device_id: str, live: dict[str, Any]) -> None:
    """Overwrite the live node the app's onValue() listener is attached to."""
    _device_ref(device_id, _LIVE_PATH).set(live)


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


# ── Unclaim-time cleanup ──────────────────────────────────────────────────────

def clear_device_data(device_id: str) -> None:
    """Wipe live/status/alerts/meta so a re-claimed device starts clean.

    meta is the important one, not just cosmetic: meta/ownerUid is the whole
    access-control record the security rules check (auth.uid == meta/ownerUid).
    If it isn't cleared here, the PREVIOUS owner's still-valid Firebase custom
    token (issued before unclaiming, good for up to an hour) keeps passing
    that check and can keep reading this device's subtree until either the
    token expires or the next owner's write_device_meta() call overwrites it —
    a real, time-bounded authorization leftover, not just stale display data.

    live/snapshots/alerts are wiped so a new owner doesn't briefly see (or, for
    the append-only alerts node, permanently see) the previous owner's
    readings before their own device sends fresh telemetry.

    commands/demoMode is force-set to False rather than deleted: the
    firmware's checkDemoModeCommand() intentionally ignores a missing/null
    value (leaves whatever it last had), so a plain delete would NOT turn
    off a demo run the previous owner forgot to stop before handing the
    device off — an explicit False is the only way to guarantee it.
    """
    _device_ref(device_id, _LIVE_PATH).delete()
    _device_ref(device_id, "safetyData/snapshots").delete()
    _device_ref(device_id, "alerts").delete()
    _device_ref(device_id, "status").delete()
    _device_ref(device_id, "meta").delete()
    _device_ref(device_id, "commands/demoMode").set(False)


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


# ── Admin: fleet-wide reads ──────────────────────────────────────────────────────
# Admin SDK reads bypass firebase_rules.json's owner-only .read rule by design —
# the same mechanism every write_* function above already relies on. There is no
# role-based read bypass in the rules themselves (see the module note on why:
# an admin's own Firebase identity doesn't match any given device's
# meta/ownerUid), so a fleet-wide view can only be served from the backend.

def read_live(device_id: str) -> dict[str, Any] | None:
    """Admin SDK read of safetyData/live for one device. None if it has never
    reported (unclaimed, or claimed but no telemetry has arrived yet)."""
    return _device_ref(device_id, _LIVE_PATH).get()


def read_status(device_id: str) -> dict[str, Any] | None:
    return _device_ref(device_id, "status").get()


def read_fleet_snapshot(device_ids: list[str]) -> dict[str, dict[str, Any]]:
    """{device_id: {"live": ..., "status": ...}} for every id that has ever
    reported — ids with neither node written yet are omitted entirely.

    Loops _device_ref per device (2 HTTP round trips each), which is fine at
    pilot-fleet scale (tens of devices). If the fleet grows into the hundreds,
    replace this with a single _db_module().reference("/devices").get()
    whole-tree read filtered in Python instead of parallelizing the loop —
    fewer round trips, one larger payload.
    """
    result: dict[str, dict[str, Any]] = {}
    for device_id in device_ids:
        live, status = read_live(device_id), read_status(device_id)
        if live is None and status is None:
            continue
        result[device_id] = {"live": live, "status": status}
    return result
