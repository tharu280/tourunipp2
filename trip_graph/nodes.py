from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from crowd.enrich_routes import enrich_route as enrich_crowd_route
from gemini_refine.refine_routes import refine_segment
from google_places.client import resolve_place_query
from google_places.enrich_routes import enrich_route as enrich_places_route
from google_routes.client import build_route_profiles, compute_routes
from nsgaii.select_routes import (
    assign_compromise_scores,
    assign_crowding_distance,
    build_candidate,
    build_summary,
    infer_active_objectives,
    nondominated_sort,
)
from roadlk.enrich_routes import enrich_route as enrich_roadlk_route
from travel_windows.client import build_travel_windows
from weather.client import build_trip_dates
from weather.enrich_routes import enrich_route as enrich_weather_route
from itinerary.generator import build_itinerary_output
from traffic.client import enrich_route_with_live_traffic

from trip_graph.state import TripGraphState

ROUTE_WORKERS = 4


def parse_trip_days(duration_text: str) -> int:
    normalized = duration_text.strip().lower()
    day_match = re.search(r"(\d+)\s*day", normalized)
    if day_match:
        return max(int(day_match.group(1)), 1)

    week_match = re.search(r"(\d+)\s*week", normalized)
    if week_match:
        return max(int(week_match.group(1)) * 7, 1)

    number_match = re.search(r"\d+", normalized)
    if number_match:
        return max(int(number_match.group(0)), 1)

    raise ValueError(f"Could not understand duration: {duration_text}")


def _rank_routes(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    routes = payload.get("routes", [])
    candidates = [build_candidate(route) for route in routes]
    if not candidates:
        return None, None

    objectives = infer_active_objectives(candidates)
    if not objectives:
        return None, routes[0].get("route_id") if routes else None

    for candidate in candidates:
        candidate.used_objectives = {
            objective: float(candidate.objectives[objective])
            for objective in objectives
            if candidate.objectives[objective] is not None
        }

    fronts = nondominated_sort(candidates, objectives)
    for front in fronts:
        assign_crowding_distance(front, objectives)
    assign_compromise_scores(candidates, objectives)

    summary = build_summary(candidates, objectives)
    return summary, summary.get("recommended_route_id")


def _select_route(payload: dict[str, Any], route_id: str | None) -> dict[str, Any] | None:
    if not route_id:
        return None
    for route in payload.get("routes", []):
        if route.get("route_id") == route_id:
            return route
    return None


def _build_route_data(route: dict[str, Any] | None, *, route_count: int) -> dict[str, Any]:
    if not route:
        return {"error": "No route selected"}

    distance_meters = float(route.get("distance_meters") or 0.0)
    duration_value = route.get("duration")
    duration_seconds = None
    if isinstance(duration_value, str) and duration_value.endswith("s"):
        try:
            duration_seconds = int(float(duration_value[:-1]))
        except ValueError:
            duration_seconds = None

    if duration_seconds is None:
        duration_str = "Unknown"
    else:
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        duration_str = f"{hours}h {minutes}m"

    return {
        "route_id": route.get("route_id"),
        "route_count": route_count,
        "summary": f"{distance_meters / 1000:.1f} km in {duration_str}",
        "distance_km": round(distance_meters / 1000, 1),
        "duration_str": duration_str,
        "distance_meters": distance_meters,
        "duration_seconds": duration_seconds,
        "route_labels": route.get("route_labels", []),
        "segments": route.get("segments", []),
        "traffic_data": route.get("traffic_data", {}),
    }


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


def _payload_with_selection(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    summary, recommended_route_id = _rank_routes(payload)
    recommended_route = _select_route(payload, recommended_route_id) if recommended_route_id else (
        payload.get("routes") or [None]
    )[0]
    payload["nsgaii_summary"] = summary
    payload["recommended_route"] = recommended_route
    return payload, recommended_route


async def resolve_trip_node(state: TripGraphState) -> TripGraphState:
    def resolve():
        trip_days = parse_trip_days(state["duration_text"])
        trip_dates = build_trip_dates(state["start_date"], trip_days)
        origin = resolve_place_query(query=state["origin_text"])
        destination = resolve_place_query(query=state["destination_text"])
        return trip_days, trip_dates, origin, destination

    trip_days, trip_dates, origin, destination = await asyncio.to_thread(resolve)
    return {
        "trip_days": trip_days,
        "trip_dates": trip_dates,
        "warnings": [],
        "origin_resolved": origin,
        "destination_resolved": destination,
    }


async def route_generation_node(state: TripGraphState) -> TripGraphState:
    options = state.get("options", {})

    def build():
        response_payload = compute_routes(
            origin_lat=state["origin_resolved"]["lat"],
            origin_lng=state["origin_resolved"]["lng"],
            destination_lat=state["destination_resolved"]["lat"],
            destination_lng=state["destination_resolved"]["lng"],
            compute_alternative_routes=True,
        )
        route_payload = build_route_profiles(
            response_payload=response_payload,
            origin_lat=state["origin_resolved"]["lat"],
            origin_lng=state["origin_resolved"]["lng"],
            destination_lat=state["destination_resolved"]["lat"],
            destination_lng=state["destination_resolved"]["lng"],
        )
        with ThreadPoolExecutor(max_workers=min(ROUTE_WORKERS, max(len(route_payload.get("routes", [])), 1))) as executor:
            routes = list(
                executor.map(
                    lambda route: enrich_places_route(
                        route,
                        trip_days=state["trip_days"],
                        strategy=options.get("place_strategy", "nearby"),
                    ),
                    route_payload.get("routes", []),
                )
            )
        payload = {
            **route_payload,
            "trip_days": state["trip_days"],
            "trip_dates": state["trip_dates"],
            "origin_resolved": state["origin_resolved"],
            "destination_resolved": state["destination_resolved"],
            "duration_text": state["duration_text"],
            "routes": routes,
        }
        payload, recommended_route = _payload_with_selection(payload)

        if options.get("include_gemini", True) and recommended_route:
            segments = recommended_route.get("segments", [])
            with ThreadPoolExecutor(max_workers=min(len(segments), ROUTE_WORKERS) or 1) as executor:
                refined_segments = list(
                    executor.map(
                        lambda segment: refine_segment(
                            route_id=recommended_route["route_id"],
                            trip_days=state["trip_days"],
                            segment=segment,
                        ),
                        segments,
                    )
                )
            refined_route = {**recommended_route, "segments": refined_segments}
            payload["routes"] = [
                refined_route if route.get("route_id") == refined_route.get("route_id") else route
                for route in payload.get("routes", [])
            ]
            recommended_route = refined_route

        return payload, recommended_route

    payload, recommended_route = await asyncio.to_thread(build)
    return {
        "route_payload": payload,
        "recommended_route": recommended_route,
        "route_data": _build_route_data(
            recommended_route,
            route_count=payload.get("route_count", 0),
        ),
        "nsgaii_summary": payload.get("nsgaii_summary"),
    }


async def roadlk_node(state: TripGraphState) -> TripGraphState:
    options = state.get("options", {})
    if not options.get("include_roadlk", True):
        return {
            "road_alerts": {
                "risk_level": "unknown",
                "critical_count": 0,
                "incidents": [],
                "skipped": True,
            }
        }

    warnings = list(state.get("warnings", []))

    def enrich():
        routes_in = state["route_payload"].get("routes", [])
        with ThreadPoolExecutor(max_workers=min(ROUTE_WORKERS, max(len(routes_in), 1))) as executor:
            routes = list(executor.map(enrich_roadlk_route, routes_in))
        payload = {**state["route_payload"], "routes": routes}
        return _payload_with_selection(payload)

    try:
        payload, recommended_route = await asyncio.to_thread(enrich)
    except Exception as exc:
        warnings.append(f"RoadLK enrichment skipped: {exc}")
        return {"warnings": warnings}

    return {
        "warnings": warnings,
        "route_payload": payload,
        "recommended_route": recommended_route,
        "route_data": _build_route_data(recommended_route, route_count=payload.get("route_count", 0)),
        "road_alerts": (recommended_route or {}).get("road_alerts", {}),
        "nsgaii_summary": payload.get("nsgaii_summary"),
    }


async def weather_node(state: TripGraphState) -> TripGraphState:
    options = state.get("options", {})
    if not options.get("include_weather", True):
        return {"weather_data": {"locations": [], "summary": {"risk_level": "unknown"}, "skipped": True}}

    warnings = list(state.get("warnings", []))

    def enrich():
        routes_in = state["route_payload"].get("routes", [])
        with ThreadPoolExecutor(max_workers=min(ROUTE_WORKERS, max(len(routes_in), 1))) as executor:
            routes = list(
                executor.map(
                    lambda route: enrich_weather_route(route=route, trip_dates=state["trip_dates"]),
                    routes_in,
                )
            )
        payload = {**state["route_payload"], "routes": routes}
        return _payload_with_selection(payload)

    try:
        payload, recommended_route = await asyncio.to_thread(enrich)
    except Exception as exc:
        warnings.append(f"Weather enrichment skipped: {exc}")
        return {"warnings": warnings}

    return {
        "warnings": warnings,
        "route_payload": payload,
        "recommended_route": recommended_route,
        "route_data": _build_route_data(recommended_route, route_count=payload.get("route_count", 0)),
        "weather_data": _build_weather_data(recommended_route),
        "nsgaii_summary": payload.get("nsgaii_summary"),
    }


async def crowd_node(state: TripGraphState) -> TripGraphState:
    options = state.get("options", {})
    if not options.get("include_crowd", True):
        return {"crowd_signals": {"risk_level": "unknown", "signal_score": 0, "skipped": True}}

    warnings = list(state.get("warnings", []))

    def enrich():
        routes_in = state["route_payload"].get("routes", [])
        with ThreadPoolExecutor(max_workers=min(ROUTE_WORKERS, max(len(routes_in), 1))) as executor:
            routes = list(
                executor.map(
                    lambda route: enrich_crowd_route(
                        route=route,
                        start_date=state["start_date"],
                        trip_days=state["trip_days"],
                    ),
                    routes_in,
                )
            )
        payload = {**state["route_payload"], "routes": routes}
        return _payload_with_selection(payload)

    try:
        payload, recommended_route = await asyncio.to_thread(enrich)
    except Exception as exc:
        warnings.append(f"Crowd enrichment skipped: {exc}")
        return {"warnings": warnings}

    return {
        "warnings": warnings,
        "route_payload": payload,
        "recommended_route": recommended_route,
        "route_data": _build_route_data(recommended_route, route_count=payload.get("route_count", 0)),
        "crowd_signals": (recommended_route or {}).get("crowd_signals", {}),
        "nsgaii_summary": payload.get("nsgaii_summary"),
    }


async def traffic_node(state: TripGraphState) -> TripGraphState:
    warnings = list(state.get("warnings", []))
    recommended_route = state.get("recommended_route")
    if not recommended_route:
        return {"warnings": warnings, "traffic_data": {"status": "unavailable"}}

    def enrich():
        return enrich_route_with_live_traffic(
            route=recommended_route,
            origin_lat=state["origin_resolved"]["lat"],
            origin_lng=state["origin_resolved"]["lng"],
            destination_lat=state["destination_resolved"]["lat"],
            destination_lng=state["destination_resolved"]["lng"],
            start_date=state["start_date"],
            departure_time=state.get("departure_time"),
        )

    try:
        traffic_enriched_route = await asyncio.to_thread(enrich)
    except Exception as exc:
        warnings.append(f"Traffic enrichment skipped: {exc}")
        return {"warnings": warnings, "traffic_data": {"status": "unavailable"}}

    route_payload = state.get("route_payload") or {}
    routes = [
        traffic_enriched_route if route.get("route_id") == traffic_enriched_route.get("route_id") else route
        for route in route_payload.get("routes", [])
    ]
    payload = {**route_payload, "routes": routes, "recommended_route": traffic_enriched_route}

    updated_crowd_signals = await asyncio.to_thread(
        enrich_crowd_route,
        route=traffic_enriched_route,
        start_date=state["start_date"],
        trip_days=state["trip_days"],
    )
    traffic_enriched_route = updated_crowd_signals
    payload["routes"] = [
        traffic_enriched_route if route.get("route_id") == traffic_enriched_route.get("route_id") else route
        for route in payload.get("routes", [])
    ]
    payload["recommended_route"] = traffic_enriched_route

    return {
        "warnings": warnings,
        "route_payload": payload,
        "recommended_route": traffic_enriched_route,
        "route_data": _build_route_data(traffic_enriched_route, route_count=payload.get("route_count", 0)),
        "traffic_data": traffic_enriched_route.get("traffic_data", {}),
        "crowd_signals": traffic_enriched_route.get("crowd_signals", state.get("crowd_signals", {})),
        "nsgaii_summary": payload.get("nsgaii_summary"),
    }


async def travel_windows_node(state: TripGraphState) -> TripGraphState:
    route_data = state.get("route_data") or {}
    if route_data.get("error"):
        return {
            "travel_windows": {
                "summary": "Travel window prediction is unavailable because route data is missing.",
                "days": [],
                "chart_rows": [],
            }
        }

    try:
        travel_windows = await asyncio.to_thread(
            build_travel_windows,
            start_date=state["start_date"],
            trip_days=state["trip_days"],
            departure_time=state.get("departure_time", "08:00"),
            weather_data=state.get("weather_data", {}),
            road_alerts=state.get("road_alerts", {}),
            crowd_signals=state.get("crowd_signals", {}),
            traffic_data=state.get("traffic_data", {}),
            route_data=route_data,
        )
        return {"travel_windows": travel_windows}
    except Exception as exc:
        return {
            "travel_windows": {
                "summary": f"Travel window prediction failed: {exc}",
                "days": [],
                "chart_rows": [],
            }
        }


async def assemble_plan_node(state: TripGraphState) -> TripGraphState:
    payload = state.get("route_payload", {})
    recommended_route = state.get("recommended_route")

    final_plan = {
        **payload,
        "trip_days": state.get("trip_days"),
        "trip_dates": state.get("trip_dates"),
        "origin_resolved": state.get("origin_resolved"),
        "destination_resolved": state.get("destination_resolved"),
        "duration_text": state.get("duration_text"),
        "streamlit_built_at_utc": datetime.now(timezone.utc).isoformat(),
        "warnings": state.get("warnings", []),
        "nsgaii_summary": state.get("nsgaii_summary"),
        "recommended_route": recommended_route,
        "route_data": state.get("route_data"),
        "road_alerts": state.get("road_alerts", {}),
        "weather_data": state.get("weather_data", {}),
        "traffic_data": state.get("traffic_data", {}),
        "crowd_signals": state.get("crowd_signals", {}),
        "travel_windows": state.get("travel_windows", {}),
        "itinerary_guidance": state.get("itinerary_guidance", {}),
        "itinerary_markdown": state.get("itinerary_markdown", ""),
        "itinerary_source": state.get("itinerary_source", "fallback"),
    }

    return {"final_plan": final_plan}


async def itinerary_node(state: TripGraphState) -> TripGraphState:
    plan_context = {
        **(state.get("route_payload") or {}),
        "trip_days": state.get("trip_days"),
        "trip_dates": state.get("trip_dates"),
        "origin_resolved": state.get("origin_resolved"),
        "destination_resolved": state.get("destination_resolved"),
        "duration_text": state.get("duration_text"),
        "route_data": state.get("route_data"),
        "recommended_route": state.get("recommended_route"),
        "road_alerts": state.get("road_alerts", {}),
        "weather_data": state.get("weather_data", {}),
        "traffic_data": state.get("traffic_data", {}),
        "crowd_signals": state.get("crowd_signals", {}),
        "travel_windows": state.get("travel_windows", {}),
    }

    use_gemini = bool((state.get("options") or {}).get("include_gemini", True))
    warnings = list(state.get("warnings", []))

    def build():
        return build_itinerary_output(plan_context, use_gemini=use_gemini)

    try:
        itinerary_output = await asyncio.to_thread(build)
    except Exception as exc:
        warnings.append(f"Itinerary generation skipped: {exc}")
        fallback = build_itinerary_output(plan_context, use_gemini=False)
        return {
            "warnings": warnings,
            "itinerary_guidance": fallback.get("itinerary_guidance", {}),
            "itinerary_markdown": fallback.get("itinerary_markdown", ""),
            "itinerary_source": fallback.get("itinerary_source", "fallback"),
        }

    generation_warning = (itinerary_output.get("itinerary_guidance") or {}).get("generation_warning")
    if generation_warning:
        warnings.append(str(generation_warning))

    return {
        "warnings": warnings,
        "itinerary_guidance": itinerary_output.get("itinerary_guidance", {}),
        "itinerary_markdown": itinerary_output.get("itinerary_markdown", ""),
        "itinerary_source": itinerary_output.get("itinerary_source", "fallback"),
    }
