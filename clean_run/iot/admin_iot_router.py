"""Admin fleet-wide IoT management API — /admin/iot prefix.

Every route requires verify_admin_token (imported from clean_run.admin_api —
the same 12h admin JWT used by /admin/sessions). Unlike devices_router.py and
iot_router.py, nothing here is owner-scoped: every read spans every
device/owner in the fleet.

Routes:
    POST   /admin/iot/devices                    — provision a new UNCLAIMED device + QR payload
    GET    /admin/iot/devices                     — fleet-wide device list (paginated)
    POST   /admin/iot/devices/{device_id}/unclaim — force-release a claimed device (support/ops)
    GET    /admin/iot/alerts                      — fleet-wide alert history (paginated)
    GET    /admin/iot/trips                       — fleet-wide trip session records (paginated)
    GET    /admin/iot/locations                   — live snapshot of every claimed device's last GPS fix
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from clean_run.admin_api import verify_admin_token
from clean_run.auth.repository import build_auth_repository_from_env

from . import rtdb_service
from .repository import (
    _ADMIN_UNCLAIMED_OWNER,
    admin_force_unclaim_device,
    count_all_devices,
    create_device_registration_ticket,
    device_id_from_mac,
    get_devices_by_ids,
    list_all_alert_events,
    list_all_devices,
    list_all_trip_sessions,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/iot",
    tags=["admin-iot"],
    dependencies=[Depends(verify_admin_token)],
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Owner-name enrichment ────────────────────────────────────────────────────────
# Same cached-lookup shape as admin_api.py's get_all_sessions() — small enough
# per call site that it isn't worth sharing as a utility across two files.

def _owner_name_lookup() -> Any:
    auth_repo = build_auth_repository_from_env()
    cache: dict[str, str | None] = {}

    def get_owner_name(owner_user_id: str | None) -> str | None:
        if not owner_user_id or owner_user_id == _ADMIN_UNCLAIMED_OWNER:
            return None
        if owner_user_id in cache:
            return cache[owner_user_id]
        name = None
        if auth_repo:
            user = auth_repo.find_user_by_id(owner_user_id)
            if user:
                name = user.get("name")
        cache[owner_user_id] = name
        return name

    return get_owner_name


# ── Schemas ───────────────────────────────────────────────────────────────────

class AdminProvisionDeviceRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    mac_address: str | None = Field(
        default=None,
        description="Real hardware only — device_id is derived from this MAC. "
        "Omit for a UUID-based device_id (demo/virtual devices).",
    )


class AdminProvisionDeviceResponse(BaseModel):
    device_id: str
    label: str
    registration_secret: str  # goes into qr_payload — reusable, not one-time
    device_secret: str  # shown once — for the ESP32 firmware's secrets.h only
    qr_payload: str  # exact string DeviceRegistrationScreen.tsx's scanner parses
    created_at: str


class AdminDeviceSummary(BaseModel):
    device_id: str
    label: str
    registered: bool
    owner_user_id: str | None
    owner_name: str | None
    registered_at: str | None
    last_seen: str | None
    created_at: str


class AdminDeviceListResponse(BaseModel):
    devices: list[AdminDeviceSummary]
    total: int


class AdminAlertEvent(BaseModel):
    event_id: str
    device_id: str
    device_label: str | None
    owner_name: str | None
    alert_tier: int
    risk_score: float
    triggered_at: str
    gps: dict[str, Any]
    driver_data: dict[str, Any]


class AdminAlertListResponse(BaseModel):
    events: list[AdminAlertEvent]
    total: int
    has_more: bool


class AdminTripRecord(BaseModel):
    trip_id: str
    device_id: str
    device_label: str | None
    owner_name: str | None
    started_at: str
    ended_at: str | None
    status: str
    duration_minutes: float | None
    total_alerts: int
    max_risk_score: float | None


class AdminTripListResponse(BaseModel):
    trips: list[AdminTripRecord]
    total: int
    has_more: bool


class AdminDeviceLiveLocation(BaseModel):
    latitude: float
    longitude: float
    speed_kmh: float
    alert_tier: int
    risk_score: float
    timestamp_ms: int


class AdminDeviceLocation(BaseModel):
    device_id: str
    label: str
    owner_name: str | None
    online: bool
    last_seen: str | None
    live: AdminDeviceLiveLocation | None


class AdminLocationsResponse(BaseModel):
    devices: list[AdminDeviceLocation]


# ── Devices ───────────────────────────────────────────────────────────────────

@router.post("/devices", response_model=AdminProvisionDeviceResponse, status_code=201)
def admin_provision_device(req: AdminProvisionDeviceRequest) -> AdminProvisionDeviceResponse:
    """Provision a new device into the unclaimed pool and return its QR payload.

    The device starts with no real owner (_ADMIN_UNCLAIMED_OWNER) — whoever
    scans the returned qr_payload in the mobile app becomes the real owner via
    the existing, unmodified POST /devices/register claim flow.
    """
    device_id: str | None = None
    if req.mac_address:
        try:
            device_id = device_id_from_mac(req.mac_address)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    ticket = create_device_registration_ticket(
        label=req.label,
        owner_user_id=_ADMIN_UNCLAIMED_OWNER,
        device_id=device_id,
    )

    # Exactly the shape DeviceRegistrationScreen.tsx's parseQRPayload() checks
    # for ({v, device_id, secret}) — mirrors provision_device.py's CLI output.
    qr_payload = json.dumps(
        {"v": 1, "device_id": ticket["device_id"], "secret": ticket["registration_secret"]},
        separators=(",", ":"),
    )

    return AdminProvisionDeviceResponse(
        device_id=ticket["device_id"],
        label=ticket["label"],
        registration_secret=ticket["registration_secret"],
        device_secret=ticket["device_secret"],
        qr_payload=qr_payload,
        created_at=_now_iso(),
    )


@router.get("/devices", response_model=AdminDeviceListResponse)
def admin_list_devices(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    registered: bool | None = Query(default=None),
) -> AdminDeviceListResponse:
    devices = list_all_devices(skip=skip, limit=limit, registered=registered)
    total = count_all_devices(registered=registered)
    get_owner_name = _owner_name_lookup()

    return AdminDeviceListResponse(
        devices=[
            AdminDeviceSummary(
                device_id=d["device_id"],
                label=d.get("label", ""),
                registered=d.get("registered", False),
                owner_user_id=d.get("owner_user_id")
                if d.get("owner_user_id") != _ADMIN_UNCLAIMED_OWNER
                else None,
                owner_name=get_owner_name(d.get("owner_user_id")),
                registered_at=d.get("registered_at"),
                last_seen=d.get("last_seen"),
                created_at=d.get("created_at", ""),
            )
            for d in devices
        ],
        total=total,
    )


@router.post("/devices/{device_id}/unclaim", status_code=204)
def admin_unclaim_device(device_id: str):
    """Force-release a claimed device back to the unclaimed pool (support/ops
    action — no ownership match required, unlike the user-initiated unclaim).
    """
    if not admin_force_unclaim_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found or already unclaimed.")
    try:
        rtdb_service.clear_device_data(device_id)
    except RuntimeError as exc:
        # Mongo state is already correct; RTDB cleanup failing here is a
        # logged degradation, not a reason to fail the whole request — same
        # tradeoff devices_router.py's user-facing unclaim path makes.
        logger.warning(
            "Device %s force-unclaimed but RTDB data could not be cleared: %s",
            device_id,
            exc,
        )


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=AdminAlertListResponse)
def admin_list_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    device_id: str | None = Query(default=None),
    min_tier: int | None = Query(default=None, ge=1, le=3),
) -> AdminAlertListResponse:
    result = list_all_alert_events(
        limit=limit, offset=offset, device_id=device_id, min_tier=min_tier
    )
    devices = get_devices_by_ids([e["device_id"] for e in result["events"]])
    get_owner_name = _owner_name_lookup()

    return AdminAlertListResponse(
        events=[
            AdminAlertEvent(
                event_id=e["event_id"],
                device_id=e["device_id"],
                device_label=devices.get(e["device_id"], {}).get("label"),
                owner_name=get_owner_name(devices.get(e["device_id"], {}).get("owner_user_id")),
                alert_tier=e["alert_tier"],
                risk_score=e["risk_score"],
                triggered_at=e["triggered_at"],
                gps=e.get("gps", {}),
                driver_data=e.get("driver_data", {}),
            )
            for e in result["events"]
        ],
        total=result["total"],
        has_more=result["has_more"],
    )


# ── Trip records ──────────────────────────────────────────────────────────────

@router.get("/trips", response_model=AdminTripListResponse)
def admin_list_trips(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> AdminTripListResponse:
    result = list_all_trip_sessions(limit=limit, offset=offset, status=status)
    devices = get_devices_by_ids([t["device_id"] for t in result["trips"]])
    get_owner_name = _owner_name_lookup()

    return AdminTripListResponse(
        trips=[
            AdminTripRecord(
                trip_id=t["trip_id"],
                device_id=t["device_id"],
                device_label=devices.get(t["device_id"], {}).get("label"),
                owner_name=get_owner_name(devices.get(t["device_id"], {}).get("owner_user_id")),
                started_at=t["started_at"],
                ended_at=t.get("ended_at"),
                status=t["status"],
                duration_minutes=t.get("duration_minutes"),
                total_alerts=t.get("total_alerts", 0),
                max_risk_score=t.get("max_risk_score"),
            )
            for t in result["trips"]
        ],
        total=result["total"],
        has_more=result["has_more"],
    )


# ── Locations ─────────────────────────────────────────────────────────────────

@router.get("/locations", response_model=AdminLocationsResponse)
def admin_list_locations() -> AdminLocationsResponse:
    """Live snapshot of every claimed device's last-known GPS fix.

    Unclaimed devices have no owner/vehicle to plot, so they're excluded here
    (unlike admin_list_devices, which shows the whole pool). A device that has
    never sent telemetry has no safetyData/live node yet — it's still listed,
    just with live=None, so admin can tell "claimed but silent" apart from
    "not provisioned at all".
    """
    devices = list_all_devices(limit=500, registered=True)
    snapshot = rtdb_service.read_fleet_snapshot([d["device_id"] for d in devices])
    get_owner_name = _owner_name_lookup()

    results: list[AdminDeviceLocation] = []
    for d in devices:
        device_id = d["device_id"]
        entry = snapshot.get(device_id, {})
        live_raw = entry.get("live")
        status_raw = entry.get("status") or {}

        live = None
        if live_raw:
            gps = live_raw.get("gps") or {}
            live = AdminDeviceLiveLocation(
                latitude=gps.get("latitude", 0.0),
                longitude=gps.get("longitude", 0.0),
                speed_kmh=gps.get("speedKmh", 0.0),
                alert_tier=live_raw.get("alertTier", 0),
                risk_score=live_raw.get("riskScore", 0.0),
                timestamp_ms=live_raw.get("timestampMs", 0),
            )

        results.append(
            AdminDeviceLocation(
                device_id=device_id,
                label=d.get("label", ""),
                owner_name=get_owner_name(d.get("owner_user_id")),
                online=bool(status_raw.get("online", False)),
                last_seen=d.get("last_seen"),
                live=live,
            )
        )

    return AdminLocationsResponse(devices=results)
