from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

import requests

from clean_run.integrations.weather_client import (
    _fetch_weather_cached,
    fetch_weather_for_point,
    summarize_daily_weather,
    weather_risk_score,
)


class WeatherClientTests(unittest.TestCase):
    def setUp(self) -> None:
        _fetch_weather_cached.cache_clear()

    def tearDown(self) -> None:
        _fetch_weather_cached.cache_clear()

    @patch.dict(os.environ, {"WEATHER_API_KEY": "test-weather-key"}, clear=False)
    @patch("clean_run.integrations.weather_client.requests.get")
    def test_falls_back_to_weatherapi_when_open_meteo_fails(self, mock_get: Mock) -> None:
        open_meteo_failure = Mock()
        open_meteo_failure.raise_for_status.side_effect = requests.HTTPError("open-meteo failed")

        weatherapi_success = Mock()
        weatherapi_success.raise_for_status.return_value = None
        weatherapi_success.json.return_value = {
            "forecast": {
                "forecastday": [
                    {
                        "date": "2026-06-22",
                        "day": {
                            "maxtemp_c": 29.0,
                            "mintemp_c": 23.0,
                            "totalprecip_mm": 4.2,
                            "daily_chance_of_rain": 65,
                            "maxwind_kph": 18.0,
                            "condition": {"code": 1189},
                        },
                    }
                ]
            }
        }

        mock_get.side_effect = [open_meteo_failure, weatherapi_success]

        payload = fetch_weather_for_point(
            latitude=7.29,
            longitude=80.63,
            start_date="2026-06-22",
            end_date="2026-06-22",
        )

        self.assertEqual(payload["provider"], "weatherapi")
        self.assertEqual(payload["daily"]["time"], ["2026-06-22"])
        self.assertEqual(payload["daily"]["weather_code"], [1189])
        self.assertEqual(payload["daily"]["temperature_2m_max"], [29.0])
        self.assertEqual(payload["daily"]["temperature_2m_min"], [23.0])

    def test_unavailable_weather_summary_preserves_provider_reason(self) -> None:
        summary = summarize_daily_weather(
            {
                "provider": "weatherapi",
                "status": "unavailable",
                "unavailable_reason": "WeatherAPI returned no forecast days for the requested trip dates.",
                "requested_range": {"start_date": "2026-07-20", "end_date": "2026-07-23"},
                "daily": {"time": []},
            }
        )
        risk = weather_risk_score(summary, day_index=0)

        self.assertEqual(summary["status"], "unavailable")
        self.assertEqual(summary["provider"], "weatherapi")
        self.assertIn("no forecast days", summary["reason"])
        self.assertEqual(risk["risk_level"], "unknown")
        self.assertIn("no forecast days", risk["reasons"][0])

    @patch.dict(os.environ, {}, clear=True)
    @patch("clean_run.integrations.weather_client.requests.get")
    def test_raises_original_error_when_no_weatherapi_key_exists(self, mock_get: Mock) -> None:
        open_meteo_failure = Mock()
        open_meteo_failure.raise_for_status.side_effect = requests.HTTPError("open-meteo failed")
        mock_get.return_value = open_meteo_failure

        with self.assertRaises(requests.HTTPError):
            fetch_weather_for_point(
                latitude=7.29,
                longitude=80.63,
                start_date="2026-06-22",
                end_date="2026-06-22",
            )


if __name__ == "__main__":
    unittest.main()
