from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from clean_run.routes.generate import RouteGenerationResult
from clean_run.trip.resolve import ResolvedTripContext
from clean_run.enrich.crowd_engine import enrich_route as enrich_crowd_route


CrowdRouteEnricher = Callable[..., dict[str, Any]]


def _route_result_with_routes(
    result: RouteGenerationResult,
    routes: list[dict[str, Any]],
) -> RouteGenerationResult:
    payload = result.model_dump()
    payload["routes"] = routes
    payload["route_count"] = len(routes)
    payload["recommended_route"] = routes[0] if routes else None
    return RouteGenerationResult.model_validate(payload)


@dataclass
class CrowdEnrichmentService:
    route_enricher: CrowdRouteEnricher = enrich_crowd_route

    def enrich(
        self,
        route_result: RouteGenerationResult,
        *,
        resolved_trip: ResolvedTripContext,
    ) -> RouteGenerationResult:
        routes = [
            self.route_enricher(
                route=route.model_dump(),
                start_date=resolved_trip.start_date,
                trip_days=resolved_trip.trip_days,
            )
            for route in route_result.routes
        ]
        return _route_result_with_routes(route_result, routes)
