from __future__ import annotations

from typing import Any, TypedDict


class TripGraphOptions(TypedDict, total=False):
    include_gemini: bool
    include_roadlk: bool
    include_weather: bool
    include_crowd: bool
    place_strategy: str


class TripGraphState(TypedDict, total=False):
    origin_text: str
    destination_text: str
    duration_text: str
    start_date: str
    departure_time: str
    options: TripGraphOptions

    trip_days: int
    trip_dates: list[str]
    warnings: list[str]

    origin_resolved: dict[str, Any]
    destination_resolved: dict[str, Any]

    route_payload: dict[str, Any]
    recommended_route: dict[str, Any]
    route_data: dict[str, Any]
    road_alerts: dict[str, Any]
    weather_data: dict[str, Any]
    traffic_data: dict[str, Any]
    crowd_signals: dict[str, Any]
    travel_windows: dict[str, Any]
    nsgaii_summary: dict[str, Any] | None
    itinerary_guidance: dict[str, Any]
    itinerary_markdown: str
    itinerary_source: str

    final_plan: dict[str, Any]
