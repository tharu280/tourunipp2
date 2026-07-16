from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .session_repository import SessionRepository


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
        "is_overnight_stop": bool(segment.get("is_overnight_stop")),
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
        "traffic_data": route.get("traffic_data", {}),
        "route_attraction_pool_size": route.get("route_attraction_pool_size"),
        "route_attraction_pool_districts": route.get("route_attraction_pool_districts", []),
    }


def _build_location_heatmap_points(crowd_signals: dict[str, Any]) -> list[dict[str, Any]]:
    zone_pressure = crowd_signals.get("zone_pressure") or {}
    district_points = [
        {
            "type": "district",
            "label": item.get("district"),
            "score": item.get("pressure_score"),
            "level": item.get("pressure_level"),
            "days": item.get("days", []),
            "corridors": item.get("corridors", []),
            "reasons": item.get("reasons", []),
        }
        for item in zone_pressure.get("districts", [])
        if item.get("district")
    ]
    corridor_points = [
        {
            "type": "corridor",
            "label": item.get("corridor"),
            "score": item.get("pressure_score"),
            "level": item.get("pressure_level"),
            "days": item.get("days", []),
            "districts": item.get("districts", []),
            "reasons": item.get("reasons", []),
        }
        for item in zone_pressure.get("corridors", [])
        if item.get("corridor")
    ]
    return district_points + corridor_points


def _build_time_heatmap_cells(crowd_signals: dict[str, Any]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for day_window in crowd_signals.get("forecast_windows", []) or []:
        for window in day_window.get("windows", []) or []:
            cells.append(
                {
                    "day": day_window.get("day"),
                    "date": day_window.get("date"),
                    "corridor": day_window.get("corridor"),
                    "window": window.get("label"),
                    "score": window.get("score"),
                    "level": window.get("level"),
                }
            )
    return cells


def _condition_updates_payload(document: dict[str, Any]) -> dict[str, Any]:
    items = [
        dict(item)
        for item in document.get("condition_notifications") or []
        if isinstance(item, dict)
    ]
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    unread_count = sum(1 for item in items if not item.get("read"))
    return {
        "items": items[:50],
        "unread_count": unread_count,
        "total_count": len(items),
        "latest_created_at": items[0].get("created_at") if items else None,
    }


@dataclass
class SessionLoaderService:
    session_repository: SessionRepository | None

    def get_session_document(self, session_id: str) -> dict[str, Any] | None:
        if self.session_repository is None:
            return None
        return self.session_repository.get_session(session_id)

    def get_full_session(self, session_id: str) -> dict[str, Any] | None:
        document = self.get_session_document(session_id)
        if document is None:
            return None

        # Mongo's private ObjectId is not JSON serializable and should not leak
        # through the public API response.
        payload = dict(document)
        payload.pop("_id", None)
        return payload

    def get_dashboard_payload(self, session_id: str) -> dict[str, Any] | None:
        document = self.get_session_document(session_id)
        if document is None:
            return None

        plan = document.get("plan") or {}
        crowd_signals = plan.get("crowd_signals") or {}
        recommended_route = plan.get("recommended_route") or {}
        route_summary = _route_summary(recommended_route) if recommended_route else {}

        dashboard_cache = dict(document.get("dashboard_cache") or {})
        dashboard_cache["location_heatmap_points"] = _build_location_heatmap_points(crowd_signals)
        dashboard_cache["time_heatmap_cells"] = _build_time_heatmap_cells(crowd_signals)

        return {
            "session_id": document.get("session_id"),
            "status": document.get("status"),
            "created_at": document.get("created_at"),
            "updated_at": document.get("updated_at"),
            "trip_requirements": document.get("trip_requirements", {}),
            "plan_overview": {
                "trip_days": plan.get("trip_days"),
                "trip_dates": plan.get("trip_dates", []),
                "duration_text": plan.get("duration_text"),
                "warnings": plan.get("warnings", []),
                "session_storage": plan.get("session_storage", {}),
            },
            "route": {
                "origin_resolved": plan.get("origin_resolved"),
                "destination_resolved": plan.get("destination_resolved"),
                "route_data": plan.get("route_data", {}),
                "recommended_route": route_summary,
                "travel_windows": plan.get("travel_windows", {}),
            },
            "budget": plan.get("budget_summary", {}),
            "package_explanation": plan.get("package_explanation", {}),
            "daily_briefings": plan.get("daily_briefings", []),
            "intelligence_refresh": plan.get("intelligence_refresh", {}),
            "condition_updates": _condition_updates_payload(document),
            "emotion": document.get("emotion_summary", {}),
            "transport_cost": plan.get("transport_cost", {}),
            "flight": plan.get("flight_plan", {}),
            "crowd": {
                "risk_level": crowd_signals.get("risk_level"),
                "signal_score": crowd_signals.get("signal_score"),
                "helper_summary": crowd_signals.get("helper_summary"),
                "recommendations": crowd_signals.get("recommendations", []),
                "redistribution_suggestions": crowd_signals.get("redistribution_suggestions", []),
                "zone_pressure": crowd_signals.get("zone_pressure", {}),
                "forecast_windows": crowd_signals.get("forecast_windows", []),
                "attraction_pressure": crowd_signals.get("attraction_pressure", []),
                "components": crowd_signals.get("components", {}),
            },
            "itinerary": {
                "guidance": plan.get("itinerary_guidance", {}),
                "markdown": plan.get("itinerary_markdown", ""),
                "source": plan.get("itinerary_source", "fallback"),
            },
            "dashboard_cache": dashboard_cache,
        }

    def get_chatbot_context(self, session_id: str) -> dict[str, Any] | None:
        document = self.get_session_document(session_id)
        if document is None:
            return None

        plan = document.get("plan") or {}
        crowd_signals = plan.get("crowd_signals") or {}
        recommended_route = plan.get("recommended_route") or {}
        segments = recommended_route.get("segments") or []

        return {
            "session_id": document.get("session_id"),
            "status": document.get("status"),
            "trip_summary": {
                "origin": (plan.get("origin_resolved") or {}).get("name"),
                "destination": (plan.get("destination_resolved") or {}).get("name"),
                "trip_days": plan.get("trip_days"),
                "trip_dates": plan.get("trip_dates", []),
                "duration_text": plan.get("duration_text"),
                "budget_summary": plan.get("budget_summary", {}),
                "package_explanation": plan.get("package_explanation", {}),
                "daily_briefings": plan.get("daily_briefings", []),
                "intelligence_refresh": plan.get("intelligence_refresh", {}),
                "condition_updates": _condition_updates_payload(document),
                "flight_summary": (plan.get("flight_plan") or {}).get("cheapest_result"),
                "crowd_summary": {
                    "risk_level": crowd_signals.get("risk_level"),
                    "signal_score": crowd_signals.get("signal_score"),
                    "helper_summary": crowd_signals.get("helper_summary"),
                    "recommendations": crowd_signals.get("recommendations", []),
                },
                "emotion_summary": document.get("emotion_summary", {}),
            },
            "recommended_route": {
                "route_id": recommended_route.get("route_id"),
                "distance_meters": recommended_route.get("distance_meters"),
                "duration": recommended_route.get("duration"),
                "segments": [_segment_summary(segment) for segment in segments],
            },
            "travel_windows": plan.get("travel_windows", {}),
            "itinerary_markdown": plan.get("itinerary_markdown", ""),
            "itinerary_guidance": plan.get("itinerary_guidance", {}),
            "warnings": plan.get("warnings", []),
            "chat_history": ((document.get("chat_session") or {}).get("history") or []),
        }
