from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from clean_run.api import app, safe_error_detail


class FakeEmotionRepository:
    def __init__(self) -> None:
        self.saved_checkin = None
        self.saved_recommendation = None

    def get_session(self, session_id: str):
        if session_id != "session-emotion":
            return None
        return {
            "session_id": session_id,
            "plan": {
                "road_alerts": {"risk_level": "medium", "critical_count": 0, "total_deduplicated": 1},
                "crowd_signals": {"risk_level": "medium", "signal_score": 45},
                "recommended_route": {
                    "segments": [
                        {
                            "day": 1,
                            "day_label": "Day 1",
                            "segment_duration_seconds": 3600,
                            "weather": {"risk": {"risk_level": "low", "risk_score": 10}},
                            "selected_attractions": [
                                {
                                    "place_id": "gangaramaya",
                                    "display_name": "Gangaramaya Temple",
                                    "lat": 6.9167,
                                    "lng": 79.8562,
                                }
                            ],
                        },
                        {
                            "day": 2,
                            "day_label": "Day 2",
                            "segment_duration_seconds": 7200,
                            "segment_distance_km": 80.0,
                            "weather": {"risk": {"risk_level": "medium", "risk_score": 45}},
                            "selected_attractions": [
                                {
                                    "place_id": "peradeniya",
                                    "display_name": "Royal Botanical Gardens",
                                    "lat": 7.2710,
                                    "lng": 80.5950,
                                }
                            ],
                        }
                    ]
                },
            },
        }

    def add_emotion_checkin(
        self,
        *,
        session_id: str,
        checkin: dict,
        recommendation: dict,
        emotion_summary: dict | None = None,
    ) -> bool:
        self.saved_checkin = checkin
        self.saved_recommendation = recommendation
        self.saved_emotion_summary = emotion_summary
        return session_id == "session-emotion"


class CleanApiTests(unittest.TestCase):
    def test_clean_api_imports_as_standalone_backend(self) -> None:
        self.assertEqual(app.title, "TourUni Clean Run Backend")
        paths = {route.path for route in app.routes}
        self.assertIn("/chat", paths)
        self.assertIn("/plan", paths)
        self.assertIn("/flights/search", paths)
        self.assertIn("/sessions/{session_id}/refresh-intelligence", paths)
        self.assertIn("/sessions/{session_id}/emotion-checkins", paths)
        self.assertIn("/sessions/{session_id}/emotion-targets", paths)

    def test_error_details_redact_api_keys(self) -> None:
        detail = safe_error_detail(
            "bad key api_key='AIzaExampleSecretKeyThatShouldBeHidden12345'",
            feature="Planning",
        )
        self.assertIn("[redacted]", detail)
        self.assertNotIn("AIzaExample", detail)

    def test_flight_search_endpoint_returns_options(self) -> None:
        class FakeFlightSearchService:
            def __init__(self) -> None:
                self.preferences = None

            def search(self, preferences):
                self.preferences = preferences
                return {
                    "origin": preferences.origin,
                    "destination": preferences.destination,
                    "results_count": 1,
                    "results": [
                        {
                            "price": 321,
                            "currency": "USD",
                            "airline": "UL",
                            "booking_link": "https://example.com/book",
                        }
                    ],
                    "cheapest_result": {
                        "price": 321,
                        "currency": "USD",
                        "airline": "UL",
                        "booking_link": "https://example.com/book",
                    },
                }

        flight_service = FakeFlightSearchService()
        client = TestClient(app)

        with patch("clean_run.api.get_flight_search_service", return_value=flight_service):
            response = client.post(
                "/flights/search",
                json={
                    "origin": "DXB",
                    "departure_date": "2026-07-20",
                    "passengers": 2,
                    "cabin_class": "economy",
                    "total_budget_lkr": 500000,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["origin"], "DXB")
        self.assertEqual(payload["destination"], "CMB")
        self.assertEqual(payload["results_count"], 1)
        self.assertEqual(payload["cheapest_result"]["booking_link"], "https://example.com/book")
        self.assertEqual(payload["budget_handoff"]["selected_flight_budget_lkr_estimated"], 96300.0)
        self.assertEqual(payload["budget_handoff"]["remaining_budget_lkr"], 403700.0)
        self.assertEqual(flight_service.preferences.passengers, 2)
        self.assertEqual(flight_service.preferences.total_budget_lkr, 500000)

    def test_emotion_checkin_endpoint_accepts_only_structured_result(self) -> None:
        repository = FakeEmotionRepository()
        client = TestClient(app)

        with patch("clean_run.api.get_session_repository", return_value=repository):
            response = client.post(
                "/sessions/session-emotion/emotion-checkins",
                json={
                    "attraction_name": "Gangaramaya Temple",
                    "user_location": {
                        "latitude": 6.9168,
                        "longitude": 79.8563,
                        "accuracy_meters": 15,
                    },
                    "emotion_label": "happy",
                    "emotion_confidence": 0.82,
                    "top_predictions": [{"class_name": "happy", "probability": 0.82}],
                    "model_version": "rafdb5_local_tflite",
                    "local_inference": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["checkin"]["emotion_label"], "happy")
        self.assertFalse(payload["privacy"]["raw_image_stored"])
        self.assertFalse(payload["privacy"]["identity_recognition"])
        self.assertFalse(repository.saved_checkin["raw_image_stored"])
        self.assertTrue(payload["checkin"]["location_context"]["matched_planned_attraction"])
        self.assertTrue(payload["checkin"]["location_context"]["within_checkin_radius"])
        self.assertIn("emotion_summary", payload)
        self.assertIn("recommendation", payload)

    def test_start_of_day_emotion_checkin_returns_day_ahead_recommendation(self) -> None:
        repository = FakeEmotionRepository()
        client = TestClient(app)

        with patch("clean_run.api.get_session_repository", return_value=repository):
            response = client.post(
                "/sessions/session-emotion/emotion-checkins",
                json={
                    "checkin_type": "start_of_day",
                    "day": 2,
                    "emotion_label": "neutral",
                    "emotion_confidence": 0.74,
                    "top_predictions": [{"class_name": "neutral", "probability": 0.74}],
                    "model_version": "rafdb5_local_tflite",
                    "local_inference": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["checkin"]["checkin_type"], "start_of_day")
        self.assertEqual(payload["checkin"]["day"], 2)
        self.assertEqual(payload["recommendation"]["type"], "start_of_day")
        self.assertEqual(payload["recommendation"]["day_label"], "Day 2")
        self.assertIn("Royal Botanical Gardens", payload["recommendation"]["day_context"]["attractions"])
        self.assertFalse(payload["privacy"]["raw_image_stored"])

    def test_emotion_targets_endpoint_returns_mobile_geofence_targets(self) -> None:
        repository = FakeEmotionRepository()
        client = TestClient(app)

        with patch("clean_run.api.get_session_repository", return_value=repository):
            response = client.get("/sessions/session-emotion/emotion-targets")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["target_count"], 2)
        self.assertEqual(payload["targets"][0]["attraction_id"], "gangaramaya")
        self.assertTrue(payload["mobile_flow"]["local_tflite_inference_required"])


if __name__ == "__main__":
    unittest.main()
