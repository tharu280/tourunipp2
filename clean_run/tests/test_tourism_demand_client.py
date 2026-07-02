from __future__ import annotations

import unittest

from clean_run.integrations.tourism_demand_client import get_tourism_demand_for_date


class TourismDemandClientTests(unittest.TestCase):
    def test_december_peak_week_is_high_pressure(self) -> None:
        payload = get_tourism_demand_for_date("2025-12-27")

        self.assertEqual(payload["level"], "high")
        self.assertGreaterEqual(payload["score"], 26)
        self.assertEqual(payload["granularity"], "daily")
        self.assertEqual(payload["matched_date"], "2025-12-27")
        self.assertEqual(payload["arrivals"], 12397)
        self.assertFalse(payload["is_seasonal_proxy"])

    def test_future_dates_use_latest_available_seasonal_proxy(self) -> None:
        payload = get_tourism_demand_for_date("2026-07-20")

        self.assertEqual(payload["granularity"], "daily")
        self.assertEqual(payload["matched_date"], "2025-07-20")
        self.assertEqual(payload["arrivals"], 6337)
        self.assertTrue(payload["is_seasonal_proxy"])
        self.assertIn("SLTDA daily arrivals indicate", payload["summary"])


if __name__ == "__main__":
    unittest.main()
