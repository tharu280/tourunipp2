from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from clean_run.routes.generate import RouteGenerationResult
from clean_run.enrich.road_engine import enrich_route as enrich_road_route


RoadRouteEnricher = Callable[[dict[str, Any]], dict[str, Any]]


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
class RoadEnrichmentService:
    route_enricher: RoadRouteEnricher = enrich_road_route

    def enrich(self, route_result: RouteGenerationResult) -> RouteGenerationResult:
        routes = [self.route_enricher(route.model_dump()) for route in route_result.routes]
        return _route_result_with_routes(route_result, routes)
