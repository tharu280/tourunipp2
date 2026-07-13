from __future__ import annotations

import unittest

from clean_run.postprocess.daily_briefing import build_daily_briefings


class DailyBriefingTests(unittest.TestCase):
    def test_builds_factual_day_cards_from_existing_plan_data(self) -> None:
        plan = {
            "trip_dates": ["2026-07-20", "2026-07-21"],
            "destination_resolved": {"name": "Kandy"},
            "recommended_route": {
                "segments": [
                    {
                        "day": 1,
                        "segment_distance_m": 42000,
                        "segment_duration_seconds": 5400,
                        "segment_path_points": [
                            {"lat": 6.9, "lng": 0.0},
                            {"lat": 7.0, "lng": 80.1},
                        ],
                        "selected_attractions": [
                            {
                                "place_id": "temple-1",
                                "display_name": "Temple One",
                                "types": ["religious"],
                            }
                        ],
                        "recommended_lodging": {
                            "place_id": "hotel-1",
                            "display_name": "Route Hotel",
                            "district": "Kegalle",
                            "price_lkr": 12500,
                        },
                        "is_overnight_stop": True,
                        "weather": {
                            "forecast": {
                                "status": "ok",
                                "dates": ["2026-07-20"],
                                "weather_codes": [61],
                                "temperature_max": [29],
                                "temperature_min": [23],
                                "precipitation_probability_max": [75],
                                "precipitation_sum": [8.5],
                                "wind_speed_max": [18],
                            },
                            "risk": {"score": 67, "risk_level": "high"},
                        },
                    },
                    {
                        "day": 2,
                        "segment_distance_m": 38000,
                        "segment_duration_seconds": 4200,
                        "segment_path_points": [
                            {"lat": 7.0, "lng": 80.1},
                            {"lat": 7.3, "lng": 80.6},
                        ],
                        "selected_attractions": [
                            {"place_id": "garden-1", "display_name": "Garden Two", "types": ["park"]}
                        ],
                        "is_overnight_stop": False,
                        "weather": {
                            "forecast": {
                                "status": "ok",
                                "dates": ["2026-07-21"],
                                "weather_codes": [1],
                                "temperature_max": [25],
                                "temperature_min": [19],
                                "precipitation_probability_max": [10],
                                "precipitation_sum": [0],
                                "wind_speed_max": [8],
                            },
                            "risk": {"score": 8, "risk_level": "low"},
                        },
                    },
                ]
            },
            "crowd_signals": {
                "risk_level": "medium",
                "signal_score": 35,
                "zone_pressure": {
                    "days": [
                        {
                            "day": 1,
                            "districts": ["Kegalle"],
                            "pressure_score": 48,
                            "pressure_level": "medium",
                            "preferred_visit_window": "mid_morning",
                            "reasons": ["tourism demand is elevated"],
                        },
                        {
                            "day": 2,
                            "districts": ["Kandy"],
                            "pressure_score": 0,
                            "pressure_level": "low",
                            "preferred_visit_window": "mid_morning",
                            "reasons": ["conditions look manageable"],
                        },
                    ]
                },
                "attraction_pressure": [
                    {
                        "day": 1,
                        "place_id": "temple-1",
                        "name": "Temple One",
                        "pressure_score": 62,
                        "pressure_level": "high",
                        "best_visit_window": {"label": "early_morning", "score": 50},
                        "reasons": ["popular attraction"],
                    }
                ],
            },
            "road_alerts": {
                "risk_level": "medium",
                "last_updated": "2026-07-19T08:00:00Z",
                "incidents": [
                    {
                        "report_number": "R-1",
                        "road_location": "Kegalle road",
                        "damage_type": "Landslide",
                        "status": "verified",
                        "latitude": 6.95,
                        "longitude": 80.05,
                    },
                    {
                        "report_number": "R-2",
                        "road_location": "Kandy road",
                        "damage_type": "Road breakage",
                        "status": "resolved",
                        "latitude": 7.28,
                        "longitude": 80.58,
                    },
                ],
            },
            "transport_cost": {
                "segments": [
                    {"day": 1, "estimated_fare_lkr": 420},
                    {"day": 2, "estimated_fare_lkr": 380},
                ]
            },
        }

        briefings = build_daily_briefings(plan)

        self.assertEqual(len(briefings), 2)
        first, second = briefings
        self.assertEqual(first["date"], "2026-07-20")
        self.assertEqual(first["location_label"], "Kegalle")
        self.assertEqual(first["weather"]["condition"], "Rain")
        self.assertEqual(first["weather"]["rain_probability_pct"], 75)
        self.assertEqual(first["attractions"][0]["crowd"]["source"], "attraction_estimate")
        self.assertEqual(first["attractions"][0]["crowd"]["score"], 62)
        self.assertEqual(first["attractions"][0]["recommended_time"], "early_morning")
        self.assertEqual(first["roads"]["incidents"][0]["report_number"], "R-1")
        self.assertEqual(first["accommodation"]["name"], "Route Hotel")
        self.assertEqual(first["costs"]["tracked_total_lkr"], 12920)
        self.assertTrue(any("Route Hotel" in item for item in first["recommendations"]))

        self.assertEqual(second["location_label"], "Kandy")
        self.assertEqual(second["crowd"]["score"], 0)
        self.assertEqual(second["attractions"][0]["crowd"]["source"], "day_estimate")
        self.assertEqual(second["roads"]["incidents"][0]["report_number"], "R-2")
        self.assertIsNone(second["accommodation"])
        self.assertEqual(second["costs"]["tracked_total_lkr"], 380)

    def test_returns_empty_list_when_route_has_no_days(self) -> None:
        self.assertEqual(build_daily_briefings({}), [])


if __name__ == "__main__":
    unittest.main()
