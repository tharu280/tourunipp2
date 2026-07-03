from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from clean_run.integrations.google_routes_client import build_route_profiles, compute_routes
from clean_run.routes.polyline import haversine_meters
from clean_run.routes.polyline import max_corridor_deviation_m
from clean_run.routes.polyline import summarize_geometry
from clean_run.routes.segments import build_day_segments

from clean_run.trip.resolve import ResolvedTripContext


class RoutesClient(Protocol):
    def __call__(
        self,
        *,
        origin_lat: float,
        origin_lng: float,
        destination_lat: float,
        destination_lng: float,
        compute_alternative_routes: bool = True,
        routing_preference: str = "TRAFFIC_AWARE",
        route_modifiers: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class RouteSegment(BaseModel):
    model_config = ConfigDict(extra="allow")

    day: int
    day_label: str
    start_distance_m: float
    end_distance_m: float
    segment_distance_m: float
    segment_duration_seconds: int | None = None
    segment_path_points: list[dict[str, float]] = Field(default_factory=list)
    start_point: dict[str, float]
    mid_point: dict[str, float]
    end_point: dict[str, float]
    is_overnight_stop: bool


class RouteProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    route_id: str
    route_labels: list[str] = Field(default_factory=list)
    distance_meters: float | None = None
    duration: str | None = None
    polyline: str | None = None
    legs: list[dict[str, Any]] = Field(default_factory=list)
    raw_route: dict[str, Any] = Field(default_factory=dict)
    geometry_point_count: int = 0
    geometry_distance_m: float = 0.0
    sampled_points: list[dict[str, float]] = Field(default_factory=list)
    segments: list[RouteSegment] = Field(default_factory=list)


class RouteGenerationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    saved_at_utc: str
    origin: dict[str, float]
    destination: dict[str, float]
    route_count: int
    routes: list[RouteProfile] = Field(default_factory=list)
    recommended_route: RouteProfile | None = None


def _parse_duration_seconds(duration_value: str | None) -> int | None:
    if not duration_value or not duration_value.endswith("s"):
        return None
    try:
        return int(float(duration_value[:-1]))
    except ValueError:
        return None


def _enrich_profile(
    profile: dict[str, Any],
    *,
    trip_days: int,
    origin: dict[str, float],
    destination: dict[str, float],
) -> dict[str, Any]:
    polyline = profile.get("polyline")
    if not polyline:
        return {
            **profile,
            "origin_point": origin,
            "destination_point": destination,
            "geometry_point_count": 0,
            "geometry_distance_m": 0.0,
            "sampled_points": [],
            "segments": [],
        }

    geometry = summarize_geometry(polyline)
    total_duration_seconds = _parse_duration_seconds(profile.get("duration"))
    segments = build_day_segments(
        decoded_points=geometry["decoded_points"],
        cumulative_distances_m=geometry["cumulative_distances_m"],
        total_route_distance_m=float(profile.get("distance_meters") or geometry["total_geometry_distance_m"] or 0.0),
        total_route_duration_seconds=total_duration_seconds,
        trip_days=trip_days,
    )
    return {
        **profile,
        "origin_point": origin,
        "destination_point": destination,
        "geometry_point_count": geometry["point_count"],
        "geometry_distance_m": geometry["total_geometry_distance_m"],
        "sampled_points": geometry["sampled_points"],
        "segments": segments,
    }


def _route_duration_seconds(route: RouteProfile) -> int:
    return _parse_duration_seconds(route.duration) or 0


def _corridor_deviation_m(
    route: RouteProfile,
    *,
    origin: dict[str, float],
    destination: dict[str, float],
) -> float:
    """Return the maximum perpendicular deviation (metres) of this route's
    sampled points from the direct origin-destination corridor.
    Returns 0.0 when no sampled points are available.
    """
    if not route.sampled_points:
        return 0.0
    return max_corridor_deviation_m(
        route.sampled_points,
        origin=origin,
        destination=destination,
    )


def _select_recommended_route(
    routes: list[RouteProfile],
    *,
    origin: dict[str, float],
    destination: dict[str, float],
) -> RouteProfile | None:
    """Select the shortest sane Google driving route.

    Sanity filters (applied in order):
    1. Distance relative cap  – reject routes > 20% longer than the shortest
       returned option (protects when multiple routes are available).
    2. Distance absolute cap  – reject routes > 1.80× the straight-line
       origin-destination distance (protects when only one route is returned
       and it's a huge detour).
    3. Corridor geometry cap  – reject routes whose points stray further than
       max(80 km, straight_line * 55%) sideways from the O→D corridor
       (catches routes that go in the physically wrong direction, e.g.
       Colombo→Badulla via Galle).

    If every route is rejected by all three filters, fall back to the globally
    shortest route so we always return something.

    Duration is only used as a tie-breaker when distances are equal.
    """
    if not routes:
        return None

    straight_line_m = haversine_meters(origin, destination) if origin and destination else 0.0
    distances = [float(route.distance_meters or route.geometry_distance_m or 0.0) for route in routes]
    positive_distances = [d for d in distances if d > 0]
    shortest_distance = min(positive_distances) if positive_distances else 0.0

    # --- Filter 1 & 2: distance caps ---
    # Relative cap: within 20% of the shortest returned route.
    relative_cap = shortest_distance * 1.20 if shortest_distance else float("inf")
    # Absolute cap: no more than 1.80× the straight-line distance.
    absolute_cap = straight_line_m * 1.80 if straight_line_m else float("inf")
    # Use the stricter of the two caps.
    distance_cap = min(relative_cap, absolute_cap)

    # --- Filter 3: corridor geometry cap ---
    # Allow up to 55% of the straight-line distance as perpendicular deviation,
    # with a floor of 80 km so short trips are not overly restricted.
    corridor_cap_m = max(80_000.0, straight_line_m * 0.55) if straight_line_m else float("inf")

    def _is_sane(route: RouteProfile) -> bool:
        dist = float(route.distance_meters or route.geometry_distance_m or 0.0)
        if dist > distance_cap:
            return False
        if _corridor_deviation_m(route, origin=origin, destination=destination) > corridor_cap_m:
            return False
        return True

    candidates = [route for route in routes if _is_sane(route)]

    # Fallback: if all routes fail the filters, pick the shortest overall.
    if not candidates:
        candidates = routes

    return min(
        candidates,
        key=lambda route: (
            float(route.distance_meters or route.geometry_distance_m or 9_999_999),
            _route_duration_seconds(route) or 9_999_999,
        ),
    )


def _straight_line_distance_m(origin: dict[str, float], destination: dict[str, float]) -> float:
    if not origin or not destination:
        return 0.0
    try:
        return haversine_meters(origin, destination)
    except (KeyError, TypeError, ValueError):
        return 0.0


def _is_excessive_detour(
    route: RouteProfile | None,
    *,
    origin: dict[str, float],
    destination: dict[str, float],
) -> bool:
    if route is None:
        return False
    straight_line_m = _straight_line_distance_m(origin, destination)
    route_distance_m = float(route.distance_meters or route.geometry_distance_m or 0.0)
    if straight_line_m <= 0 or route_distance_m <= 0:
        return False
    return route_distance_m / straight_line_m > 2.05 and route_distance_m - straight_line_m > 85_000


@dataclass
class RouteGenerationService:
    routes_client: RoutesClient = compute_routes

    def _generate_once(
        self,
        resolved_trip: ResolvedTripContext,
        *,
        routing_preference: str = "TRAFFIC_AWARE",
        route_modifiers: dict[str, Any] | None = None,
    ) -> RouteGenerationResult:
        response_payload = self.routes_client(
            origin_lat=resolved_trip.origin_resolved.lat,
            origin_lng=resolved_trip.origin_resolved.lng,
            destination_lat=resolved_trip.destination_resolved.lat,
            destination_lng=resolved_trip.destination_resolved.lng,
            compute_alternative_routes=True,
            routing_preference=routing_preference,
            route_modifiers=route_modifiers,
        )
        route_payload = build_route_profiles(
            response_payload=response_payload,
            origin_lat=resolved_trip.origin_resolved.lat,
            origin_lng=resolved_trip.origin_resolved.lng,
            destination_lat=resolved_trip.destination_resolved.lat,
            destination_lng=resolved_trip.destination_resolved.lng,
        )
        origin = route_payload.get("origin") or {}
        destination = route_payload.get("destination") or {}
        routes = [
            RouteProfile.model_validate(
                _enrich_profile(
                    profile,
                    trip_days=resolved_trip.trip_days,
                    origin=origin,
                    destination=destination,
                )
            )
            for profile in route_payload.get("routes", [])
        ]
        recommended_route = _select_recommended_route(
            routes,
            origin=origin,
            destination=destination,
        )
        return RouteGenerationResult(
            saved_at_utc=route_payload.get("saved_at_utc") or datetime.now(timezone.utc).isoformat(),
            origin=origin,
            destination=destination,
            route_count=route_payload.get("route_count", len(routes)),
            routes=routes,
            recommended_route=recommended_route,
        )

    def generate(self, resolved_trip: ResolvedTripContext) -> RouteGenerationResult:
        result = self._generate_once(resolved_trip)
        if not _is_excessive_detour(
            result.recommended_route,
            origin=result.origin,
            destination=result.destination,
        ):
            return result

        try:
            scenic_result = self._generate_once(
                resolved_trip,
                routing_preference="TRAFFIC_UNAWARE",
                route_modifiers={"avoidHighways": True},
            )
        except Exception:
            return result

        if scenic_result.recommended_route and not _is_excessive_detour(
            scenic_result.recommended_route,
            origin=scenic_result.origin,
            destination=scenic_result.destination,
        ):
            return scenic_result
        return result
