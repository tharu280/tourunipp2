from __future__ import annotations

import unittest

from clean_run.storage.session_loader import SessionLoaderService
from clean_run.storage.session_repository import SessionRepository


class FakeCollection:
    def __init__(self, document: dict) -> None:
        self.document = document

    def create_index(self, key: str, **kwargs):
        return key

    def find_one(self, query: dict):
        if query.get("session_id") == self.document.get("session_id"):
            return self.document
        return None


def _sample_document() -> dict:
    return {
        "session_id": "session-123",
        "status": "planned",
        "created_at": "2026-06-21T00:00:00Z",
        "updated_at": "2026-06-21T00:10:00Z",
        "trip_requirements": {
            "origin": "Colombo",
            "destination": "Kandy",
            "duration": "3 days",
        },
        "chat_session": {
            "history": [
                {"role": "user", "message": "Plan Colombo to Kandy"},
            ]
        },
        "dashboard_cache": {},
        "emotion_summary": {
            "count": 1,
            "latest": {"emotion_label": "happy", "emotion_confidence": 0.82},
            "latest_recommendation": {"risk_level": "low"},
            "raw_images_stored": False,
        },
        "plan": {
            "trip_days": 3,
            "trip_dates": ["2026-06-25", "2026-06-26", "2026-06-27"],
            "duration_text": "3 days",
            "warnings": [],
            "session_storage": {"enabled": True, "saved": True},
            "origin_resolved": {"name": "Colombo"},
            "destination_resolved": {"name": "Kandy"},
            "route_data": {"route_id": "route-1", "distance_km": 115.0},
            "recommended_route": {
                "route_id": "route-1",
                "route_labels": ["DEFAULT_ROUTE"],
                "distance_meters": 115000,
                "duration": "10800s",
                "polyline": "encoded-road-polyline",
                "geometry_point_count": 42,
                "geometry_distance_m": 116000.0,
                "sampled_points": [
                    {"lat": 6.9271, "lng": 79.8612},
                    {"lat": 7.1282, "lng": 80.0124},
                    {"lat": 7.2906, "lng": 80.6337},
                ],
                "road_alerts": {"risk_level": "medium"},
                "weather_summary": {"risk_level": "high"},
                "crowd_signals": {"risk_level": "high"},
                "traffic_data": {"risk_level": "low"},
                "segments": [
                    {
                        "day": 1,
                        "day_label": "Day 1",
                        "segment_distance_m": 50000,
                        "segment_duration_seconds": 3600,
                        "segment_path_points": [
                            {"lat": 6.9271, "lng": 79.8612},
                            {"lat": 7.0, "lng": 80.1},
                        ],
                        "start_point": {"lat": 6.9271, "lng": 79.8612},
                        "mid_point": {"lat": 6.9, "lng": 79.9},
                        "end_point": {"lat": 7.0, "lng": 80.1},
                        "top_attractions": [{"display_name": "Gangaramaya Temple"}],
                        "top_lodging": [{"display_name": "Hotel A"}],
                        "recommended_lodging": {"display_name": "Hotel A"},
                        "weather": {"risk": {"risk_level": "medium"}},
                        "is_overnight_stop": True,
                    }
                ],
            },
            "travel_windows": {"best_windows": [{"label": "late_morning"}]},
            "budget_summary": {"total_budget_lkr": 300000, "nightly_lodging_budget_lkr": 100000},
            "transport_cost": {
                "mode": "bus",
                "estimated_total_lkr": 560,
                "total_distance_km": 115.0,
                "segments": [{"label": "Day 1", "day": 1, "distance_km": 115.0, "estimated_fare_lkr": 560}],
            },
            "flight_plan": {"cheapest_result": {"price": 303, "currency": "USD"}},
            "crowd_signals": {
                "risk_level": "high",
                "signal_score": 51,
                "helper_summary": "Trip pressure is high.",
                "recommendations": ["Start early."],
                "redistribution_suggestions": [{"title": "Shift Day 1 earlier"}],
                "zone_pressure": {
                    "districts": [{"district": "Colombo", "pressure_score": 20, "pressure_level": "medium", "days": [1], "corridors": ["South Coast"], "reasons": ["Rain"]}],
                    "corridors": [{"corridor": "South Coast", "pressure_score": 20, "pressure_level": "medium", "days": [1], "districts": ["Colombo"], "reasons": ["Rain"]}],
                },
                "forecast_windows": [
                    {
                        "day": 1,
                        "date": "2026-06-25",
                        "corridor": "South Coast",
                        "windows": [{"label": "early_morning", "score": 12, "level": "best"}],
                    }
                ],
                "attraction_pressure": [{"name": "Gangaramaya Temple", "pressure_score": 41}],
                "components": {"weather_pressure": {"level": "medium"}},
            },
            "itinerary_guidance": {"summary": "Flexible timing."},
            "itinerary_markdown": "# Day 1\nVisit Colombo",
            "itinerary_source": "fallback",
            "daily_briefings": [
                {
                    "day": 1,
                    "date": "2026-06-25",
                    "location_label": "Colombo",
                    "weather": {"condition": "Rain", "risk_level": "medium"},
                    "crowd": {"score": 41, "risk_level": "medium"},
                    "attractions": [{"name": "Gangaramaya Temple"}],
                }
            ],
        },
    }


class SessionLoaderTests(unittest.TestCase):
    def test_dashboard_payload_shapes_session_for_frontend(self) -> None:
        repository = SessionRepository(FakeCollection(_sample_document()))
        service = SessionLoaderService(repository)

        payload = service.get_dashboard_payload("session-123")

        assert payload is not None
        self.assertEqual(payload["session_id"], "session-123")
        self.assertEqual(payload["route"]["recommended_route"]["route_id"], "route-1")
        self.assertEqual(payload["route"]["recommended_route"]["geometry_point_count"], 42)
        self.assertEqual(len(payload["route"]["recommended_route"]["sampled_points"]), 3)
        self.assertEqual(
            payload["route"]["recommended_route"]["segments"][0]["segment_path_points"][0]["lat"],
            6.9271,
        )
        self.assertEqual(payload["budget"]["total_budget_lkr"], 300000)
        self.assertEqual(payload["transport_cost"]["estimated_total_lkr"], 560)
        self.assertEqual(payload["flight"]["cheapest_result"]["price"], 303)
        self.assertEqual(payload["crowd"]["risk_level"], "high")
        self.assertEqual(payload["emotion"]["latest"]["emotion_label"], "happy")
        self.assertEqual(payload["daily_briefings"][0]["location_label"], "Colombo")
        self.assertEqual(payload["dashboard_cache"]["location_heatmap_points"][0]["label"], "Colombo")
        self.assertEqual(payload["dashboard_cache"]["time_heatmap_cells"][0]["window"], "early_morning")

    def test_chatbot_context_shapes_session_for_assistant(self) -> None:
        repository = SessionRepository(FakeCollection(_sample_document()))
        service = SessionLoaderService(repository)

        payload = service.get_chatbot_context("session-123")

        assert payload is not None
        self.assertEqual(payload["trip_summary"]["origin"], "Colombo")
        self.assertEqual(payload["trip_summary"]["destination"], "Kandy")
        self.assertEqual(payload["trip_summary"]["flight_summary"]["price"], 303)
        self.assertEqual(payload["trip_summary"]["crowd_summary"]["risk_level"], "high")
        self.assertEqual(payload["trip_summary"]["emotion_summary"]["latest"]["emotion_label"], "happy")
        self.assertEqual(payload["trip_summary"]["daily_briefings"][0]["day"], 1)
        self.assertEqual(payload["recommended_route"]["segments"][0]["top_attractions"][0]["display_name"], "Gangaramaya Temple")
        self.assertEqual(payload["chat_history"][0]["message"], "Plan Colombo to Kandy")


if __name__ == "__main__":
    unittest.main()
