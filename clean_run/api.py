from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from clean_run.emotion import (
    attach_location_context,
    build_emotion_checkin_targets,
    build_emotion_recommendation,
    build_emotion_summary,
    build_start_of_day_mood_recommendation,
    sanitize_emotion_checkin,
    build_nearby_emotion_tips,
)
from clean_run.emotion.inference import classify_image_bytes
from clean_run.auth import auth_router, authenticated_user_id, optional_authenticated_user_id
from clean_run.flights.service import FlightSearchPreferences, FlightSearchService
from clean_run.intake.schemas import ChatSessionState
from clean_run.intake.service import TravelIntakeService
from clean_run.notifications import (
    SchedulerSettings,
    queue_mood_reminders,
    run_condition_refresh_batch,
)
from clean_run.planner_pipeline import TripPlanOptions, build_trip_plan, refresh_trip_intelligence
from clean_run.recommendations import build_contextual_alternatives
from clean_run.storage import SessionLoaderService, build_session_repository_from_env


CLEAN_RUN_ROOT = Path(__file__).resolve().parent
load_dotenv(CLEAN_RUN_ROOT / ".env")
load_dotenv(CLEAN_RUN_ROOT / "atlas-credentials.env")

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"api_key['\"]?\s*[:=]\s*['\"]?[^,'\"\s}]+", re.IGNORECASE),
    re.compile(r"key['\"]?\s*[:=]\s*['\"]?[^,'\"\s}]+", re.IGNORECASE),
]


def safe_error_detail(exc: Exception | str, *, feature: str) -> str:
    raw = str(exc)
    lowered = raw.lower()

    if "consumer_suspended" in lowered or "has been suspended" in lowered:
        return (
            f"{feature} is unavailable because the Google/Gemini project or API key is suspended. "
            "Create a fresh key, update the deployment secret, and restart the app."
        )
    if "reported as leaked" in lowered or "permission_denied" in lowered or "permission denied" in lowered:
        return (
            f"{feature} cannot use the current Google/Gemini key. "
            "The key may be blocked, leaked, restricted, or missing access."
        )
    if "api key" in lowered and ("missing" in lowered or "required" in lowered):
        return f"{feature} needs a configured API key."

    sanitized = raw
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[redacted]", sanitized)
    return sanitized[:500]


class ChatRequest(BaseModel):
    message: str = Field(description="Latest user message.")
    session: ChatSessionState | None = Field(default=None)


class FlightSearchRequest(BaseModel):
    origin: str = Field(description="Origin airport IATA code, for example DXB.")
    departure_date: str = Field(description="Departure date in YYYY-MM-DD format.")
    search_mode: str = Field(default="single_day", pattern="^(single_day|week)$")
    passengers: int = Field(default=1, ge=1)
    cabin_class: str = "economy"
    total_budget_lkr: float | None = None
    currency: str = "USD"


class FlightConfirmRequest(BaseModel):
    session: ChatSessionState
    selected_flight: dict[str, Any] | None = None
    continue_without_live_fare: bool = False


class PlanRequest(BaseModel):
    origin: str
    destination: str
    duration: str
    start_date: str
    departure_time: str = "08:00"
    accommodation_budget_lkr: float | None = None
    total_budget_lkr: float | None = None
    flight_usd_to_lkr_rate: float | None = None
    selected_flight: dict[str, Any] | None = None
    flight_plan: dict[str, Any] | None = None
    session_id: str | None = None
    include_gemini: bool = True
    include_roadlk: bool = True
    include_weather: bool = True
    include_crowd: bool = True
    place_strategy: str = Field(default="nearby", pattern="^(nearby|text)$")
    response_mode: str = Field(default="slim", pattern="^(slim|full)$")


class RefreshIntelligenceRequest(BaseModel):
    departure_time: str = "08:00"
    include_gemini: bool = True
    include_weather: bool = True
    include_crowd: bool = True
    include_roadlk: bool = True
    response_mode: str = Field(default="slim", pattern="^(slim|full)$")


class ScheduledRefreshRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    departure_time: str = "08:00"
    include_gemini: bool = False


class ScheduledReminderRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)


class ContextualAlternativesRequest(BaseModel):
    day: int | None = Field(default=None, ge=1)
    attraction_id: str | None = None
    interests: list[str] = Field(default_factory=list)
    radius_meters: int = Field(default=5_000, ge=1_000, le=8_000)
    limit_per_attraction: int = Field(default=3, ge=1, le=5)
    max_attractions: int = Field(default=6, ge=1, le=12)
    force: bool = False


class EmotionTopPrediction(BaseModel):
    class_name: str
    probability: float = Field(ge=0, le=1)


class EmotionUserLocation(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0)


class EmotionCheckinRequest(BaseModel):
    attraction_id: str | None = None
    attraction_name: str | None = None
    checkin_type: str = Field(default="attraction", pattern="^(attraction|start_of_day)$")
    day: int | None = Field(default=None, ge=1)
    timestamp: str | None = None
    user_location: EmotionUserLocation | None = None
    emotion_label: str = Field(pattern="^(anger|happy|neutral|sad|surprise|uncertain)$")
    emotion_confidence: float = Field(ge=0, le=1)
    top_predictions: list[EmotionTopPrediction] = Field(default_factory=list)
    model_version: str = "rafdb5_local_tflite"
    local_inference: bool = True
    hobbies: list[str] = Field(default_factory=list)


def _parse_hobbies(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in value.split(",")]
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_intake_service() -> TravelIntakeService:
    return TravelIntakeService(use_llm=True)


@lru_cache(maxsize=1)
def get_session_loader() -> SessionLoaderService:
    return SessionLoaderService(build_session_repository_from_env())


@lru_cache(maxsize=1)
def get_session_repository():
    return build_session_repository_from_env()


def _require_cron_secret(value: str | None) -> None:
    configured = os.getenv("CRON_SECRET")
    if not configured:
        raise HTTPException(status_code=503, detail="Scheduled jobs are not configured.")
    if not value or not secrets.compare_digest(value, configured):
        raise HTTPException(status_code=401, detail="Invalid scheduler credentials.")


def _ensure_session_access(
    document: dict[str, Any],
    authorization: str | None,
) -> None:
    """Require the owning account for user-linked sessions; allow legacy sessions."""
    owner_id = document.get("user_id")
    if not owner_id:
        return
    if authenticated_user_id(authorization) != owner_id:
        raise HTTPException(status_code=403, detail="This trip belongs to another account.")


@lru_cache(maxsize=1)
def get_flight_search_service() -> FlightSearchService:
    return FlightSearchService()


def _estimate_flight_cost_lkr(
    flight: dict[str, Any] | None,
    *,
    total_budget_lkr: float | None = None,
    flight_usd_to_lkr_rate: float | None = None,
) -> dict[str, Any]:
    if not flight:
        return {
            "selected_flight_budget_lkr_estimated": None,
            "selected_flight_budget_conversion": None,
            "remaining_budget_lkr": total_budget_lkr,
        }

    try:
        price_value = float(flight.get("price"))
    except (TypeError, ValueError):
        return {
            "selected_flight_budget_lkr_estimated": None,
            "selected_flight_budget_conversion": None,
            "remaining_budget_lkr": total_budget_lkr,
        }

    currency = str(flight.get("currency") or "").upper()
    if currency == "LKR":
        estimated = price_value
        conversion = {
            "source_currency": "LKR",
            "target_currency": "LKR",
            "rate": 1.0,
            "mode": "identity",
        }
    elif currency == "USD":
        configured_rate = (
            flight_usd_to_lkr_rate
            if flight_usd_to_lkr_rate is not None
            else float(os.getenv("FLIGHT_USD_TO_LKR_RATE") or 300.0)
        )
        estimated = price_value * configured_rate
        conversion = {
            "source_currency": "USD",
            "target_currency": "LKR",
            "rate": configured_rate,
            "mode": (
                "provided"
                if flight_usd_to_lkr_rate is not None
                else ("env" if os.getenv("FLIGHT_USD_TO_LKR_RATE") else "default_estimate")
            ),
        }
    else:
        return {
            "selected_flight_budget_lkr_estimated": None,
            "selected_flight_budget_conversion": None,
            "remaining_budget_lkr": total_budget_lkr,
        }

    remaining = None
    if total_budget_lkr is not None:
        remaining = max(0.0, float(total_budget_lkr) - float(estimated))

    return {
        "selected_flight_budget_lkr_estimated": estimated,
        "selected_flight_budget_conversion": conversion,
        "remaining_budget_lkr": remaining,
    }


def _segment_summary(segment: dict[str, Any]) -> dict[str, Any]:
    top_attractions = segment.get("top_attractions") or []
    selected_attractions = (
        segment.get("gemini_selected_attractions")
        or segment.get("selected_attractions")
        or top_attractions[:3]
    )
    top_lodging = segment.get("top_lodging") or []

    segment_distance_km = segment.get("segment_distance_km")
    if segment_distance_km is None:
        segment_distance_m = segment.get("segment_distance_m")
        if segment_distance_m is not None:
            segment_distance_km = round(float(segment_distance_m) / 1000, 1)

    return {
        "day": segment.get("day"),
        "day_label": segment.get("day_label") or f"Day {segment.get('day')}",
        "segment_distance_km": segment_distance_km,
        "segment_duration_seconds": segment.get("segment_duration_seconds"),
        "segment_path_points": segment.get("segment_path_points", []),
        "start_point": segment.get("start_point"),
        "mid_point": segment.get("mid_point"),
        "end_point": segment.get("end_point"),
        "assigned_route_attraction_count": segment.get("assigned_route_attraction_count"),
        "selected_attractions": selected_attractions,
        "top_attractions": top_attractions[:5],
        "recommended_lodging": segment.get("recommended_lodging"),
        "top_lodging": top_lodging[:3],
        "weather": segment.get("weather"),
    }


def _route_summary(route: dict[str, Any]) -> dict[str, Any]:
    segments = route.get("segments") or []
    return {
        "route_id": route.get("route_id"),
        "route_labels": route.get("route_labels", []),
        "distance_meters": route.get("distance_meters"),
        "duration": route.get("duration"),
        "polyline": route.get("polyline"),
        "geometry_point_count": route.get("geometry_point_count", 0),
        "geometry_distance_m": route.get("geometry_distance_m", 0.0),
        "sampled_points": route.get("sampled_points", []),
        "segment_count": len(segments),
        "segments": [_segment_summary(segment) for segment in segments],
        "road_alerts": route.get("road_alerts", {}),
        "weather_summary": route.get("weather_summary", {}),
        "crowd_signals": route.get("crowd_signals", {}),
        "route_attraction_pool_size": route.get("route_attraction_pool_size"),
        "route_attraction_pool_districts": route.get("route_attraction_pool_districts", []),
    }


def _slim_plan_payload(plan: dict[str, Any]) -> dict[str, Any]:
    routes = plan.get("routes") or []
    recommended_route = plan.get("recommended_route") or {}

    return {
        "saved_at_utc": plan.get("saved_at_utc"),
        "streamlit_built_at_utc": plan.get("streamlit_built_at_utc"),
        "session_id": plan.get("session_id"),
        "session_storage": plan.get("session_storage", {}),
        "trip_days": plan.get("trip_days"),
        "trip_dates": plan.get("trip_dates", []),
        "duration_text": plan.get("duration_text"),
        "route_count": plan.get("route_count", len(routes)),
        "warnings": plan.get("warnings", []),
        "origin_resolved": plan.get("origin_resolved"),
        "destination_resolved": plan.get("destination_resolved"),
        "routes": [_route_summary(route) for route in routes],
        "recommended_route": _route_summary(recommended_route) if recommended_route else {},
        "route_data": plan.get("route_data", {}),
        "road_alerts": plan.get("road_alerts", {}),
        "weather_data": plan.get("weather_data", {}),
        "traffic_data": plan.get("traffic_data", {}),
        "crowd_signals": plan.get("crowd_signals", {}),
        "flight_plan": plan.get("flight_plan", {}),
        "transport_cost": plan.get("transport_cost", {}),
        "travel_windows": plan.get("travel_windows", {}),
        "budget_summary": plan.get("budget_summary", {}),
        "package_explanation": plan.get("package_explanation", {}),
        "intelligence_refresh": plan.get("intelligence_refresh", {}),
        "nsgaii_summary": plan.get("nsgaii_summary"),
        "itinerary_guidance": plan.get("itinerary_guidance", {}),
        "itinerary_markdown": plan.get("itinerary_markdown", ""),
        "itinerary_source": plan.get("itinerary_source", "fallback"),
    }


app = FastAPI(
    title="TourUni Clean Run Backend",
    version="1.0.0",
    description="Standalone clean_run backend for Sri Lanka trip planning.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "status": "running",
        "service": "tourunipp2-clean-run-backend",
        "entrypoint": "clean_run.api:app",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "google_maps_key_configured": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
        "gemini_key_configured": bool(os.getenv("GEMINI_API_KEY")),
        "weather_api_key_configured": bool(os.getenv("WEATHER_API_KEY")),
        "mongodb_uri_configured": bool(os.getenv("MONGODB_URI")),
        "scheduled_jobs_configured": bool(os.getenv("CRON_SECRET")),
    }


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    try:
        response = get_intake_service().process_turn(req.message, req.session)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Chat failed: {safe_error_detail(exc, feature='Chat')}",
        ) from exc
    return {
        "session": response.session.model_dump(),
        "turn": response.turn.model_dump(),
    }


@app.post("/flights/search")
async def search_flights(req: FlightSearchRequest) -> dict[str, Any]:
    try:
        date.fromisoformat(req.departure_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="departure_date must be in YYYY-MM-DD format.") from exc

    try:
        result = await asyncio.to_thread(
            get_flight_search_service().search,
            FlightSearchPreferences(
                origin=req.origin,
                departure_date=req.departure_date,
                search_mode=req.search_mode,
                passengers=req.passengers,
                cabin_class=req.cabin_class,
                total_budget_lkr=req.total_budget_lkr,
                currency=req.currency,
            ),
        )
        result["budget_handoff"] = _estimate_flight_cost_lkr(
            result.get("cheapest_result"),
            total_budget_lkr=req.total_budget_lkr,
        )
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Flight search failed: {safe_error_detail(exc, feature='Flight search')}",
        ) from exc


@app.post("/flights/confirm")
async def confirm_flight(req: FlightConfirmRequest) -> dict[str, Any]:
    if req.selected_flight is None and not req.continue_without_live_fare:
        raise HTTPException(
            status_code=422,
            detail="Select a flight or explicitly continue without a live fare.",
        )

    handoff = _estimate_flight_cost_lkr(
        req.selected_flight,
        total_budget_lkr=req.session.trip_requirements.total_budget_lkr,
    )
    try:
        response = get_intake_service().confirm_flight(
            req.session,
            selected_flight=req.selected_flight,
            flight_budget_handoff=handoff,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "session": response.session.model_dump(),
        "turn": response.turn.model_dump(),
    }


@app.post("/plan")
async def plan(
    req: PlanRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        trip_start_date = date.fromisoformat(req.start_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="start_date must be in YYYY-MM-DD format.") from exc

    options = TripPlanOptions(
        include_gemini=req.include_gemini,
        include_roadlk=req.include_roadlk,
        include_weather=req.include_weather,
        include_crowd=req.include_crowd,
        place_strategy=req.place_strategy,
    )

    try:
        plan_payload = await asyncio.to_thread(
            build_trip_plan,
            origin_text=req.origin,
            destination_text=req.destination,
            duration_text=req.duration,
            start_date=trip_start_date,
            departure_time=req.departure_time,
            accommodation_budget_lkr=req.accommodation_budget_lkr,
            total_budget_lkr=req.total_budget_lkr,
            flight_usd_to_lkr_rate=req.flight_usd_to_lkr_rate,
            selected_flight=req.selected_flight,
            flight_plan=req.flight_plan,
            session_id=req.session_id,
            options=options,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Planning failed: {safe_error_detail(exc, feature='Planning')}",
        ) from exc

    user_id = optional_authenticated_user_id(authorization)
    session_id = plan_payload.get("session_id")
    repository = get_session_repository()
    if user_id and session_id and repository is not None:
        repository.assign_session_owner(session_id=session_id, user_id=user_id)

    if req.response_mode == "full":
        return plan_payload
    return _slim_plan_payload(plan_payload)


@app.get("/sessions/latest")
async def get_latest_session(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = authenticated_user_id(authorization)
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")

    document = repository.get_latest_session_for_user(user_id)
    if document is None:
        return {"session_id": None}

    return {
        "session_id": document.get("session_id"),
        "status": document.get("status"),
        "updated_at": document.get("updated_at"),
        "trip_requirements": document.get("trip_requirements", {}),
    }


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    payload = get_session_loader().get_full_session(session_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return payload


@app.get("/sessions/{session_id}/dashboard")
async def get_session_dashboard(session_id: str) -> dict[str, Any]:
    payload = get_session_loader().get_dashboard_payload(session_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return payload


@app.get("/sessions/{session_id}/chatbot-context")
async def get_session_chatbot_context(session_id: str) -> dict[str, Any]:
    payload = get_session_loader().get_chatbot_context(session_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return payload


@app.get("/sessions/{session_id}/condition-notifications")
async def get_condition_notifications(
    session_id: str,
    unread_only: bool = False,
    limit: int = 50,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")
    document = repository.get_session(session_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    _ensure_session_access(document, authorization)

    items = repository.get_condition_notifications(
        session_id=session_id,
        unread_only=unread_only,
        limit=limit,
    ) or []
    all_items = document.get("condition_notifications") or []
    return {
        "session_id": session_id,
        "items": items,
        "unread_count": sum(1 for item in all_items if isinstance(item, dict) and not item.get("read")),
        "total_count": sum(1 for item in all_items if isinstance(item, dict)),
    }


@app.post("/sessions/{session_id}/condition-notifications/read-all")
async def mark_all_condition_notifications_read(
    session_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")
    document = repository.get_session(session_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    _ensure_session_access(document, authorization)

    changed_count = repository.mark_all_condition_notifications_read(session_id=session_id)
    return {"session_id": session_id, "status": "ok", "changed_count": changed_count or 0}


@app.post("/sessions/{session_id}/condition-notifications/{notification_id}/read")
async def mark_condition_notification_read(
    session_id: str,
    notification_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")
    document = repository.get_session(session_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    _ensure_session_access(document, authorization)

    changed = repository.mark_condition_notification_read(
        session_id=session_id,
        notification_id=notification_id,
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Trip update not found.")
    return {"session_id": session_id, "notification_id": notification_id, "status": "ok"}


@app.get("/sessions/{session_id}/emotion-targets")
async def get_session_emotion_targets(session_id: str) -> dict[str, Any]:
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")

    session_document = repository.get_session(session_id)
    if session_document is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return build_emotion_checkin_targets(session_document)


@app.post("/sessions/{session_id}/refresh-intelligence")
async def refresh_session_intelligence(
    session_id: str,
    req: RefreshIntelligenceRequest | None = None,
) -> dict[str, Any]:
    active_req = req or RefreshIntelligenceRequest()
    options = TripPlanOptions(
        include_gemini=active_req.include_gemini,
        include_roadlk=active_req.include_roadlk,
        include_weather=active_req.include_weather,
        include_crowd=active_req.include_crowd,
    )
    try:
        payload = await asyncio.to_thread(
            refresh_trip_intelligence,
            session_id=session_id,
            departure_time=active_req.departure_time,
            options=options,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Refresh failed: {safe_error_detail(exc, feature='Intelligence refresh')}",
        ) from exc

    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    if active_req.response_mode == "full":
        return payload
    return {
        "session_id": payload.get("session_id"),
        "status": payload.get("status"),
        "changed_package": payload.get("changed_package", False),
        "updated_fields": payload.get("updated_fields", []),
        "condition_updates": payload.get("condition_updates", []),
        "notification_summary": payload.get("notification_summary", {}),
        "plan": _slim_plan_payload(payload.get("plan") or {}),
    }


@app.post("/internal/scheduled/refresh-conditions")
async def scheduled_refresh_conditions(
    req: ScheduledRefreshRequest | None = None,
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
) -> dict[str, Any]:
    """Refresh mutable trip intelligence for active or near-future saved trips."""
    _require_cron_secret(x_cron_secret)
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")

    active_req = req or ScheduledRefreshRequest()
    documents = await asyncio.to_thread(
        repository.list_scheduled_sessions,
        limit=active_req.limit,
    )
    options = TripPlanOptions(
        include_gemini=active_req.include_gemini,
        include_roadlk=True,
        include_weather=True,
        include_crowd=True,
    )

    async def refresh_one(session_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(
            refresh_trip_intelligence,
            session_id=session_id,
            departure_time=active_req.departure_time,
            options=options,
        )

    payload = await run_condition_refresh_batch(
        documents,
        refresh_one=refresh_one,
        now=datetime.now(timezone.utc),
        settings=SchedulerSettings.from_env(),
    )
    for failure in payload.get("failures") or []:
        failure["error"] = safe_error_detail(
            failure.get("error") or "Unknown refresh failure.",
            feature="Scheduled intelligence refresh",
        )
    return payload


@app.post("/internal/scheduled/mood-reminders")
async def scheduled_mood_reminders(
    req: ScheduledReminderRequest | None = None,
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
) -> dict[str, Any]:
    """Queue opt-in mood check-in prompts; this never runs image inference."""
    _require_cron_secret(x_cron_secret)
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")

    active_req = req or ScheduledReminderRequest()
    documents = await asyncio.to_thread(
        repository.list_scheduled_sessions,
        limit=active_req.limit,
    )
    return await asyncio.to_thread(
        queue_mood_reminders,
        repository,
        documents,
        now=datetime.now(timezone.utc),
        settings=SchedulerSettings.from_env(),
    )


@app.post("/sessions/{session_id}/contextual-alternatives")
async def get_contextual_alternatives(
    session_id: str,
    req: ContextualAlternativesRequest | None = None,
) -> dict[str, Any]:
    """Generate temporary alternatives without changing the saved itinerary."""
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")

    session_document = repository.get_session(session_id)
    if session_document is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    active_req = req or ContextualAlternativesRequest()
    return await asyncio.to_thread(
        build_contextual_alternatives,
        session_document,
        day=active_req.day,
        attraction_id=active_req.attraction_id,
        interests=active_req.interests,
        radius_meters=active_req.radius_meters,
        limit_per_attraction=active_req.limit_per_attraction,
        max_attractions=active_req.max_attractions,
        force=active_req.force,
    )


@app.post("/sessions/{session_id}/emotion-checkins")
async def add_emotion_checkin(session_id: str, req: EmotionCheckinRequest) -> dict[str, Any]:
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")

    session_document = repository.get_session(session_id)
    if session_document is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    checkin = sanitize_emotion_checkin(req.model_dump())
    checkin = attach_location_context(
        checkin=checkin,
        session_document=session_document,
    )
    if checkin.get("checkin_type") == "start_of_day":
        recommendation = build_start_of_day_mood_recommendation(
            checkin=checkin,
            session_document=session_document,
        )
    else:
        recommendation = build_emotion_recommendation(
            checkin=checkin,
            session_document=session_document,
        )
    emotion_checkins = list(session_document.get("emotion_checkins") or [])
    emotion_checkins.append(checkin)
    emotion_summary = build_emotion_summary(
        checkins=emotion_checkins,
        latest_recommendation=recommendation,
    )
    saved = repository.add_emotion_checkin(
        session_id=session_id,
        checkin=checkin,
        recommendation=recommendation,
        emotion_summary=emotion_summary,
    )
    if not saved:
        raise HTTPException(status_code=404, detail="Session not found.")

    nearby_tips = await asyncio.to_thread(
        build_nearby_emotion_tips,
        session_document,
        checkin.get("emotion_label", "neutral"),
        req.hobbies,
    )

    return {
        "session_id": session_id,
        "checkin": checkin,
        "recommendation": recommendation,
        "emotion_summary": emotion_summary,
        "nearby_tips": nearby_tips,
        "privacy": {
            "raw_image_received_by_backend": False,
            "raw_image_stored": False,
            "identity_recognition": False,
            "local_inference_required": True,
        },
    }


@app.post("/sessions/{session_id}/emotion-checkins/image")
async def add_emotion_checkin_image(
    session_id: str,
    image: UploadFile,
    day: int = Form(...),
    checkin_type: str = Form("start_of_day"),
    hobbies: str = Form("[]"),
) -> dict[str, Any]:
    repository = get_session_repository()
    if repository is None:
        raise HTTPException(status_code=503, detail="Session storage is not configured.")

    session_document = repository.get_session(session_id)
    if session_document is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file.")

    try:
        classification = await asyncio.to_thread(classify_image_bytes, image_bytes)
    except Exception as exc:
        if "face detected" in str(exc).lower():
            raise HTTPException(status_code=400, detail="No face detected. Try a brighter front-facing photo.")
        raise HTTPException(
            status_code=500,
            detail=f"Emotion inference failed: {safe_error_detail(exc, feature='Emotion inference')}",
        ) from exc

    selected_hobbies = _parse_hobbies(hobbies)
    checkin_data = {
        "checkin_type": checkin_type,
        "day": day,
        **classification,
        "local_inference": False,
        "hobbies": selected_hobbies,
    }

    checkin = sanitize_emotion_checkin(checkin_data)
    checkin = attach_location_context(
        checkin=checkin,
        session_document=session_document,
    )
    if checkin.get("checkin_type") == "start_of_day":
        recommendation = build_start_of_day_mood_recommendation(
            checkin=checkin,
            session_document=session_document,
        )
    else:
        recommendation = build_emotion_recommendation(
            checkin=checkin,
            session_document=session_document,
        )
    
    emotion_checkins = list(session_document.get("emotion_checkins") or [])
    emotion_checkins.append(checkin)
    emotion_summary = build_emotion_summary(
        checkins=emotion_checkins,
        latest_recommendation=recommendation,
    )
    
    saved = repository.add_emotion_checkin(
        session_id=session_id,
        checkin=checkin,
        recommendation=recommendation,
        emotion_summary=emotion_summary,
    )
    if not saved:
        raise HTTPException(status_code=404, detail="Session not found.")

    nearby_tips = await asyncio.to_thread(
        build_nearby_emotion_tips,
        session_document,
        checkin.get("emotion_label", "neutral"),
        selected_hobbies,
    )

    return {
        "session_id": session_id,
        "checkin": checkin,
        "recommendation": recommendation,
        "emotion_summary": emotion_summary,
        "nearby_tips": nearby_tips,
        "privacy": {
            "raw_image_received_by_backend": True,
            "raw_image_stored": False,
            "identity_recognition": False,
            "local_inference_required": False,
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("clean_run.api:app", host="0.0.0.0", port=port)
