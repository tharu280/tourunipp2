"""Push-notification registration — /notifications prefix.

The mobile app has been calling POST /notifications/register since the IoT
screens were added (see registerFCMToken in src/api/iotClient.ts), but the route
never existed, so every registration attempt 404'd silently inside a catch.

This stores the token so the plumbing is complete and verifiable. Actually
*sending* FCM pushes — owner alerts on Tier 2+, the "owner_notified" flag on
AlertEventResponse — is deliberately still out of scope; see
4g-ec20-integration-plan.md.

Routes:
    POST /notifications/register    — store this device's FCM/Expo push token
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from clean_run.auth import authenticated_user_id
from clean_run.storage import build_mongo_database_from_env

router = APIRouter(prefix="/notifications", tags=["notifications"])


class FCMTokenRequest(BaseModel):
    fcm_token: str = Field(min_length=1, max_length=512)
    platform: Literal["ios", "android"] = "ios"


class FCMTokenResponse(BaseModel):
    registered: bool


@router.post("/register", response_model=FCMTokenResponse)
def register_push_token(
    req: FCMTokenRequest,
    authorization: str | None = Header(default=None),
):
    """Record a push token against the authenticated user.

    Tokens are held in a set keyed by token string: one user can have several
    (phone plus tablet, or a reinstall that issued a fresh token), and FCM
    rotates them without warning. $addToSet keeps re-registration idempotent,
    which matters because the app calls this on every cold start.
    """
    user_id = authenticated_user_id(authorization)

    db = build_mongo_database_from_env()
    if db is None:
        raise HTTPException(status_code=503, detail="Storage is not configured.")

    db["users"].update_one(
        {"user_id": user_id},
        {
            "$addToSet": {
                "push_tokens": {
                    "token": req.fcm_token,
                    "platform": req.platform,
                    "registered_at": datetime.now(timezone.utc).isoformat(),
                }
            }
        },
    )
    return FCMTokenResponse(registered=True)
