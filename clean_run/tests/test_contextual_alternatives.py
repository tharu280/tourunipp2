from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from clean_run.api import app
from clean_run.recommendations.contextual_alternatives import build_contextual_alternatives


def _session(*, crowd_level: str = "high", weather_level: str = "high") -> dict:
    return {
        "session_id": "session-alternatives",
        "plan": {
            "recommended_route": {
                "segments": [
                    {
                        "day": 1,
                        "selected_attractions": [
                            {
                                "place_id": "galle-fort",
                                "display_name": "Galle Fort",
                                "lat": 6.0260,
                                "lng": 80.2170,
                            }
                        ],
                    }
                ]
            },
            "daily_briefings": [
                {
                    "day": 1,
                    "date": "2026-07-20",
                    "weather": {
                        "risk_level": weather_level,
                        "condition": "Rain",
                        "rain_probability_pct": 85 if weather_level == "high" else 10,
                    },
                    "crowd": {"risk_level": crowd_level, "score": 55},
                    "attractions": [
                        {
                            "place_id": "galle-fort",
                            "name": "Galle Fort",
                            "crowd": {
                                "level": crowd_level,
                                "score": 62,
                                "source": "attraction_estimate",
                            },
                        }
                    ],
                }
            ],
        },
    }


def _overpass_places() -> list[dict]:
    return [
        {
            "type": "node",
            "id": 1,
            "lat": 6.0300,
            "lon": 80.2200,
            "tags": {
                "name": "Maritime Museum",
                "tourism": "museum",
                "opening_hours": "09:00-17:00",
                "wikidata": "Q1",
            },
        },
        {
            "type": "node",
            "id": 2,
            "lat": 6.0270,
            "lon": 80.2180,
            "tags": {"name": "Coastal Park", "leisure": "park"},
        },
        {
            "type": "node",
            "id": 3,
            "lat": 6.0260,
            "lon": 80.2170,
            "tags": {"name": "Galle Fort", "historic": "fort"},
        },
        {
            "type": "node",
            "id": 4,
            "lat": 6.0280,
            "lon": 80.2190,
            "tags": {"tourism": "museum"},
        },
    ]


class ContextualAlternativesTests(unittest.TestCase):
    def test_rainy_high_pressure_stop_prefers_indoor_named_place(self) -> None:
        original = _session()
        before = copy.deepcopy(original)

        with patch(
            "clean_run.recommendations.contextual_alternatives._cached_overpass",
            return_value=_overpass_places(),
        ):
            result = build_contextual_alternatives(
                original,
                interests=["Culture"],
                limit_per_attraction=3,
            )

        self.assertEqual(result["status"], "available")
        self.assertTrue(result["temporary"])
        self.assertFalse(result["persisted"])
        self.assertEqual(original, before)
        group = result["recommendation_groups"][0]
        self.assertTrue(group["trigger"]["fallback_needed"])
        alternatives = group["alternatives"]
        self.assertEqual(alternatives[0]["name"], "Maritime Museum")
        self.assertEqual(alternatives[0]["category"], "museum")
        self.assertEqual(alternatives[0]["distance_method"], "straight_line")
        self.assertEqual(alternatives[0]["opening_hours_confidence"], "provided_by_osm")
        self.assertEqual(alternatives[0]["interest_matches"], ["Culture"])
        self.assertNotIn("Galle Fort", [item["name"] for item in alternatives])
        self.assertIn("Consider Maritime Museum", group["guidance"])

    def test_low_risk_stop_does_not_call_overpass(self) -> None:
        with patch(
            "clean_run.recommendations.contextual_alternatives._cached_overpass"
        ) as fetch:
            result = build_contextual_alternatives(
                _session(crowd_level="low", weather_level="low")
            )

        fetch.assert_not_called()
        self.assertEqual(result["status"], "not_needed")
        self.assertEqual(result["recommendation_groups"], [])

    def test_day_and_attraction_filters_limit_evaluation(self) -> None:
        with patch(
            "clean_run.recommendations.contextual_alternatives._cached_overpass",
            return_value=_overpass_places(),
        ) as fetch:
            wrong_day = build_contextual_alternatives(_session(), day=2)
            wrong_attraction = build_contextual_alternatives(
                _session(), attraction_id="another-attraction"
            )

        fetch.assert_not_called()
        self.assertEqual(wrong_day["status"], "not_needed")
        self.assertEqual(wrong_attraction["status"], "not_needed")

    def test_api_endpoint_reads_session_without_repository_write_methods(self) -> None:
        class ReadOnlyRepository:
            def get_session(self, session_id: str):
                return _session() if session_id == "session-alternatives" else None

        client = TestClient(app)
        generated = {
            "session_id": "session-alternatives",
            "status": "not_needed",
            "temporary": True,
            "persisted": False,
            "recommendation_groups": [],
        }
        with (
            patch("clean_run.api.get_session_repository", return_value=ReadOnlyRepository()),
            patch("clean_run.api.build_contextual_alternatives", return_value=generated) as build,
        ):
            response = client.post(
                "/sessions/session-alternatives/contextual-alternatives",
                json={"day": 1, "interests": ["Culture"], "radius_meters": 4000},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), generated)
        build.assert_called_once()
        self.assertEqual(build.call_args.kwargs["day"], 1)
        self.assertEqual(build.call_args.kwargs["interests"], ["Culture"])
        self.assertEqual(build.call_args.kwargs["radius_meters"], 4000)


if __name__ == "__main__":
    unittest.main()
