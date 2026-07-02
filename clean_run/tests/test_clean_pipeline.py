from __future__ import annotations

import unittest
from unittest.mock import patch

from clean_run.pipeline.service import CleanRunPipelineService
from clean_run.routes.generate import RouteGenerationResult, RouteProfile
from clean_run.storage.session_repository import SessionRepository
from clean_run.trip.resolve import ResolvedPlace, ResolvedTripContext


class FakeIntakeService:
    def process_turn(self, message: str):
        from clean_run.intake.schemas import ChatResponse, ChatSessionState, ChatTurnResult, TripRequirements

        req = TripRequirements(origin="Colombo", destination="Kandy", duration="1 day")
        return ChatResponse(
            session=ChatSessionState(trip_requirements=req, history=[]),
            turn=ChatTurnResult(
                assistant_reply="ok",
                extracted_trip_requirements=req,
                missing_fields=[],
                is_complete=True,
            ),
        )


class FakeResolveService:
    def resolve(self, **kwargs):
        return ResolvedTripContext(
            origin_text="Colombo",
            destination_text="Kandy",
            duration_text="1 day",
            start_date="2026-06-12",
            trip_days=1,
            trip_dates=["2026-06-12"],
            origin_resolved=ResolvedPlace(
                place_id="colombo-id",
                name="Colombo",
                formatted_address="Colombo, Sri Lanka",
                lat=6.9271,
                lng=79.8612,
                types=["locality"],
            ),
            destination_resolved=ResolvedPlace(
                place_id="kandy-id",
                name="Kandy",
                formatted_address="Kandy, Sri Lanka",
                lat=7.2906,
                lng=80.6337,
                types=["locality"],
            ),
        )


def _base_route_result() -> RouteGenerationResult:
    route = RouteProfile.model_validate(
        {
            "route_id": "route_1",
            "route_labels": ["DEFAULT_ROUTE"],
            "distance_meters": 120000,
            "duration": "10314s",
            "polyline": "abc",
            "legs": [],
            "raw_route": {},
            "geometry_point_count": 2,
            "geometry_distance_m": 120000,
            "sampled_points": [{"lat": 0.0, "lng": 0.0}],
            "segments": [
                {
                    "day": 1,
                    "day_label": "Day 1",
                    "start_distance_m": 0,
                    "end_distance_m": 120000,
                    "segment_distance_m": 120000,
                    "segment_duration_seconds": 10314,
                    "segment_path_points": [{"lat": 0.0, "lng": 0.0}],
                    "start_point": {"lat": 0.0, "lng": 0.0},
                    "mid_point": {"lat": 0.1, "lng": 0.1},
                    "end_point": {"lat": 0.2, "lng": 0.2},
                    "is_overnight_stop": False,
                }
            ],
        }
    )
    return RouteGenerationResult(
        saved_at_utc="2026-06-12T00:00:00Z",
        origin={"lat": 6.9271, "lng": 79.8612},
        destination={"lat": 7.2906, "lng": 80.6337},
        route_count=1,
        routes=[route],
        recommended_route=route,
    )


class IdentityRouteService:
    def generate(self, resolved_trip):
        return _base_route_result()


class IdentityPlacesService:
    def __init__(self) -> None:
        self.last_nightly_budget_lkr = None

    def enrich(self, route_result, **kwargs):
        self.last_nightly_budget_lkr = kwargs.get("nightly_lodging_budget_lkr")
        payload = route_result.model_dump()
        payload["routes"][0]["segments"][0]["top_attractions"] = [{"display_name": "Temple"}]
        payload["recommended_route"] = payload["routes"][0]
        return RouteGenerationResult.model_validate(payload)


class IdentityRoadService:
    def enrich(self, route_result):
        payload = route_result.model_dump()
        payload["routes"][0]["road_alerts"] = {"risk_level": "low", "critical_count": 0}
        payload["recommended_route"] = payload["routes"][0]
        return RouteGenerationResult.model_validate(payload)


class IdentityWeatherService:
    def enrich(self, route_result, **kwargs):
        payload = route_result.model_dump()
        payload["routes"][0]["segments"][0]["weather"] = {
            "forecast": {"status": "ok", "dates": ["2026-06-12"], "precipitation_probability_max": [20], "precipitation_sum": [1], "wind_speed_max": [8]},
            "risk": {"score": 10, "risk_level": "low"},
        }
        payload["routes"][0]["weather_summary"] = {"risk_level": "low", "average_weather_risk_score": 10, "max_weather_risk_score": 10}
        payload["recommended_route"] = payload["routes"][0]
        return RouteGenerationResult.model_validate(payload)


class IdentityCrowdService:
    def enrich(self, route_result, **kwargs):
        payload = route_result.model_dump()
        payload["routes"][0]["crowd_signals"] = {"risk_level": "low", "signal_score": 8, "recommendations": [], "redistribution_suggestions": []}
        payload["recommended_route"] = payload["routes"][0]
        return RouteGenerationResult.model_validate(payload)


class HighCrowdService:
    def enrich(self, route_result, **kwargs):
        payload = route_result.model_dump()
        payload["routes"][0]["crowd_signals"] = {
            "risk_level": "high",
            "signal_score": 72,
            "recommendations": ["Shift visits earlier."],
            "redistribution_suggestions": [],
        }
        payload["recommended_route"] = payload["routes"][0]
        return RouteGenerationResult.model_validate(payload)


class IdentityTrafficService:
    def enrich(self, route_result, **kwargs):
        payload = route_result.model_dump()
        payload["routes"][0]["traffic_data"] = {"status": "ok", "risk_level": "low", "delay_minutes": 0}
        payload["recommended_route"] = payload["routes"][0]
        return RouteGenerationResult.model_validate(payload)


class FakeTravelWindowsService:
    def build(self, **kwargs):
        return {"summary": "ok", "days": [{"date": "2026-06-12"}], "chart_rows": [{"label": "Early Morning"}]}


class FakeItineraryService:
    def build(self, **kwargs):
        return {
            "itinerary_guidance": {"summary": "ok"},
            "itinerary_markdown": "# Itinerary",
            "itinerary_source": "fallback",
        }


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    def create_index(self, key: str, **kwargs):
        return key

    def find_one(self, query: dict):
        return self.documents.get(query.get("session_id"))

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        session_id = query.get("session_id")
        existing = self.documents.get(session_id)
        if existing is None and not upsert:
            return type("Result", (), {"matched_count": 0})()

        if "$set" not in update:
            return type("Result", (), {"matched_count": 0})()

        if existing is None:
            self.documents[session_id] = update["$set"]
            return type("Result", (), {"matched_count": 1})()

        for key, value in update["$set"].items():
            parts = key.split(".")
            target = existing
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        self.documents[session_id] = existing
        return type("Result", (), {"matched_count": 1})()


class CleanPipelineTests(unittest.TestCase):
    def test_pipeline_disables_session_repository_when_mongo_init_fails(self) -> None:
        with patch("clean_run.pipeline.service.build_session_repository_from_env", side_effect=RuntimeError("boom")):
            service = CleanRunPipelineService()
        self.assertIsNone(service.session_repository)

    def test_pipeline_can_stop_after_route_generation(self) -> None:
        service = CleanRunPipelineService(
            intake_service=FakeIntakeService(),
            resolve_service=FakeResolveService(),
            route_service=IdentityRouteService(),
        )
        payload = service.run(
            origin="Colombo",
            destination="Kandy",
            duration="1 day",
            start_date="2026-06-12",
            stop_after="route_generation",
        )
        self.assertIn("route_result", payload)
        self.assertEqual(payload["route_result"]["route_count"], 1)

    def test_pipeline_builds_final_plan(self) -> None:
        places_service = IdentityPlacesService()
        service = CleanRunPipelineService(
            intake_service=FakeIntakeService(),
            resolve_service=FakeResolveService(),
            route_service=IdentityRouteService(),
            session_repository=None,
            places_service=places_service,
            road_service=IdentityRoadService(),
            weather_service=IdentityWeatherService(),
            crowd_service=IdentityCrowdService(),
            traffic_service=IdentityTrafficService(),
            travel_windows_service=FakeTravelWindowsService(),
            itinerary_service=FakeItineraryService(),
        )
        payload = service.run(
            origin="Colombo",
            destination="Kandy",
            duration="1 day",
            start_date="2026-06-12",
        )
        self.assertEqual(payload["route_count"], 1)
        self.assertEqual(payload["traffic_data"]["status"], "ok")
        self.assertEqual(payload["road_alerts"]["risk_level"], "low")
        self.assertEqual(payload["itinerary_source"], "fallback")
        self.assertEqual(payload["route_data"]["duration_str"], "2h 51m")
        self.assertEqual(payload["route_data"]["duration_raw"], "10314s")
        self.assertEqual(payload["transport_cost"]["mode"], "bus")
        self.assertGreater(payload["transport_cost"]["estimated_total_lkr"], 0)
        self.assertEqual(payload["route_data"]["transport_cost"], payload["transport_cost"])
        self.assertEqual(payload["budget_summary"]["overnight_stays"], 0)
        self.assertEqual(payload["package_explanation"]["mode"], "read_only")
        self.assertFalse(payload["package_explanation"]["package_mutation"]["allowed"])
        self.assertIn("budget_fit", payload["package_explanation"]["components"])
        self.assertIsNone(places_service.last_nightly_budget_lkr)

    def test_pipeline_divides_total_budget_across_overnight_stays(self) -> None:
        places_service = IdentityPlacesService()

        class ThreeDayResolveService(FakeResolveService):
            def resolve(self, **kwargs):
                return ResolvedTripContext(
                    origin_text="Colombo",
                    destination_text="Kandy",
                    duration_text="3 days",
                    start_date="2026-06-12",
                    trip_days=3,
                    trip_dates=["2026-06-12", "2026-06-13", "2026-06-14"],
                    origin_resolved=ResolvedPlace(
                        place_id="colombo-id",
                        name="Colombo",
                        formatted_address="Colombo, Sri Lanka",
                        lat=6.9271,
                        lng=79.8612,
                        types=["locality"],
                    ),
                    destination_resolved=ResolvedPlace(
                        place_id="kandy-id",
                        name="Kandy",
                        formatted_address="Kandy, Sri Lanka",
                        lat=7.2906,
                        lng=80.6337,
                        types=["locality"],
                    ),
                )

        service = CleanRunPipelineService(
            intake_service=FakeIntakeService(),
            resolve_service=ThreeDayResolveService(),
            route_service=IdentityRouteService(),
            session_repository=None,
            places_service=places_service,
            road_service=IdentityRoadService(),
            weather_service=IdentityWeatherService(),
            crowd_service=IdentityCrowdService(),
            traffic_service=IdentityTrafficService(),
            travel_windows_service=FakeTravelWindowsService(),
            itinerary_service=FakeItineraryService(),
        )
        payload = service.run(
            origin="Colombo",
            destination="Kandy",
            duration="3 days",
            start_date="2026-06-12",
            accommodation_budget_lkr=300000,
        )
        self.assertEqual(payload["budget_summary"]["accommodation_budget_lkr"], 300000)
        self.assertEqual(payload["budget_summary"]["overnight_stays"], 2)
        self.assertEqual(payload["budget_summary"]["nightly_lodging_budget_lkr"], 150000.0)
        self.assertEqual(places_service.last_nightly_budget_lkr, 150000.0)

    def test_pipeline_splits_total_budget_from_selected_flight_handoff(self) -> None:
        places_service = IdentityPlacesService()

        class ThreeDayResolveService(FakeResolveService):
            def resolve(self, **kwargs):
                return ResolvedTripContext(
                    origin_text="Colombo",
                    destination_text="Kandy",
                    duration_text="3 days",
                    start_date="2026-06-12",
                    trip_days=3,
                    trip_dates=["2026-06-12", "2026-06-13", "2026-06-14"],
                    origin_resolved=ResolvedPlace(
                        place_id="colombo-id",
                        name="Colombo",
                        formatted_address="Colombo, Sri Lanka",
                        lat=6.9271,
                        lng=79.8612,
                        types=["locality"],
                    ),
                    destination_resolved=ResolvedPlace(
                        place_id="kandy-id",
                        name="Kandy",
                        formatted_address="Kandy, Sri Lanka",
                        lat=7.2906,
                        lng=80.6337,
                        types=["locality"],
                    ),
                )

        service = CleanRunPipelineService(
            intake_service=FakeIntakeService(),
            resolve_service=ThreeDayResolveService(),
            route_service=IdentityRouteService(),
            session_repository=None,
            places_service=places_service,
            road_service=IdentityRoadService(),
            weather_service=IdentityWeatherService(),
            crowd_service=IdentityCrowdService(),
            traffic_service=IdentityTrafficService(),
            travel_windows_service=FakeTravelWindowsService(),
            itinerary_service=FakeItineraryService(),
        )
        payload = service.run(
            origin="Colombo",
            destination="Kandy",
            duration="3 days",
            start_date="2026-06-12",
            total_budget_lkr=300000,
            flight_usd_to_lkr_rate=300.0,
            selected_flight={
                "provider": "travelpayouts",
                "origin": "DXB",
                "destination": "CMB",
                "price": 500,
                "currency": "USD",
                "airline": "UL",
                "booking_link": "https://example.com/flight",
            },
        )
        self.assertEqual(payload["budget_summary"]["total_budget_lkr"], 300000)
        self.assertEqual(payload["budget_summary"]["selected_flight_budget_lkr_estimated"], 150000.0)
        self.assertEqual(payload["budget_summary"]["accommodation_budget_lkr"], 150000.0)
        self.assertEqual(payload["budget_summary"]["nightly_lodging_budget_lkr"], 75000.0)
        self.assertEqual(places_service.last_nightly_budget_lkr, 75000.0)
        self.assertEqual(payload["flight_plan"]["selected_result"]["booking_link"], "https://example.com/flight")

    def test_pipeline_uses_selected_flight_handoff(self) -> None:
        places_service = IdentityPlacesService()

        class ThreeDayResolveService(FakeResolveService):
            def resolve(self, **kwargs):
                return ResolvedTripContext(
                    origin_text="Colombo",
                    destination_text="Kandy",
                    duration_text="3 days",
                    start_date="2026-06-12",
                    trip_days=3,
                    trip_dates=["2026-06-12", "2026-06-13", "2026-06-14"],
                    origin_resolved=ResolvedPlace(
                        place_id="colombo-id",
                        name="Colombo",
                        formatted_address="Colombo, Sri Lanka",
                        lat=6.9271,
                        lng=79.8612,
                        types=["locality"],
                    ),
                    destination_resolved=ResolvedPlace(
                        place_id="kandy-id",
                        name="Kandy",
                        formatted_address="Kandy, Sri Lanka",
                        lat=7.2906,
                        lng=80.6337,
                        types=["locality"],
                    ),
                )

        selected_flight = {
            "provider": "travelpayouts",
            "origin": "DXB",
            "destination": "CMB",
            "price": 400,
            "currency": "USD",
            "airline": "UL",
            "booking_link": "https://example.com/selected-flight",
        }

        service = CleanRunPipelineService(
            intake_service=FakeIntakeService(),
            resolve_service=ThreeDayResolveService(),
            route_service=IdentityRouteService(),
            session_repository=None,
            places_service=places_service,
            road_service=IdentityRoadService(),
            weather_service=IdentityWeatherService(),
            crowd_service=IdentityCrowdService(),
            traffic_service=IdentityTrafficService(),
            travel_windows_service=FakeTravelWindowsService(),
            itinerary_service=FakeItineraryService(),
        )
        payload = service.run(
            origin="Colombo",
            destination="Kandy",
            duration="3 days",
            start_date="2026-06-12",
            total_budget_lkr=300000,
            flight_usd_to_lkr_rate=300.0,
            selected_flight=selected_flight,
        )

        self.assertEqual(payload["flight_plan"]["selected_result"]["booking_link"], "https://example.com/selected-flight")
        self.assertEqual(payload["flight_plan"]["selection_source"], "frontend_selected")
        self.assertEqual(payload["budget_summary"]["selected_flight_budget_lkr_estimated"], 120000.0)
        self.assertEqual(payload["budget_summary"]["accommodation_budget_lkr"], 180000.0)
        self.assertEqual(payload["budget_summary"]["nightly_lodging_budget_lkr"], 90000.0)
        self.assertEqual(places_service.last_nightly_budget_lkr, 90000.0)

    def test_pipeline_never_searches_flights_during_tour_planning(self) -> None:
        service = CleanRunPipelineService(
            intake_service=FakeIntakeService(),
            resolve_service=FakeResolveService(),
            route_service=IdentityRouteService(),
            session_repository=None,
            places_service=IdentityPlacesService(),
            road_service=IdentityRoadService(),
            weather_service=IdentityWeatherService(),
            crowd_service=IdentityCrowdService(),
            traffic_service=IdentityTrafficService(),
            travel_windows_service=FakeTravelWindowsService(),
            itinerary_service=FakeItineraryService(),
        )

        payload = service.run(
            origin="Colombo",
            destination="Kandy",
            duration="1 day",
            start_date="2026-06-12",
            total_budget_lkr=300000,
        )

        self.assertEqual(payload["budget_summary"]["accommodation_budget_lkr"], 300000.0)
        self.assertEqual(payload["flight_plan"], {})

    def test_pipeline_auto_saves_session_when_repository_is_present(self) -> None:
        repository = SessionRepository(FakeCollection())
        service = CleanRunPipelineService(
            intake_service=FakeIntakeService(),
            resolve_service=FakeResolveService(),
            route_service=IdentityRouteService(),
            session_repository=repository,
            places_service=IdentityPlacesService(),
            road_service=IdentityRoadService(),
            weather_service=IdentityWeatherService(),
            crowd_service=IdentityCrowdService(),
            traffic_service=IdentityTrafficService(),
            travel_windows_service=FakeTravelWindowsService(),
            itinerary_service=FakeItineraryService(),
        )
        payload = service.run(
            origin="Colombo",
            destination="Kandy",
            duration="1 day",
            start_date="2026-06-12",
            session_id="session-clean-run-1",
        )
        self.assertEqual(payload["session_id"], "session-clean-run-1")
        self.assertEqual(payload["session_storage"]["enabled"], True)
        self.assertEqual(payload["session_storage"]["saved"], True)
        saved = repository.get_session("session-clean-run-1")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["plan"]["route_data"]["route_id"], "route_1")
        self.assertEqual(saved["plan"]["transport_cost"]["mode"], "bus")

    def test_refresh_intelligence_does_not_change_package_decisions(self) -> None:
        repository = SessionRepository(FakeCollection())
        service = CleanRunPipelineService(
            intake_service=FakeIntakeService(),
            resolve_service=FakeResolveService(),
            route_service=IdentityRouteService(),
            session_repository=repository,
            places_service=IdentityPlacesService(),
            road_service=IdentityRoadService(),
            weather_service=IdentityWeatherService(),
            crowd_service=IdentityCrowdService(),
            traffic_service=IdentityTrafficService(),
            travel_windows_service=FakeTravelWindowsService(),
            itinerary_service=FakeItineraryService(),
        )
        original = service.run(
            origin="Colombo",
            destination="Kandy",
            duration="1 day",
            start_date="2026-06-12",
            total_budget_lkr=300000,
            flight_usd_to_lkr_rate=300,
            session_id="refresh-session-1",
        )

        service.crowd_service = HighCrowdService()
        refreshed = service.refresh_intelligence(
            session_id="refresh-session-1",
            departure_time="09:00",
            use_gemini_itinerary=False,
        )

        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertFalse(refreshed["changed_package"])
        updated_plan = refreshed["plan"]
        self.assertEqual(updated_plan["flight_plan"], original["flight_plan"])
        self.assertEqual(updated_plan["budget_summary"], original["budget_summary"])
        self.assertEqual(updated_plan["transport_cost"], original["transport_cost"])
        self.assertEqual(updated_plan["route_data"]["route_id"], original["route_data"]["route_id"])
        self.assertEqual(updated_plan["route_data"]["distance_meters"], original["route_data"]["distance_meters"])
        self.assertEqual(updated_plan["crowd_signals"]["risk_level"], "high")
        self.assertEqual(updated_plan["intelligence_refresh"]["mode"], "signals_only")
        self.assertFalse(updated_plan["intelligence_refresh"]["package_mutation"]["allowed"])

        saved = repository.get_session("refresh-session-1")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["plan"]["crowd_signals"]["risk_level"], "high")
        self.assertEqual(saved["plan"]["flight_plan"], original["flight_plan"])


if __name__ == "__main__":
    unittest.main()
