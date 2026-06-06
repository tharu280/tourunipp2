from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from chat.bot import TravelIntakeChatbot
from chat.schemas import ChatSessionState
from planner_pipeline import TripPlanOptions
from trip_graph.graph import invoke_trip_graph


load_dotenv(".env")
load_dotenv("google_routes/.env")

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"


class ChatRequest(BaseModel):
    message: str = Field(description="Latest user message.")
    session: ChatSessionState | None = Field(
        default=None,
        description="Optional prior chat session state.",
    )


class PlanRequest(BaseModel):
    origin: str = Field(description="Trip starting point.")
    destination: str = Field(description="Trip ending point.")
    duration: str = Field(description="Trip duration such as '4 days'.")
    start_date: str = Field(description="Trip start date in YYYY-MM-DD format.")
    departure_time: str = Field(
        default="08:00",
        description="Preferred departure time in HH:MM 24-hour format.",
    )
    include_gemini: bool = True
    include_roadlk: bool = True
    include_weather: bool = True
    include_crowd: bool = True
    place_strategy: str = Field(default="nearby", pattern="^(nearby|text)$")
    response_mode: str = Field(
        default="slim",
        pattern="^(slim|full)$",
        description="Use 'slim' for frontend-safe payloads and 'full' for internal debugging.",
    )


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_chatbot() -> TravelIntakeChatbot:
    return TravelIntakeChatbot()


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
        "crowd_signals": plan.get("crowd_signals", {}),
        "travel_windows": plan.get("travel_windows", {}),
        "nsgaii_summary": plan.get("nsgaii_summary"),
        "itinerary_guidance": plan.get("itinerary_guidance", {}),
        "itinerary_markdown": plan.get("itinerary_markdown", ""),
        "itinerary_source": plan.get("itinerary_source", "fallback"),
    }


app = FastAPI(
    title="RouteMVP Planner API",
    version="1.0.0",
    description=(
        "FastAPI wrapper around the LangGraph-based Sri Lanka route planning backend."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> Any:
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return {
        "status": "running",
        "service": "routemvp-planner-api",
        "mode": "langgraph-backend",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "google_maps_key_configured": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
        "gemini_key_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    try:
        response = get_chatbot().process_turn(req.message, req.session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc

    return {
        "session": response.session.model_dump(),
        "turn": response.turn.model_dump(),
    }


@app.post("/plan")
async def plan(req: PlanRequest) -> dict[str, Any]:
    try:
        trip_start_date = date.fromisoformat(req.start_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="start_date must be in YYYY-MM-DD format.",
        ) from exc

    options = TripPlanOptions(
        include_gemini=req.include_gemini,
        include_roadlk=req.include_roadlk,
        include_weather=req.include_weather,
        include_crowd=req.include_crowd,
        place_strategy=req.place_strategy,
    )

    try:
        plan_payload = await invoke_trip_graph(
            origin_text=req.origin,
            destination_text=req.destination,
            duration_text=req.duration,
            start_date=trip_start_date,
            departure_time=req.departure_time,
            options=options,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Planning failed: {exc}") from exc

    if req.response_mode == "full":
        return plan_payload
    return _slim_plan_payload(plan_payload)


@app.get("/{full_path:path}")
async def frontend(full_path: str) -> Any:
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend build not found.")

    requested = FRONTEND_DIST / full_path
    if full_path and requested.exists() and requested.is_file():
        return FileResponse(requested)
    return FileResponse(FRONTEND_INDEX)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("api:app", host="0.0.0.0", port=port)
