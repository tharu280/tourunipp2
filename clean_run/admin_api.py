import os
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel

from clean_run.storage import build_session_repository_from_env

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
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage not configured.")
    
    sessions = repository.list_all_sessions(skip=skip, limit=limit)
    
    slim_sessions = []
    for s in sessions:
        slim = {
            "session_id": s.get("session_id"),
            "user_id": s.get("user_id"),
            "status": s.get("status"),
            "created_at": s.get("created_at"),
            "updated_at": s.get("updated_at"),
            "trip_requirements": s.get("trip_requirements", {})
        }
        plan = s.get("plan", {})
        slim["destination"] = plan.get("destination_resolved") or slim["trip_requirements"].get("destination")
        slim["budget"] = slim["trip_requirements"].get("total_budget_lkr")
        slim["trip_days"] = plan.get("trip_days")
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
