from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from clean_run.routes.generate import RouteGenerationResult
from clean_run.trip.resolve import ResolvedTripContext


def _format_distance(distance_meters: float | int | None) -> str | None:
    if distance_meters is None:
        return None
    try:
        return f"{float(distance_meters) / 1000:.1f} km"
    except (TypeError, ValueError):
        return None


def _parse_duration_seconds(duration_value: str | None) -> int | None:
    if not duration_value or not isinstance(duration_value, str) or not duration_value.endswith("s"):
        return None
    try:
        return int(float(duration_value[:-1]))
    except ValueError:
        return None


def _format_duration(duration_value: str | None) -> str | None:
    duration_seconds = _parse_duration_seconds(duration_value)
    if duration_seconds is None:
        return duration_value

    hours, remainder = divmod(duration_seconds, 3600)
    minutes, _seconds = divmod(remainder, 60)

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def assemble_plan(
    *,
    resolved_trip: ResolvedTripContext,
    route_result: RouteGenerationResult,
    travel_windows: dict[str, Any],
    itinerary_output: dict[str, Any],
    flight_plan: dict[str, Any] | None = None,
    budget_summary: dict[str, Any] | None = None,
    transport_cost: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    recommended = route_result.recommended_route.model_dump() if route_result.recommended_route else {}
    recommended_duration = recommended.get("duration")
    transport_cost_payload = transport_cost or {}
    return {
        "saved_at_utc": route_result.saved_at_utc,
        "streamlit_built_at_utc": datetime.now(timezone.utc).isoformat(),
        "trip_days": resolved_trip.trip_days,
        "trip_dates": resolved_trip.trip_dates,
        "origin_resolved": resolved_trip.origin_resolved.model_dump(),
        "destination_resolved": resolved_trip.destination_resolved.model_dump(),
        "duration_text": resolved_trip.duration_text,
        "route_count": route_result.route_count,
        "routes": [route.model_dump() for route in route_result.routes],
        "recommended_route": recommended,
        "route_data": {
            "route_id": recommended.get("route_id"),
            "route_count": route_result.route_count,
            "distance_meters": recommended.get("distance_meters"),
            "distance_km": round(float(recommended.get("distance_meters") or 0) / 1000, 1),
            "distance_str": _format_distance(recommended.get("distance_meters")),
            "duration_str": _format_duration(recommended_duration),
            "duration_raw": recommended_duration,
            "segments": recommended.get("segments", []),
            "traffic_data": recommended.get("traffic_data", {}),
            "transport_cost": transport_cost_payload,
        },
        "road_alerts": recommended.get("road_alerts", {}),
        "weather_data": {
            "locations": [
                {
                    "label": f"day_{segment.get('day')}_segment",
                    "name": f"Day {segment.get('day')} route segment",
                    "forecast": (segment.get("weather") or {}).get("forecast") or {"status": "unavailable"},
                    "risk": (segment.get("weather") or {}).get("risk"),
                }
                for segment in recommended.get("segments", [])
            ],
            "summary": recommended.get("weather_summary", {}),
        },
        "traffic_data": recommended.get("traffic_data", {}),
        "crowd_signals": recommended.get("crowd_signals", {}),
        "travel_windows": travel_windows,
        "flight_plan": flight_plan or {},
        "transport_cost": transport_cost_payload,
        "budget_summary": budget_summary or {},
        "itinerary_guidance": itinerary_output.get("itinerary_guidance", {}),
        "itinerary_markdown": itinerary_output.get("itinerary_markdown", ""),
        "itinerary_source": itinerary_output.get("itinerary_source", "fallback"),
        "warnings": warnings or [],
    }
