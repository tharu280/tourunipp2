import os
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel

from clean_run.storage import build_session_repository_from_env
from clean_run.auth.repository import build_auth_repository_from_env

admin_router = APIRouter(prefix="/admin", tags=["admin"])

class AdminLoginRequest(BaseModel):
    email: str
    password: str

class AdminLoginResponse(BaseModel):
    token: str

def get_admin_password() -> str:
    pwd = os.getenv("ADMIN_PASSWORD")
    if not pwd:
        raise HTTPException(status_code=503, detail="Admin feature not configured.")
    return pwd

def verify_admin_token(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token.")
    token = authorization.split(" ")[1]
    secret = os.getenv("JWT_SECRET", "fallback_secret")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not authorized as admin.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")

@admin_router.post("/login", response_model=AdminLoginResponse)
async def admin_login(req: AdminLoginRequest) -> AdminLoginResponse:
    expected_email = os.getenv("ADMIN_EMAIL", "admin@touruni.com")
    expected_password = get_admin_password()
    
    if req.email != expected_email or not secrets.compare_digest(req.password, expected_password):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
        
    secret = os.getenv("JWT_SECRET", "fallback_secret")
    payload = {
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "iat": datetime.now(timezone.utc)
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return AdminLoginResponse(token=token)

@admin_router.get("/sessions")
async def get_all_sessions(skip: int = 0, limit: int = 50, _=Depends(verify_admin_token)) -> dict[str, Any]:
    repository = build_session_repository_from_env()
    auth_repo = build_auth_repository_from_env()
    
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage not configured.")
    
    sessions = repository.list_all_sessions(skip=skip, limit=limit)
    
    # Simple cache to avoid querying the same user multiple times
    user_cache = {}
    def get_user_name(uid: str) -> str:
        if not uid:
            return "Guest User"
        if uid in user_cache:
            return user_cache[uid]
        if auth_repo:
            user = auth_repo.find_user_by_id(uid)
            if user and user.get("name"):
                user_cache[uid] = user.get("name")
                return user.get("name")
        user_cache[uid] = "Unknown User"
        return "Unknown User"
    
    slim_sessions = []
    for s in sessions:
        user_id = s.get("user_id")
        slim = {
            "session_id": s.get("session_id"),
            "user_id": user_id,
            "user_name": get_user_name(user_id),
            "status": s.get("status"),
            "created_at": s.get("created_at"),
            "updated_at": s.get("updated_at"),
            "trip_requirements": s.get("trip_requirements", {})
        }
        plan = s.get("plan", {})
        slim["destination"] = plan.get("destination_resolved") or slim["trip_requirements"].get("destination")
        slim["origin"] = plan.get("origin_resolved") or slim["trip_requirements"].get("origin")
        slim["trip_days"] = plan.get("trip_days")
        
        locations = set()
        for route in plan.get("routes", []):
            for place in route.get("ranked_places", []):
                name = place.get("display_name")
                if name:
                    locations.add(name)
        slim["locations"] = list(locations)
        
        slim_sessions.append(slim)
        
    return {"sessions": slim_sessions, "count": len(slim_sessions)}

@admin_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, _=Depends(verify_admin_token)) -> dict[str, Any]:
    repository = build_session_repository_from_env()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage not configured.")
    
    success = repository.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    return {"status": "ok", "deleted": session_id}
