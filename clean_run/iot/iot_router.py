"""IoT telemetry API — /iot prefix.

Handles alert event logging, trip session lifecycle, and device heartbeat.
All routes require a valid Bearer JWT.

Routes:
    POST /iot/alert-events              — log a safety alert event from mobile
    GET  /iot/alert-events              — paginated alert history for a device
    POST /iot/trips/start               — start a trip session (biometric verified)
    POST /iot/trips/{trip_id}/end       — end a trip session and get summary
    POST /iot/device-heartbeat          — device heartbeat (updates last_seen)
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from clean_run.auth import authenticated_user_id
from .repository import (
    insert_alert_event,
    list_alert_events,
    start_trip_session,
    end_trip_session,
    get_device_for_user,
    update_device_last_seen,
)

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


class TripStartResponse(BaseModel):
    trip_id: str
    device_id: str
    started_at: str


class TripSummaryResponse(BaseModel):
    trip_id: str
    device_id: str
    started_at: str
    ended_at: str | None
    duration_minutes: float | None
    total_alerts: int | None
    max_risk_score: float | None


class HeartbeatRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)


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

    session = start_trip_session(
        device_id=req.device_id,
        owner_user_id=user_id,
        biometric_verified=req.biometric_verified,
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
