from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from clean_run.routes.generate import RouteGenerationResult
from clean_run.trip.resolve import ResolvedTripContext
from clean_run.postprocess.travel_windows_engine import build_travel_windows


TravelWindowsBuilder = Callable[..., dict[str, Any]]


def _build_weather_data(route: dict[str, Any] | None) -> dict[str, Any]:
    if not route:
        return {"locations": [], "summary": {"risk_level": "unknown"}}

    locations = []
    for segment in route.get("segments", []):
        weather = segment.get("weather") or {}
        locations.append(
            {
                "label": f"day_{segment.get('day')}_segment",
                "name": f"Day {segment.get('day')} route segment",
                "forecast": weather.get("forecast") or {"status": "unavailable"},
                "risk": weather.get("risk"),
            }
        )
    return {
        "locations": locations,
        "summary": route.get("weather_summary", {}),
    }


@dataclass
class TravelWindowsService:
    builder: TravelWindowsBuilder = build_travel_windows

    def build(
        self,
        *,
        route_result: RouteGenerationResult,
        resolved_trip: ResolvedTripContext,
        departure_time: str = "08:00",
    ) -> dict[str, Any]:
        recommended = route_result.recommended_route.model_dump() if route_result.recommended_route else {}
        route_data = {
            "route_id": recommended.get("route_id"),
            "route_count": route_result.route_count,
            "distance_km": round(float(recommended.get("distance_meters") or 0) / 1000, 1),
            "distance_meters": recommended.get("distance_meters"),
            "duration_str": recommended.get("duration"),
            "segments": recommended.get("segments", []),
        }
        return self.builder(
            start_date=resolved_trip.start_date,
            trip_days=resolved_trip.trip_days,
            departure_time=departure_time,
            weather_data=_build_weather_data(recommended),
            road_alerts=recommended.get("road_alerts", {}),
            crowd_signals=recommended.get("crowd_signals", {}),
            traffic_data=recommended.get("traffic_data", {}),
            route_data=route_data,
        )
