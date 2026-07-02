from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

from clean_run.pipeline.service import CleanRunPipelineService


@dataclass
class TripPlanOptions:
    include_gemini: bool = True
    include_roadlk: bool = True
    include_weather: bool = True
    include_crowd: bool = True
    place_strategy: str = "nearby"


class _IdentityRouteService:
    def enrich(self, route_result, **kwargs):
        return route_result


def _service_for_options(options: TripPlanOptions) -> CleanRunPipelineService:
    service = CleanRunPipelineService()
    if not options.include_roadlk:
        service.road_service = _IdentityRouteService()
    if not options.include_weather:
        service.weather_service = _IdentityRouteService()
    if not options.include_crowd:
        service.crowd_service = _IdentityRouteService()
    return service


def _normalize_plan_payload(plan: dict[str, Any]) -> dict[str, Any]:
    payload = dict(plan)
    route_data = dict(payload.get("route_data") or {})
    recommended_route = payload.get("recommended_route") or {}

    distance_meters = route_data.get("distance_meters")
    if distance_meters is None:
        distance_meters = recommended_route.get("distance_meters")
    if distance_meters is not None:
        route_data["distance_meters"] = distance_meters
        route_data.setdefault("distance_km", round(float(distance_meters) / 1000, 1))
        route_data.setdefault("distance_str", f"{float(distance_meters) / 1000:.1f} km")

    payload["route_data"] = route_data
    payload.setdefault("nsgaii_summary", {})
    return payload


async def invoke_trip_plan(
    *,
    origin_text: str,
    destination_text: str,
    duration_text: str,
    start_date: date,
    departure_time: str = "08:00",
    accommodation_budget_lkr: float | None = None,
    total_budget_lkr: float | None = None,
    flight_usd_to_lkr_rate: float | None = None,
    selected_flight: dict[str, Any] | None = None,
    flight_plan: dict[str, Any] | None = None,
    session_id: str | None = None,
    options: TripPlanOptions | None = None,
) -> dict[str, Any]:
    active_options = options or TripPlanOptions()
    service = _service_for_options(active_options)
    plan = await asyncio.to_thread(
        service.run,
        origin=origin_text,
        destination=destination_text,
        duration=duration_text,
        start_date=start_date.isoformat(),
        departure_time=departure_time,
        place_strategy=active_options.place_strategy,
        accommodation_budget_lkr=accommodation_budget_lkr,
        total_budget_lkr=total_budget_lkr,
        flight_usd_to_lkr_rate=flight_usd_to_lkr_rate,
        selected_flight=selected_flight,
        flight_plan=flight_plan,
        session_id=session_id,
        use_gemini_itinerary=active_options.include_gemini,
    )
    return _normalize_plan_payload(plan)


def build_trip_plan(
    *,
    origin_text: str,
    destination_text: str,
    duration_text: str,
    start_date: date,
    departure_time: str = "08:00",
    accommodation_budget_lkr: float | None = None,
    total_budget_lkr: float | None = None,
    flight_usd_to_lkr_rate: float | None = None,
    selected_flight: dict[str, Any] | None = None,
    flight_plan: dict[str, Any] | None = None,
    session_id: str | None = None,
    options: TripPlanOptions | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        invoke_trip_plan(
            origin_text=origin_text,
            destination_text=destination_text,
            duration_text=duration_text,
            start_date=start_date,
            departure_time=departure_time,
            accommodation_budget_lkr=accommodation_budget_lkr,
            total_budget_lkr=total_budget_lkr,
            flight_usd_to_lkr_rate=flight_usd_to_lkr_rate,
            selected_flight=selected_flight,
            flight_plan=flight_plan,
            session_id=session_id,
            options=options,
        )
    )


def refresh_trip_intelligence(
    *,
    session_id: str,
    departure_time: str = "08:00",
    options: TripPlanOptions | None = None,
) -> dict[str, Any] | None:
    active_options = options or TripPlanOptions()
    service = _service_for_options(active_options)
    return service.refresh_intelligence(
        session_id=session_id,
        departure_time=departure_time,
        use_gemini_itinerary=active_options.include_gemini,
    )
