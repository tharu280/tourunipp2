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

    return firebase_admin.initialize_app(cred)


def issue_device_firebase_token(
    device_id: str,
    *,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a Firebase custom token for an IoT device.

    The Firebase uid will be `device:{device_id}`.
    Firebase Security Rules should restrict this uid to write only to
    /devices/{device_id}/** and read nothing.

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


def issue_user_firebase_token(user_id: str, device_id: str) -> str:
    """Issue a Firebase custom token for a mobile app user to READ a specific device.

    Firebase uid will be `user:{user_id}`.
    Firebase Security Rules grant read access to /devices/{device_id}/** only if
    the requesting uid owns the device.

    Returns the raw custom token string (valid for 1 hour).
    """
    _get_firebase_app()
    try:
        from firebase_admin import auth as firebase_auth
    except ImportError as exc:
        raise RuntimeError("firebase-admin is not installed.") from exc

    uid = f"user:{user_id}"
    claims = {"role": "mobile_user", "user_id": user_id, "device_id": device_id}
    token = firebase_auth.create_custom_token(uid, claims)
    return token.decode("utf-8") if isinstance(token, bytes) else token
