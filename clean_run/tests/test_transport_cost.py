from __future__ import annotations

import unittest

from clean_run.postprocess.transport_cost import (
    estimate_bus_fare_for_distance_km,
    estimate_transport_cost_for_route,
    fare_band_for_distance_km,
)


class TransportCostTests(unittest.TestCase):
    def test_bus_fare_uses_2026_stage_table(self) -> None:
        band = fare_band_for_distance_km(120.0)

        assert band is not None
        self.assertEqual(band["stage"], 120)
        self.assertEqual(band["new_fare_lkr"], 862)
        self.assertEqual(estimate_bus_fare_for_distance_km(120.0), 862)

    def test_route_transport_cost_includes_fare_stage_metadata(self) -> None:
        payload = estimate_transport_cost_for_route(
            {
                "distance_meters": 120000,
                "segments": [
                    {
                        "day": 1,
                        "day_label": "Day 1",
                        "segment_distance_m": 120000,
                    }
                ]
            }
        )

        self.assertEqual(payload["source"], "ntc_normal_service_fare_stage_table_2026")
        self.assertEqual(payload["confidence"], "high")
        self.assertEqual(payload["estimated_total_lkr"], 862)
        self.assertEqual(payload["segments"][0]["fare_stage"], 120)
        self.assertEqual(payload["distance_basis"], "segment_distance")

    def test_route_transport_cost_scales_trimmed_planning_segments_to_full_route(self) -> None:
        payload = estimate_transport_cost_for_route(
            {
                "distance_meters": 332402,
                "segments": [
                    {"day": 1, "day_label": "Day 1", "segment_distance_m": 32991.41},
                    {"day": 2, "day_label": "Day 2", "segment_distance_m": 32991.41},
                    {"day": 3, "day_label": "Day 3", "segment_distance_m": 32991.41},
                    {"day": 4, "day_label": "Day 4", "segment_distance_m": 32991.41},
                ],
            }
        )

        self.assertEqual(payload["distance_basis"], "scaled_to_full_route_distance")
        self.assertEqual(payload["route_distance_km"], 332.4)
        self.assertEqual(payload["raw_segment_total_distance_km"], 132.0)
        self.assertAlmostEqual(payload["total_distance_km"], 332.4, places=1)
        self.assertGreater(payload["estimated_total_lkr"], 1096)
        self.assertEqual(payload["segments"][0]["raw_segment_distance_km"], 33.0)


if __name__ == "__main__":
    unittest.main()
