from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from datetime import datetime, timezone
import os
from typing import Any

from clean_run.enrich import (
    CrowdEnrichmentService,
    PlaceEnrichmentService,
    RoadEnrichmentService,
    TrafficEnrichmentService,
    WeatherEnrichmentService,
)
from clean_run.intake.service import TravelIntakeService
from clean_run.postprocess import (
    ItineraryService,
    TravelWindowsService,
    assemble_plan,
    build_daily_briefings,
    build_package_explanation,
    estimate_transport_cost_for_route,
)
from clean_run.routes.generate import RouteGenerationService
from clean_run.routes.generate import RouteGenerationResult
from clean_run.storage import SessionRepository, build_session_repository_from_env
from clean_run.trip.resolve import ResolvedPlace, ResolvedTripContext
from clean_run.trip.resolve import ResolveTripService


def _session_repository_from_env() -> SessionRepository | None:
    try:
        return build_session_repository_from_env()
    except Exception:
        return None


@dataclass
class CleanRunPipelineService:
    intake_service: TravelIntakeService = field(default_factory=lambda: TravelIntakeService(use_llm=False))
    session_repository: SessionRepository | None = field(default_factory=_session_repository_from_env)
    resolve_service: ResolveTripService = field(default_factory=ResolveTripService)
    route_service: RouteGenerationService = field(default_factory=RouteGenerationService)
    places_service: PlaceEnrichmentService = field(default_factory=PlaceEnrichmentService)
    road_service: RoadEnrichmentService = field(default_factory=RoadEnrichmentService)
    weather_service: WeatherEnrichmentService = field(default_factory=WeatherEnrichmentService)
    crowd_service: CrowdEnrichmentService = field(default_factory=CrowdEnrichmentService)
    traffic_service: TrafficEnrichmentService = field(default_factory=TrafficEnrichmentService)
    travel_windows_service: TravelWindowsService = field(default_factory=TravelWindowsService)
    itinerary_service: ItineraryService = field(default_factory=ItineraryService)

    def _resolved_trip_from_plan(self, plan: dict[str, Any]) -> ResolvedTripContext:
        origin_payload = plan.get("origin_resolved") or {}
        destination_payload = plan.get("destination_resolved") or {}
        trip_dates = plan.get("trip_dates") or []
        if not trip_dates:
            raise ValueError("Saved session does not contain trip_dates; cannot refresh intelligence.")

        return ResolvedTripContext(
            origin_text=origin_payload.get("name") or "Origin",
            destination_text=destination_payload.get("name") or "Destination",
            duration_text=plan.get("duration_text") or f"{plan.get('trip_days') or len(trip_dates)} days",
            start_date=trip_dates[0],
            trip_days=int(plan.get("trip_days") or len(trip_dates)),
            trip_dates=trip_dates,
            origin_resolved=ResolvedPlace.model_validate(origin_payload),
            destination_resolved=ResolvedPlace.model_validate(destination_payload),
        )

    def _route_result_from_plan(self, plan: dict[str, Any]) -> RouteGenerationResult:
        routes = deepcopy(plan.get("routes") or [])
        recommended_route = deepcopy(plan.get("recommended_route") or {})
        if recommended_route:
            recommended_route_id = recommended_route.get("route_id")
            routes = [
                recommended_route if route.get("route_id") == recommended_route_id else route
                for route in routes
            ]
            if not any(route.get("route_id") == recommended_route_id for route in routes):
                routes.insert(0, recommended_route)
        if not routes:
            raise ValueError("Saved session does not contain route data; cannot refresh intelligence.")

        payload = {
            "saved_at_utc": plan.get("saved_at_utc") or datetime.now(timezone.utc).isoformat(),
            "origin": {
                "lat": (plan.get("origin_resolved") or {}).get("lat"),
                "lng": (plan.get("origin_resolved") or {}).get("lng"),
            },
            "destination": {
                "lat": (plan.get("destination_resolved") or {}).get("lat"),
                "lng": (plan.get("destination_resolved") or {}).get("lng"),
            },
            "route_count": len(routes),
            "routes": routes,
            "recommended_route": recommended_route or routes[0],
        }
        return RouteGenerationResult.model_validate(payload)

    def _weather_data_from_route(self, route: dict[str, Any]) -> dict[str, Any]:
        return {
            "locations": [
                {
                    "label": f"day_{segment.get('day')}_segment",
                    "name": f"Day {segment.get('day')} route segment",
                    "forecast": (segment.get("weather") or {}).get("forecast") or {"status": "unavailable"},
                    "risk": (segment.get("weather") or {}).get("risk"),
                }
                for segment in route.get("segments", [])
            ],
            "summary": route.get("weather_summary", {}),
        }

    def refresh_intelligence(
        self,
        *,
        session_id: str,
        departure_time: str = "08:00",
        use_gemini_itinerary: bool = False,
    ) -> dict[str, Any] | None:
        if self.session_repository is None:
            raise RuntimeError("Session repository is not configured.")

        document = self.session_repository.get_session(session_id)
        if document is None:
            return None

        old_plan = document.get("plan") or {}
        resolved = self._resolved_trip_from_plan(old_plan)
        route_result = self._route_result_from_plan(old_plan)

        route_result = self.weather_service.enrich(route_result, resolved_trip=resolved)
        route_result = self.crowd_service.enrich(route_result, resolved_trip=resolved)
        route_result = self.traffic_service.enrich(
            route_result,
            resolved_trip=resolved,
            departure_time=departure_time,
        )
        travel_windows = self.travel_windows_service.build(
            route_result=route_result,
            resolved_trip=resolved,
            departure_time=departure_time,
        )
        itinerary_output = self.itinerary_service.build(
            route_result=route_result,
            resolved_trip=resolved,
            travel_windows=travel_windows,
            use_gemini=use_gemini_itinerary,
        )

        recommended_route = route_result.recommended_route.model_dump() if route_result.recommended_route else {}
        refreshed_plan = deepcopy(old_plan)
        refreshed_plan.update(
            {
                "routes": [route.model_dump() for route in route_result.routes],
                "recommended_route": recommended_route,
                "weather_data": self._weather_data_from_route(recommended_route),
                "traffic_data": recommended_route.get("traffic_data", {}),
                "crowd_signals": recommended_route.get("crowd_signals", {}),
                "travel_windows": travel_windows,
                "itinerary_guidance": itinerary_output.get("itinerary_guidance", {}),
                "itinerary_markdown": itinerary_output.get("itinerary_markdown", ""),
                "itinerary_source": itinerary_output.get("itinerary_source", "fallback"),
                "intelligence_refresh": {
                    "refreshed_at_utc": datetime.now(timezone.utc).isoformat(),
                    "mode": "signals_only",
                    "package_mutation": {
                        "allowed": False,
                        "changed_fields": [
                            "weather_data",
                            "traffic_data",
                            "crowd_signals",
                            "travel_windows",
                            "itinerary_guidance",
                            "package_explanation",
                            "daily_briefings",
                        ],
                    },
                },
            }
        )
        route_data = dict(refreshed_plan.get("route_data") or {})
        route_data["segments"] = recommended_route.get("segments", [])
        route_data["traffic_data"] = recommended_route.get("traffic_data", {})
        route_data["polyline"] = recommended_route.get("polyline")
        route_data["geometry_point_count"] = recommended_route.get("geometry_point_count", 0)
        route_data["geometry_distance_m"] = recommended_route.get("geometry_distance_m", 0.0)
        route_data["sampled_points"] = recommended_route.get("sampled_points", [])
        refreshed_plan["route_data"] = route_data
        refreshed_plan["package_explanation"] = build_package_explanation(refreshed_plan)
        refreshed_plan["daily_briefings"] = build_daily_briefings(refreshed_plan)

        plan_updates = {
            key: refreshed_plan[key]
            for key in [
                "routes",
                "recommended_route",
                "route_data",
                "weather_data",
                "traffic_data",
                "crowd_signals",
                "travel_windows",
                "itinerary_guidance",
                "itinerary_markdown",
                "itinerary_source",
                "package_explanation",
                "daily_briefings",
                "intelligence_refresh",
            ]
        }
        updated = self.session_repository.update_session_intelligence(
            session_id=session_id,
            plan_updates=plan_updates,
            status=document.get("status") or "planned",
        )
        if not updated:
            return None

        return {
            "session_id": session_id,
            "status": "refreshed",
            "changed_package": False,
            "updated_fields": list(plan_updates.keys()),
            "plan": refreshed_plan,
        }

    def run(
        self,
        *,
        origin: str,
        destination: str,
        duration: str,
        start_date: str,
        departure_time: str = "08:00",
        place_strategy: str = "nearby",
        accommodation_budget_lkr: float | None = None,
        total_budget_lkr: float | None = None,
        flight_usd_to_lkr_rate: float | None = None,
        selected_flight: dict[str, Any] | None = None,
        flight_plan: dict[str, Any] | None = None,
        session_id: str | None = None,
        use_gemini_intake: bool = False,
        use_gemini_itinerary: bool = False,
        stop_after: str | None = None,
    ) -> dict[str, Any]:
        warnings: list[str] = []
        intake = self.intake_service.process_turn(
            f"Plan a trip from {origin} to {destination} for {duration}.",
        )
        if stop_after == "intake":
            return {"intake": intake.model_dump(), "warnings": warnings}

        resolved = self.resolve_service.resolve(
            origin_text=intake.session.trip_requirements.origin or origin,
            destination_text=intake.session.trip_requirements.destination or destination,
            duration_text=intake.session.trip_requirements.duration or duration,
            start_date=start_date,
        )
        session_requirements = intake.session.trip_requirements
        total_trip_budget_lkr = total_budget_lkr if total_budget_lkr is not None else session_requirements.total_budget_lkr
        explicit_accommodation_budget_lkr = (
            accommodation_budget_lkr
            if accommodation_budget_lkr is not None
            else session_requirements.accommodation_budget_lkr
        )
        selected_flight = deepcopy(selected_flight) if selected_flight else None
        flight_plan = deepcopy(flight_plan) if flight_plan else None
        flight_budget_lkr_estimated: float | None = None
        flight_budget_conversion: dict[str, Any] | None = None

        if selected_flight and flight_plan is None:
            flight_plan = {
                "origin": selected_flight.get("origin"),
                "destination": selected_flight.get("destination") or "CMB",
                "results": [selected_flight],
                "results_count": 1,
                "cheapest_result": selected_flight,
                "selected_result": selected_flight,
                "selection_source": "frontend_selected",
            }
        elif selected_flight and flight_plan is not None:
            flight_plan["selected_result"] = selected_flight
            flight_plan.setdefault("selection_source", "frontend_selected")
        def _estimate_flight_cost_lkr(flight: dict[str, Any] | None) -> tuple[float | None, dict[str, Any] | None]:
            if not flight:
                return None, None
            price = flight.get("price")
            currency = str(flight.get("currency") or "").upper()
            try:
                price_value = float(price)
            except (TypeError, ValueError):
                return None, None

            if currency == "LKR":
                return price_value, {
                    "source_currency": "LKR",
                    "target_currency": "LKR",
                    "rate": 1.0,
                    "mode": "identity",
                }

            if currency == "USD":
                configured_rate = (
                    flight_usd_to_lkr_rate
                    if flight_usd_to_lkr_rate is not None
                    else float(os.getenv("FLIGHT_USD_TO_LKR_RATE") or 300.0)
                )
                mode = (
                    "provided"
                    if flight_usd_to_lkr_rate is not None
                    else ("env" if os.getenv("FLIGHT_USD_TO_LKR_RATE") else "default_estimate")
                )
                if mode == "default_estimate":
                    warnings.append(
                        f"Flight budget conversion used default estimated USD->LKR rate of {configured_rate:.2f}. Set FLIGHT_USD_TO_LKR_RATE for tighter budget math."
                    )
                return price_value * configured_rate, {
                    "source_currency": "USD",
                    "target_currency": "LKR",
                    "rate": configured_rate,
                    "mode": mode,
                }

            warnings.append(f"Could not convert flight currency '{currency}' into LKR for budget splitting.")
            return None, None

        flight_budget_lkr_estimated, flight_budget_conversion = _estimate_flight_cost_lkr(selected_flight)

        total_accommodation_budget_lkr = explicit_accommodation_budget_lkr
        if total_trip_budget_lkr is not None:
            if flight_budget_lkr_estimated is not None:
                total_accommodation_budget_lkr = max(0.0, float(total_trip_budget_lkr) - float(flight_budget_lkr_estimated))
            else:
                total_accommodation_budget_lkr = float(total_trip_budget_lkr)
        overnight_stays = max(resolved.trip_days - 1, 0)
        nightly_lodging_budget_lkr = None
        if total_accommodation_budget_lkr and overnight_stays > 0:
            nightly_lodging_budget_lkr = float(total_accommodation_budget_lkr) / overnight_stays
        if stop_after == "resolve_trip":
            return {"resolved_trip": resolved.model_dump(), "warnings": warnings}

        route_result = self.route_service.generate(resolved)
        if stop_after == "route_generation":
            return {"route_result": route_result.model_dump(), "warnings": warnings}

        route_result = self.places_service.enrich(
            route_result,
            resolved_trip=resolved,
            strategy=place_strategy,
            nightly_lodging_budget_lkr=nightly_lodging_budget_lkr,
        )
        if stop_after == "place_enrichment":
            return {"route_result": route_result.model_dump(), "warnings": warnings}

        route_result = self.road_service.enrich(route_result)
        if stop_after == "road_enrichment":
            return {"route_result": route_result.model_dump(), "warnings": warnings}

        route_result = self.weather_service.enrich(route_result, resolved_trip=resolved)
        if stop_after == "weather_enrichment":
            return {"route_result": route_result.model_dump(), "warnings": warnings}

        route_result = self.crowd_service.enrich(route_result, resolved_trip=resolved)
        if stop_after == "crowd_enrichment":
            return {"route_result": route_result.model_dump(), "warnings": warnings}

        route_result = self.traffic_service.enrich(
            route_result,
            resolved_trip=resolved,
            departure_time=departure_time,
        )
        if stop_after == "traffic_enrichment":
            return {"route_result": route_result.model_dump(), "warnings": warnings}

        travel_windows = self.travel_windows_service.build(
            route_result=route_result,
            resolved_trip=resolved,
            departure_time=departure_time,
        )
        if stop_after == "travel_windows":
            return {"travel_windows": travel_windows, "warnings": warnings}

        itinerary_output = self.itinerary_service.build(
            route_result=route_result,
            resolved_trip=resolved,
            travel_windows=travel_windows,
            use_gemini=use_gemini_itinerary,
        )
        if stop_after == "itinerary":
            return {"itinerary_output": itinerary_output, "warnings": warnings}

        recommended_route_payload = route_result.recommended_route.model_dump() if route_result.recommended_route else {}
        transport_cost = estimate_transport_cost_for_route(recommended_route_payload)

        plan_payload = assemble_plan(
            resolved_trip=resolved,
            route_result=route_result,
            travel_windows=travel_windows,
            itinerary_output=itinerary_output,
            flight_plan=flight_plan,
            transport_cost=transport_cost,
            budget_summary={
                "total_budget_lkr": total_trip_budget_lkr,
                "selected_flight_budget_lkr_estimated": flight_budget_lkr_estimated,
                "selected_flight_budget_conversion": flight_budget_conversion,
                "selected_flight_price": selected_flight.get("price") if selected_flight else None,
                "selected_flight_currency": selected_flight.get("currency") if selected_flight else None,
                "accommodation_budget_lkr": total_accommodation_budget_lkr,
                "overnight_stays": overnight_stays,
                "nightly_lodging_budget_lkr": nightly_lodging_budget_lkr,
            },
            warnings=warnings,
        )
        plan_payload["package_explanation"] = build_package_explanation(plan_payload)
        plan_payload["daily_briefings"] = build_daily_briefings(plan_payload)
        plan_payload["session_id"] = session_id
        plan_payload["session_storage"] = {
            "enabled": self.session_repository is not None,
            "saved": False,
        }

        if self.session_repository is not None:
            try:
                saved_session_id = self.session_repository.save_planned_session(
                    session_id=session_id,
                    trip_requirements=session_requirements.model_dump(),
                    chat_history=[turn.model_dump() for turn in intake.session.history],
                    plan=plan_payload,
                )
                plan_payload["session_id"] = saved_session_id
                plan_payload["session_storage"] = {
                    "enabled": True,
                    "saved": True,
                }
                self.session_repository.save_planned_session(
                    session_id=saved_session_id,
                    trip_requirements=session_requirements.model_dump(),
                    chat_history=[turn.model_dump() for turn in intake.session.history],
                    plan=plan_payload,
                )
            except Exception as exc:
                warnings.append(f"Session save failed: {exc}")
                plan_payload["session_storage"] = {
                    "enabled": True,
                    "saved": False,
                }

        return plan_payload
