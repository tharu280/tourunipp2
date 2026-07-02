from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from clean_run.routes.generate import RouteGenerationResult
from clean_run.trip.resolve import ResolvedTripContext
from clean_run.enrich.places_engine import enrich_route as enrich_places_route


PlaceRouteEnricher = Callable[..., dict[str, Any]]


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
class PlaceEnrichmentService:
    route_enricher: PlaceRouteEnricher = enrich_places_route

    def enrich(
        self,
        route_result: RouteGenerationResult,
        *,
        resolved_trip: ResolvedTripContext,
        strategy: str = "nearby",
        nightly_lodging_budget_lkr: float | None = None,
    ) -> RouteGenerationResult:
        routes = [
            self.route_enricher(
                route.model_dump(),
                trip_days=resolved_trip.trip_days,
                strategy=strategy,
                lodging_budget_lkr=nightly_lodging_budget_lkr,
            )
            for route in route_result.routes
        ]
        return _route_result_with_routes(route_result, routes)
