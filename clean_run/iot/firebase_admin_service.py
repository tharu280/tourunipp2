"""Firebase Admin SDK service — issues custom tokens for IoT devices.

The mobile app calls GET /devices/{id}/firebase-token to get a short-lived
custom token. The ESP32 fetches its own token via POST /iot/device-token
(authenticated with its device_secret stored in NVM).

SECURITY:
    - Custom tokens are signed by Firebase Admin SDK using the service account
    - Token has 1-hour TTL; mobile refreshes 5 min before expiry
    - The ESP32 device uid in Firebase is `device:{device_id}` — separate
      from the user uid space — so Firebase Security Rules can distinguish
      "this is a device, only allow writes to /devices/{device_id}/**"
    - We never issue a token with admin privileges

Required env vars:
    FIREBASE_SERVICE_ACCOUNT_JSON   — full service account JSON as a string, OR
    GOOGLE_APPLICATION_CREDENTIALS — path to service account JSON file
    FIREBASE_DATABASE_URL          — RTDB URL, required by rtdb_service.py
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _get_firebase_app():
    """Lazy init — avoids startup failure when Firebase is not configured."""
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise RuntimeError(
            "firebase-admin is not installed. Add it to requirements.txt."
        ) from exc

    if firebase_admin._apps:
        return firebase_admin.get_app()

    # Prefer JSON string in env (Render / Railway / Docker secrets)
    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        sa_dict = json.loads(sa_json)
        cred = credentials.Certificate(sa_dict)
    else:
        # Fall back to file path (local dev)
        sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not sa_path:
            raise RuntimeError(
                "Firebase Admin is not configured. Set FIREBASE_SERVICE_ACCOUNT_JSON "
                "or GOOGLE_APPLICATION_CREDENTIALS."
            )
        cred = credentials.Certificate(sa_path)

    # databaseURL is only consulted by db.reference(); minting custom tokens
    # works without it, which is why its absence went unnoticed while token
    # issuance was the app's only Firebase feature. rtdb_service.py raises a
    # clearer error than the SDK's own if it is still missing.
    options: dict[str, Any] = {}
    database_url = os.getenv("FIREBASE_DATABASE_URL")
    if database_url:
        options["databaseURL"] = database_url

    return firebase_admin.initialize_app(cred, options)


def issue_device_firebase_token(
    device_id: str,
    *,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a Firebase custom token for an IoT device.

    Called from POST /iot/device-token (iot_router.py). This IS the live
    architecture now: the ESP32 exchanges this custom token for a Firebase ID
    token and writes /devices/{id}/safetyData/live + /status directly to RTDB
    over TLS (4g-ec20-integration-plan.md §10.3 Option A). /iot/telemetry
    (Option B, backend-relay) is kept as a documented fallback, per
    change-management rule 7 — it still works, the device just doesn't call it
    by default anymore.

    The Firebase uid is `device:{device_id}`. The matching `role == 'iot_device'`
    write rules are reinstated in firebase_rules.json, scoped to only
    /devices/$deviceId/safetyData/live and /devices/$deviceId/status.

    Returns the raw custom token string (valid for 1 hour).
    """
    _get_firebase_app()
    try:
        from firebase_admin import auth as firebase_auth
    except ImportError as exc:
        raise RuntimeError("firebase-admin is not installed.") from exc

    uid = f"device:{device_id}"
    claims = {"role": "iot_device", "device_id": device_id}
    if additional_claims:
        claims.update(additional_claims)

    token = firebase_auth.create_custom_token(uid, claims)
    # SDK returns bytes; convert to str for JSON serialization
    return token.decode("utf-8") if isinstance(token, bytes) else token


def firebase_uid_for_user(user_id: str) -> str:
    """The Firebase uid a user's custom token carries.

    Written into /devices/{id}/meta/ownerUid at registration, and compared
    against auth.uid by the security rules. One helper so the two sides cannot
    drift apart.
    """
    return f"user:{user_id}"


def issue_user_firebase_token(user_id: str, device_id: str | None = None) -> str:
    """Issue a Firebase custom token for a mobile app user.

    Firebase uid will be `user:{user_id}`. Read access is decided by the security
    rules comparing that uid against /devices/{id}/meta/ownerUid, so this one
    token covers every device the user owns.

    device_id is accepted for call-site compatibility but deliberately NOT put
    into the claims. It used to be, and that scoped the token to a single device:
    switching devices in the app's picker forced a fresh token round-trip, and
    two devices could never be watched at once.

    Returns the raw custom token string (valid for 1 hour).
    """
    _get_firebase_app()
    try:
        from firebase_admin import auth as firebase_auth
    except ImportError as exc:
        raise RuntimeError("firebase-admin is not installed.") from exc

    claims = {"role": "mobile_user", "user_id": user_id}
    token = firebase_auth.create_custom_token(firebase_uid_for_user(user_id), claims)
    return token.decode("utf-8") if isinstance(token, bytes) else token
