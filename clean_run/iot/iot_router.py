"""IoT telemetry API — /iot prefix.

Handles device telemetry ingest, alert event logging, trip session lifecycle,
and device heartbeat.

Routes:
    POST /iot/telemetry                 — ESP32 telemetry ingest (device auth)
    POST /iot/alert-events              — log a safety alert event from mobile
    GET  /iot/alert-events              — paginated alert history for a device
    POST /iot/trips/start               — start a trip session (biometric verified)
    POST /iot/trips/{trip_id}/end       — end a trip session and get summary
    POST /iot/device-heartbeat          — device heartbeat (updates last_seen)

Every route requires a valid Bearer JWT EXCEPT /iot/telemetry, which is the one
caller that has no user session: the ESP32 authenticates with the device_secret
burned into its firmware. See the X-Device-Secret handling below.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from clean_run.auth import authenticated_user_id
from clean_run.storage import build_session_repository_from_env
from . import rtdb_service
from .normalizer import compute_alert_tier, normalize_telemetry
from .repository import (
    insert_alert_event,
    list_alert_events,
    start_trip_session,
    end_trip_session,
    get_device_by_secret,
    get_device_for_user,
    record_telemetry_tick,
    update_device_last_seen,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/iot", tags=["iot-telemetry"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class GpsPayload(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_kmh: float = Field(ge=0)


class DriverDataPayload(BaseModel):
    drowsy_level: int = Field(ge=0, le=4)
    confidence: float = Field(ge=0, le=1)
    eye_status: str = Field(max_length=20)
    yawning_status: str = Field(max_length=20)


class AlertEventRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    alert_tier: int = Field(ge=1, le=3)  # Tier 0 = normal, not logged
    risk_score: float = Field(ge=0, le=1)
    triggered_at: str  # ISO-8601
    gps: GpsPayload
    driver_data: DriverDataPayload


class AlertEventResponse(BaseModel):
    event_id: str
    owner_notified: bool = False  # reserved for future push notification


class TripStartRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    biometric_verified: bool = Field(
        description="True only if the mobile app completed Face ID / BiometricPrompt. "
                    "Biometric bytes never leave the device."
    )
    planning_session_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional trip-planning session_id this IoT trip is linked to.",
    )


class TripStartResponse(BaseModel):
    trip_id: str
    device_id: str
    started_at: str
    planning_session_id: str | None = None


class TripSummaryResponse(BaseModel):
    trip_id: str
    device_id: str
    started_at: str
    ended_at: str | None
    duration_minutes: float | None
    total_alerts: int | None
    max_risk_score: float | None
    planning_session_id: str | None = None


class HeartbeatRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)


# ── Device telemetry ingest ───────────────────────────────────────────────────
# These mirror the JSON that buildTelemetryJson() emits in the esp32-main sketch.
# Field names are the firmware's (snake_case, riskScore 0-100), NOT the mobile
# app's — normalizer.py is what bridges the two. Changing a name here means
# reflashing hardware, so they stay as-is.

class TelemetryDriver(BaseModel):
    drowsyLevel: int = Field(default=0, ge=0, le=4)
    confidence: float = Field(default=0.0, ge=0, le=1)
    eyeStatus: int = Field(default=0, ge=0, le=1)
    yawningStatus: int = Field(default=0, ge=0, le=1)
    faceValid: int = Field(default=0, ge=0, le=1)
    driverVisible: bool = False


class TelemetryVehicle(BaseModel):
    riskScore: int = Field(default=0, ge=0, le=100)  # device scale, not 0-1
    distance_cm: float = Field(default=0, ge=0)


class TelemetryGps(BaseModel):
    latitude: float = Field(default=0, ge=-90, le=90)
    longitude: float = Field(default=0, ge=-180, le=180)
    speed_kmh: float = Field(default=0, ge=0)
    satellites: int = Field(default=0, ge=0)
    fixed: bool = False


class TelemetryRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    driver: TelemetryDriver = Field(default_factory=TelemetryDriver)
    vehicle: TelemetryVehicle = Field(default_factory=TelemetryVehicle)
    gps: TelemetryGps = Field(default_factory=TelemetryGps)
    timestamp_ms: int = Field(default=0, ge=0)  # device uptime, not epoch


@router.post("/telemetry", status_code=204)
def ingest_telemetry(
    req: TelemetryRequest,
    x_device_id: str | None = Header(default=None),
    x_device_secret: str | None = Header(default=None),
    x_modem_csq: int | None = Header(default=None),
):
    """Ingest one telemetry cycle from an ESP32 hub over its 4G link.

    This is the only route in the app that does not use authenticated_user_id():
    the device has no user session and no way to hold a 15-minute JWT across a
    flaky cellular link. It presents the long-lived device_secret from its
    secrets.h instead, over TLS.

    Flow: authenticate -> normalize to the app's schema -> write RTDB live +
    status -> throttled history snapshot -> alert on tier increase.

    Returns 204 with an empty body deliberately. The EC20 pays for every byte of
    the response and parses none of it.
    """
    if not x_device_id or not x_device_secret:
        raise HTTPException(
            status_code=401,
            detail="X-Device-Id and X-Device-Secret headers are required.",
        )

    # The body carries device_id too (the firmware puts it in the JSON). Trusting
    # the header alone would let an authenticated device write under someone
    # else's id, so they have to agree.
    if req.device_id != x_device_id:
        raise HTTPException(
            status_code=403,
            detail="device_id in the body does not match the X-Device-Id header.",
        )

    device = get_device_by_secret(x_device_id, x_device_secret)
    if device is None:
        # One message for unknown-device, bad-secret and not-yet-registered
        # alike: a probe should not learn which device ids exist.
        raise HTTPException(status_code=401, detail="Device authentication failed.")

    raw = req.model_dump()

    # Tier is needed before the Mongo write so the same atomic operation can
    # hand back the previous tier (see record_telemetry_tick).
    tier = compute_alert_tier(req.vehicle.riskScore / 100.0, req.driver.drowsyLevel)
    sequence_num, previous_tier = record_telemetry_tick(x_device_id, tier)

    live = normalize_telemetry(raw, sequence_num=sequence_num)

    try:
        rtdb_service.write_live(x_device_id, live)
        rtdb_service.write_status(x_device_id, online=True, csq=x_modem_csq)
        if rtdb_service.should_snapshot(sequence_num):
            rtdb_service.append_snapshot(x_device_id, live)
        if live["alertTier"] > previous_tier:
            rtdb_service.append_alert(x_device_id, live)
    except RuntimeError as exc:
        # Misconfiguration (no databaseURL, no service account). Nothing the
        # device can do about it, but 503 makes it queue and retry rather than
        # discard the reading — and it shows up loudly in the uvicorn log.
        logger.error("RTDB write failed for device %s: %s", x_device_id, exc)
        raise HTTPException(
            status_code=503,
            detail=f"Live telemetry storage is unavailable: {exc}",
        ) from exc

    # Durable, queryable alert history. Only on a tier increase — telemetry
    # arrives every 3s, so a driver who stays drowsy for a minute would otherwise
    # write twenty identical rows.
    if live["alertTier"] > previous_tier and live["alertTier"] >= 1:
        insert_alert_event(
            {
                "device_id": x_device_id,
                "alert_tier": live["alertTier"],
                "risk_score": live["riskScore"],
                "triggered_at": _iso_from_ms(live["timestampMs"]),
                "gps": {
                    "latitude": live["gps"]["latitude"],
                    "longitude": live["gps"]["longitude"],
                    "speed_kmh": live["gps"]["speedKmh"],
                },
                "driver_data": {
                    "drowsy_level": live["driver"]["drowsyLevel"],
                    "confidence": live["driver"]["confidence"],
                    "eye_status": live["driver"]["eyeStatus"],
                    "yawning_status": live["driver"]["yawningStatus"],
                },
            }
        )
    # 204 No Content


def _iso_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


# ── Alert events ──────────────────────────────────────────────────────────────

@router.post("/alert-events", response_model=AlertEventResponse, status_code=201)
def log_alert_event(
    req: AlertEventRequest,
    authorization: str | None = Header(default=None),
):
    """Persist an alert event emitted by the mobile app when a safety threshold
    is crossed. Only logs tiers 1-3 (Tier 0 = normal, not worth storing).

    Security: device must be registered under the authenticated user's account.
    """
    user_id = authenticated_user_id(authorization)

    # Ownership check — prevents logging alerts for other users' devices
    device = get_device_for_user(req.device_id, user_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found or not owned by you.")

    payload = {
        "device_id": req.device_id,
        "alert_tier": req.alert_tier,
        "risk_score": req.risk_score,
        "triggered_at": req.triggered_at,
        "gps": req.gps.model_dump(),
        "driver_data": req.driver_data.model_dump(),
    }
    event_id = insert_alert_event(payload)

    return AlertEventResponse(
        event_id=event_id,
        owner_notified=False,  # future: push via FCM
    )


@router.get("/alert-events", response_model=dict)
def get_alert_history(
    device_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    authorization: str | None = Header(default=None),
):
    """Paginated alert history for a device. Only the device owner can query."""
    user_id = authenticated_user_id(authorization)
    result = list_alert_events(
        device_id=device_id,
        owner_user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return result


# ── Trip sessions ─────────────────────────────────────────────────────────────

@router.post("/trips/start", response_model=TripStartResponse, status_code=201)
def start_trip(
    req: TripStartRequest,
    authorization: str | None = Header(default=None),
):
    """Start a trip session.

    Requires biometric_verified=True — the mobile app must have completed
    Face ID / BiometricPrompt before calling this endpoint. The backend trusts
    the mobile app's assertion; biometric bytes never leave the device.
    """
    user_id = authenticated_user_id(authorization)

    # Ownership check
    device = get_device_for_user(req.device_id, user_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found or not owned by you.")

    if not req.biometric_verified:
        raise HTTPException(
            status_code=403,
            detail="Biometric verification is required to start a trip.",
        )

    if req.planning_session_id:
        session_repo = build_session_repository_from_env()
        if session_repo is None:
            raise HTTPException(status_code=503, detail="Session storage is not configured.")
        session_doc = session_repo.get_session(req.planning_session_id)
        if session_doc is None or session_doc.get("user_id") != user_id:
            raise HTTPException(
                status_code=404,
                detail="Trip session not found or not owned by you.",
            )

    session = start_trip_session(
        device_id=req.device_id,
        owner_user_id=user_id,
        biometric_verified=req.biometric_verified,
        planning_session_id=req.planning_session_id,
    )
    return TripStartResponse(**session)


@router.post("/trips/{trip_id}/end", response_model=TripSummaryResponse)
def end_trip(
    trip_id: str,
    authorization: str | None = Header(default=None),
):
    """End an active trip and return the summary (duration, alert count, max risk)."""
    user_id = authenticated_user_id(authorization)
    summary = end_trip_session(trip_id, user_id)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail="Trip not found, already ended, or not owned by you.",
        )
    return TripSummaryResponse(**summary)


# ── Device heartbeat ──────────────────────────────────────────────────────────

@router.post("/device-heartbeat", status_code=204)
def device_heartbeat(
    req: HeartbeatRequest,
    authorization: str | None = Header(default=None),
):
    """Called by the mobile app to refresh the device's last_seen timestamp.

    The ESP32 itself sets its online state directly in Firebase RTDB
    (/.info/connected + onDisconnect). This endpoint handles the MongoDB
    last_seen field for display in the device list.
    """
    user_id = authenticated_user_id(authorization)

    # Ownership check
    device = get_device_for_user(req.device_id, user_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found or not owned by you.")

    update_device_last_seen(req.device_id)
    # 204 No Content
