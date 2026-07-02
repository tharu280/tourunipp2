from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from clean_run.enrich.weather_engine import enrich_segment_weather


class WeatherEngineTests(unittest.TestCase):
    def test_enrich_segment_weather_fails_soft_when_provider_errors(self) -> None:
        segment = {
            "mid_point": {"lat": 7.29, "lng": 80.63},
        }

        with patch(
            "clean_run.enrich.weather_engine.fetch_weather_for_point",
            side_effect=requests.HTTPError("400 Client Error: Bad Request"),
        ):
            enriched = enrich_segment_weather(
                segment=segment,
                trip_dates=["2026-06-22", "2026-06-23"],
                day_index=0,
            )

        self.assertEqual(enriched["weather"]["forecast"]["status"], "unavailable")
        self.assertEqual(enriched["weather"]["risk"]["risk_level"], "unknown")
        self.assertIn("provider request failed", enriched["weather"]["risk"]["reasons"][0].lower())


if __name__ == "__main__":
    unittest.main()
