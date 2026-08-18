"""Device management API — /devices prefix.

All routes require a valid Bearer JWT (existing auth system).
Uses authenticated_user_id() from clean_run.auth — same helper used across the app.

Routes:
    GET  /devices                         — list user's registered devices
    POST /devices/register                — claim a device with a one-time secret
    GET  /devices/{device_id}             — get single device (must be owned)
    DELETE /devices/{device_id}           — unregister device (must be owned)
    GET  /devices/{device_id}/firebase-token — issue 1-hr Firebase custom token
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from clean_run.auth import authenticated_user_id
from .repository import (
    delete_device_for_user,
    get_device_for_user,
    list_devices_for_user,
    register_device,
)
from . import rtdb_service
from .firebase_admin_service import firebase_uid_for_user, issue_user_firebase_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["iot-devices"])

_FIREBASE_TOKEN_TTL_SECONDS = 3600  # 1-hour Firebase custom token lifetime


# ── Request/Response schemas ──────────────────────────────────────────────────

class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    registration_secret: str = Field(min_length=1, max_length=128)


class DeviceSummary(BaseModel):
    device_id: str
    label: str
    registered_at: str | None
    last_seen: str | None
    online: bool = False  # real-time online state comes from Firebase RTDB, not MongoDB


class DeviceRegistrationResponse(BaseModel):
    device_id: str
    label: str
    owner_user_id: str
    registered_at: str | None
    firebase_token: str  # immediately usable — no extra round-trip needed


class FirebaseTokenResponse(BaseModel):
    firebase_token: str
    expires_in: int  # seconds


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=dict)
def list_devices(authorization: str | None = Header(default=None)):
    """Return all devices registered to the authenticated user."""
    user_id = authenticated_user_id(authorization)
    devices = list_devices_for_user(user_id)
    return {
        "devices": [
            DeviceSummary(
                device_id=d["device_id"],
                label=d.get("label", ""),
                registered_at=d.get("registered_at"),
                last_seen=d.get("last_seen"),
                online=False,  # mobile resolves online state via Firebase RTDB
            ).model_dump()
            for d in devices
        ]
    }


@router.post("/register", response_model=DeviceRegistrationResponse, status_code=201)
def register_device_endpoint(
    req: DeviceRegisterRequest,
    authorization: str | None = Header(default=None),
):
    """Claim a device using a one-time registration secret from the QR code.

    The secret is consumed on first use — replaying the same QR code will fail.
    Returns the device document plus a ready-to-use Firebase token.
    """
    user_id = authenticated_user_id(authorization)

    device = register_device(
        device_id=req.device_id,
        label=req.label,
        registration_secret=req.registration_secret,
        claiming_user_id=user_id,
    )
    if device is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid or already-used registration code. "
                "Each QR code can only be used once. "
                "Request a new code from the device admin."
            ),
        )

    # Publish the ownership record BEFORE handing back a token. The security
    # rules decide every read of this device's subtree by comparing auth.uid
    # against meta/ownerUid — without this write the owner authenticates fine
    # and is then denied everything, which is indistinguishable from a bad token.
    try:
        rtdb_service.write_device_meta(
            req.device_id,
            label=device.get("label", req.label),
            owner_uid=firebase_uid_for_user(user_id),
            registered_at=device.get("registered_at"),
        )
    except RuntimeError as exc:
        # Firebase unconfigured in this env — registration itself still stands,
        # so don't fail the request, but this device will show no live data
        # until the meta node exists.
        logger.warning(
            "Device %s registered but its RTDB meta could not be written: %s",
            req.device_id,
            exc,
        )

    # Issue a Firebase token immediately so the app can start listening
    try:
        firebase_token = issue_user_firebase_token(user_id)
    except RuntimeError as exc:
        # Firebase not configured in this env — return without token
        # (app will fetch it separately when needed)
        logger.warning("Firebase token issuance skipped: %s", exc)
        firebase_token = ""

    return DeviceRegistrationResponse(
        device_id=device["device_id"],
        label=device.get("label", req.label),
        owner_user_id=user_id,
        registered_at=device.get("registered_at"),
        firebase_token=firebase_token,
    )


@router.get("/{device_id}", response_model=DeviceSummary)
def get_device(
    device_id: str,
    authorization: str | None = Header(default=None),
):
    """Fetch a single device — only if owned by the authenticated user."""
    user_id = authenticated_user_id(authorization)
    device = get_device_for_user(device_id, user_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")
    return DeviceSummary(
        device_id=device["device_id"],
        label=device.get("label", ""),
        registered_at=device.get("registered_at"),
        last_seen=device.get("last_seen"),
        online=False,
    )


@router.delete("/{device_id}", status_code=204)
def delete_device(
    device_id: str,
    authorization: str | None = Header(default=None),
):
    """Unregister a device. Only the owner can remove their own device."""
    user_id = authenticated_user_id(authorization)
    deleted = delete_device_for_user(device_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found.")
    # 204 No Content — no body


@router.get("/{device_id}/firebase-token", response_model=FirebaseTokenResponse)
def get_firebase_token(
    device_id: str,
    authorization: str | None = Header(default=None),
):
    """Issue a short-lived Firebase custom token so the mobile app can subscribe
    to the device's live data path in Firebase RTDB.

    Security:
        - Caller must be authenticated (Bearer JWT)
        - Device must be registered under the caller's account
        - The token grants read-only access to every device whose
          meta/ownerUid matches this user, enforced by Firebase Rules

    The device_id in the path is still checked for ownership (a 404 here is a
    clearer signal than a silent permission denial later), but the token itself
    is no longer scoped to one device — see issue_user_firebase_token().
    """
    user_id = authenticated_user_id(authorization)

    # Ownership check — device must exist under this user
    device = get_device_for_user(device_id, user_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")

    try:
        firebase_token = issue_user_firebase_token(user_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Firebase token issuance failed: {exc}",
        ) from exc

    return FirebaseTokenResponse(
        firebase_token=firebase_token,
        expires_in=_FIREBASE_TOKEN_TTL_SECONDS,
    )
