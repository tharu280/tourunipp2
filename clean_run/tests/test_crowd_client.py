from __future__ import annotations

import unittest
from unittest.mock import patch

from clean_run.integrations.crowd_client import get_crowd_signals_for_route
from clean_run.integrations.wiki_pageviews_client import MonthlyPageviewRow


def _route() -> dict:
    return {
        "segments": [
            {
                "day": 1,
                "top_attractions": [
                    {
                        "place_id": "sigiriya",
                        "display_name": "Sigiriya",
                        "district": "Matale",
                        "tags": ["iconic", "unesco"],
                        "types": ["historic"],
                        "tier": "tier_1",
                        "distance_from_route_m": 1000,
                        "source_urls": ["https://en.wikipedia.org/wiki/Sigiriya"],
                    }
                ],
                "gemini_selected_attractions": [{"place_id": "sigiriya", "display_name": "Sigiriya"}],
                "weather": {
                    "forecast": {"dates": ["2025-12-24"]},
                    "risk": {"score": 10, "risk_level": "low", "reasons": []},
                },
            }
        ],
        "road_alerts": {"risk_level": "low", "critical_count": 0, "total_deduplicated": 0},
        "traffic_data": {"status": "ok", "risk_level": "low", "congestion_score": 0, "summary": "Traffic is light."},
    }


class CrowdClientTests(unittest.TestCase):
    @patch("clean_run.integrations.crowd_client._get_public_holidays", return_value=[])
    def test_crowd_signals_include_sltda_tourism_demand(self, _mock_holidays) -> None:
        payload = get_crowd_signals_for_route(
            route=_route(),
            start_date="2025-12-24",
            trip_days=1,
        )

        tourism = payload["components"]["tourism_demand_pressure"]
        self.assertEqual(tourism["level"], "high")
        self.assertGreaterEqual(tourism["score"], 26)
        self.assertIn("Tourism demand is high", payload["helper_summary"])
        self.assertEqual(payload["zone_pressure"]["days"][0]["components"]["tourism_demand"], tourism["score"])
        self.assertGreaterEqual(payload["attraction_pressure"][0]["pressure_score"], tourism["score"])

    @patch(
        "clean_run.integrations.wiki_pageviews_client.load_monthly_pageview_cache",
        return_value=(
            MonthlyPageviewRow("sigiriya", "Sigiriya", "Sigiriya", 2025, 1, 1000, "test"),
            MonthlyPageviewRow("sigiriya", "Sigiriya", "Sigiriya", 2025, 12, 12000, "test"),
        ),
    )
    @patch("clean_run.integrations.crowd_client._get_public_holidays", return_value=[])
    def test_attraction_pressure_includes_wikipedia_interest(self, _mock_holidays, _mock_cache) -> None:
        payload = get_crowd_signals_for_route(
            route=_route(),
            start_date="2025-12-24",
            trip_days=1,
        )

        attraction = payload["attraction_pressure"][0]
        self.assertEqual(attraction["wiki_interest"]["level"], "high")
        self.assertGreater(attraction["wiki_interest"]["score"], 0)
        self.assertEqual(attraction["combined_pressure"]["score"], attraction["pressure_score"])
        self.assertEqual(
            attraction["combined_pressure"]["components"]["wikipedia_interest"],
            attraction["wiki_interest"]["score"],
        )
        self.assertIn("combined_pressure", attraction)
        self.assertIn("best_visit_window", attraction)
        self.assertGreater(len(attraction["visit_window_scores"]), 0)
        self.assertTrue(
            any("Wikipedia monthly pageviews" in reason for reason in attraction["reasons"])
        )


if __name__ == "__main__":
    unittest.main()
