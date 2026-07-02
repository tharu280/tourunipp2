from __future__ import annotations

import unittest

from clean_run.routes.generate import RouteGenerationService
from clean_run.trip.resolve import ResolvedPlace, ResolvedTripContext


def fake_routes_client(**kwargs):
    return {
        "routes": [
            {
                "routeLabels": ["DEFAULT_ROUTE"],
                "distanceMeters": 2211,
                "duration": "600s",
                "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                "legs": [
                    {
                        "distanceMeters": 2211,
                        "duration": "600s",
                        "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                    }
                ],
            },
            {
                "routeLabels": ["DEFAULT_ROUTE_ALTERNATE"],
                "distanceMeters": 2500,
                "duration": "660s",
                "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                "legs": [],
            },
        ]
    }


def fake_detour_first_routes_client(**kwargs):
    return {
        "routes": [
            {
                "routeLabels": ["DEFAULT_ROUTE"],
                "distanceMeters": 6000,
                "duration": "520s",
                "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                "legs": [],
            },
            {
                "routeLabels": ["DEFAULT_ROUTE_ALTERNATE"],
                "distanceMeters": 2400,
                "duration": "640s",
                "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                "legs": [],
            },
        ]
    }


class RetryRoutesClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if (kwargs.get("route_modifiers") or {}).get("avoidHighways"):
            return {
                "routes": [
                    {
                        "routeLabels": ["AVOID_HIGHWAYS"],
                        "distanceMeters": 135000,
                        "duration": "14400s",
                        "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                        "legs": [],
                    }
                ]
            }
        return {
            "routes": [
                {
                    "routeLabels": ["HIGHWAY_DETOUR"],
                    "distanceMeters": 260000,
                    "duration": "12000s",
                    "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
                    "legs": [],
                }
            ]
        }


class RouteGenerationTests(unittest.TestCase):
    def _resolved_trip(self) -> ResolvedTripContext:
        return ResolvedTripContext(
            origin_text="Colombo",
            destination_text="Kandy",
            duration_text="2 days",
            start_date="2026-06-12",
            trip_days=2,
            trip_dates=["2026-06-12", "2026-06-13"],
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

    def test_generate_shapes_route_profiles(self) -> None:
        service = RouteGenerationService(routes_client=fake_routes_client)
        result = service.generate(self._resolved_trip())
        self.assertEqual(result.route_count, 2)
        self.assertEqual(len(result.routes), 2)
        self.assertEqual(result.recommended_route.route_id, "route_1")
        self.assertEqual(result.routes[0].geometry_point_count, 3)
        self.assertEqual(len(result.routes[0].segments), 2)
        self.assertTrue(result.routes[0].sampled_points)

    def test_generate_assigns_segments_with_day_labels(self) -> None:
        service = RouteGenerationService(routes_client=fake_routes_client)
        result = service.generate(self._resolved_trip())
        self.assertEqual(result.routes[0].segments[0].day_label, "Day 1")
        self.assertEqual(result.routes[0].segments[1].day_label, "Day 2")

    def test_generate_avoids_large_detour_as_recommended_route(self) -> None:
        service = RouteGenerationService(routes_client=fake_detour_first_routes_client)
        result = service.generate(self._resolved_trip())
        self.assertEqual(result.route_count, 2)
        self.assertEqual(result.recommended_route.route_id, "route_2")

    def test_generate_retries_excessive_detour_with_avoid_highways(self) -> None:
        client = RetryRoutesClient()
        service = RouteGenerationService(routes_client=client)
        result = service.generate(self._resolved_trip())
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1]["route_modifiers"], {"avoidHighways": True})
        self.assertEqual(result.recommended_route.route_labels, ["AVOID_HIGHWAYS"])


if __name__ == "__main__":
    unittest.main()
