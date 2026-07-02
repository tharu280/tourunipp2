from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from clean_run.routes.generate import RouteGenerationResult
from clean_run.trip.resolve import ResolvedTripContext
from clean_run.integrations.traffic_client import enrich_route_with_live_traffic


TrafficRouteEnricher = Callable[..., dict[str, Any]]


def _route_result_with_routes(
    result: RouteGenerationResult,
    routes: list[dict[str, Any]],
    recommended_route_id: str | None,
) -> RouteGenerationResult:
    payload = result.model_dump()
    payload["routes"] = routes
    payload["route_count"] = len(routes)
    selected = None
    if recommended_route_id:
        for route in routes:
            if route.get("route_id") == recommended_route_id:
                selected = route
                break
    payload["recommended_route"] = selected or (routes[0] if routes else None)
    return RouteGenerationResult.model_validate(payload)


@dataclass
class TrafficEnrichmentService:
    route_enricher: TrafficRouteEnricher = enrich_route_with_live_traffic

    def enrich(
        self,
        route_result: RouteGenerationResult,
        *,
        resolved_trip: ResolvedTripContext,
        departure_time: str = "08:00",
    ) -> RouteGenerationResult:
        recommended = route_result.recommended_route
        if not recommended:
            return route_result
        traffic_route = self.route_enricher(
            route=recommended.model_dump(),
            origin_lat=resolved_trip.origin_resolved.lat,
            origin_lng=resolved_trip.origin_resolved.lng,
            destination_lat=resolved_trip.destination_resolved.lat,
            destination_lng=resolved_trip.destination_resolved.lng,
            start_date=resolved_trip.start_date,
            departure_time=departure_time,
        )
        routes = [
            traffic_route if route.route_id == recommended.route_id else route.model_dump()
            for route in route_result.routes
        ]
        return _route_result_with_routes(route_result, routes, recommended.route_id)
