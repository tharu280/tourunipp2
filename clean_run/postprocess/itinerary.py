from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from clean_run.routes.generate import RouteGenerationResult
from clean_run.trip.resolve import ResolvedTripContext
from clean_run.postprocess.itinerary_engine import build_itinerary_output


ItineraryBuilder = Callable[..., dict[str, Any]]


def _plan_context(
    *,
    resolved_trip: ResolvedTripContext,
    route_result: RouteGenerationResult,
    travel_windows: dict[str, Any],
) -> dict[str, Any]:
    recommended = route_result.recommended_route.model_dump() if route_result.recommended_route else {}
    return {
        "saved_at_utc": route_result.saved_at_utc,
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
            "distance_km": round(float(recommended.get("distance_meters") or 0) / 1000, 1),
            "duration_str": recommended.get("duration"),
            "segments": recommended.get("segments", []),
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
    }


@dataclass
class ItineraryService:
    builder: ItineraryBuilder = build_itinerary_output

    def build(
        self,
        *,
        route_result: RouteGenerationResult,
        resolved_trip: ResolvedTripContext,
        travel_windows: dict[str, Any],
        use_gemini: bool = False,
    ) -> dict[str, Any]:
        return self.builder(
            _plan_context(
                resolved_trip=resolved_trip,
                route_result=route_result,
                travel_windows=travel_windows,
            ),
            use_gemini=use_gemini,
        )
