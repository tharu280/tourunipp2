from __future__ import annotations

import unittest
from unittest.mock import patch

from clean_run.routes.generate import RouteGenerationService, _select_recommended_route, RouteProfile
from clean_run.routes.polyline import max_corridor_deviation_m
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


# ---------------------------------------------------------------------------
# Helpers for Colombo → Badulla geography tests
# ---------------------------------------------------------------------------
# Colombo: 6.9271°N, 79.8612°E
# Badulla:  6.9934°N, 81.0550°E  (almost due east, ~130 km straight-line)
# Galle:    6.0328°N, 80.2170°E  (south-west of Colombo)
# Matara:   5.9549°N, 80.5353°E  (south of Badulla corridor)

# South-coast detour: Colombo → Galle → Matara → Badulla (~450 km road dist)
_SOUTH_COAST_SAMPLED_POINTS = [
    {"lat": 6.9271, "lng": 79.8612},  # Colombo (start)
    {"lat": 6.5000, "lng": 79.9500},  # heading south
    {"lat": 6.0328, "lng": 80.2170},  # Galle
    {"lat": 5.9549, "lng": 80.5353},  # Matara (far south)
    {"lat": 6.2000, "lng": 80.8000},  # turning north-east
    {"lat": 6.9934, "lng": 81.0550},  # Badulla (end)
]

# Direct A9 corridor: Colombo → Kandy → Badulla (~230 km road dist)
_DIRECT_SAMPLED_POINTS = [
    {"lat": 6.9271, "lng": 79.8612},  # Colombo
    {"lat": 7.1000, "lng": 80.0000},  # heading north-east via Kandy direction
    {"lat": 7.2906, "lng": 80.6337},  # Kandy area
    {"lat": 7.1500, "lng": 80.8000},  # Nuwara Eliya area
    {"lat": 6.9934, "lng": 81.0550},  # Badulla
]

_COLOMBO = {"lat": 6.9271, "lng": 79.8612}
_BADULLA = {"lat": 6.9934, "lng": 81.0550}


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

    def _resolved_trip_colombo_badulla(self) -> ResolvedTripContext:
        return ResolvedTripContext(
            origin_text="Colombo",
            destination_text="Badulla",
            duration_text="3 days",
            start_date="2026-06-12",
            trip_days=3,
            trip_dates=["2026-06-12", "2026-06-13", "2026-06-14"],
            origin_resolved=ResolvedPlace(
                place_id="colombo-id",
                name="Colombo",
                formatted_address="Colombo, Sri Lanka",
                lat=6.9271,
                lng=79.8612,
                types=["locality"],
            ),
            destination_resolved=ResolvedPlace(
                place_id="badulla-id",
                name="Badulla",
                formatted_address="Badulla, Sri Lanka",
                lat=6.9934,
                lng=81.0550,
                types=["locality"],
            ),
        )

    # ------------------------------------------------------------------
    # Existing tests (must continue to pass)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # New tests: generic detour preference
    # ------------------------------------------------------------------

    def test_shorter_direct_route_preferred_when_detour_returned_first(self) -> None:
        """route_1 is a long detour; route_2 is shorter/direct – backend must select route_2."""
        # Build profiles directly so we can control sampled_points.
        route_detour = RouteProfile(
            route_id="route_1",
            route_labels=["DETOUR"],
            distance_meters=450_000,
            duration="18000s",
            sampled_points=_SOUTH_COAST_SAMPLED_POINTS,
        )
        route_direct = RouteProfile(
            route_id="route_2",
            route_labels=["DIRECT"],
            distance_meters=230_000,
            duration="9000s",
            sampled_points=_DIRECT_SAMPLED_POINTS,
        )
        result = _select_recommended_route(
            [route_detour, route_direct],
            origin=_COLOMBO,
            destination=_BADULLA,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.route_id, "route_2")

    # ------------------------------------------------------------------
    # New tests: Colombo → Badulla south-coast detour scenario
    # ------------------------------------------------------------------

    def test_colombo_badulla_rejects_south_coast_detour_via_galle(self) -> None:
        """The Galle/Matara south-coast route (~450 km) must be rejected in favour
        of the direct A9 corridor route (~230 km) for Colombo→Badulla."""
        route_galle = RouteProfile(
            route_id="route_1",
            route_labels=["DEFAULT_ROUTE"],
            distance_meters=452_000,   # ~452 km via Galle/Matara
            duration="19800s",
            sampled_points=_SOUTH_COAST_SAMPLED_POINTS,
        )
        route_direct = RouteProfile(
            route_id="route_2",
            route_labels=["DEFAULT_ROUTE_ALTERNATE"],
            distance_meters=228_000,   # ~228 km via Kandy/Nuwara Eliya
            duration="10800s",
            sampled_points=_DIRECT_SAMPLED_POINTS,
        )
        result = _select_recommended_route(
            [route_galle, route_direct],
            origin=_COLOMBO,
            destination=_BADULLA,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.route_id, "route_2",
                         "Expected direct A9 route, got south-coast detour instead")

    def test_colombo_badulla_single_detour_route_falls_back_gracefully(self) -> None:
        """When Google returns only ONE route and it's a detour, we must still
        return it rather than crashing (graceful fallback)."""
        route_only = RouteProfile(
            route_id="route_1",
            route_labels=["DEFAULT_ROUTE"],
            distance_meters=452_000,
            duration="19800s",
            sampled_points=_SOUTH_COAST_SAMPLED_POINTS,
        )
        result = _select_recommended_route(
            [route_only],
            origin=_COLOMBO,
            destination=_BADULLA,
        )
        # Must not be None – fallback to shortest available.
        self.assertIsNotNone(result)
        self.assertEqual(result.route_id, "route_1")

    def test_colombo_badulla_geometry_detects_south_coast_deviation(self) -> None:
        """The south-coast sampled points must produce a very large corridor
        deviation (>> 80 km), confirming the geometry filter will trigger."""
        deviation = max_corridor_deviation_m(
            _SOUTH_COAST_SAMPLED_POINTS,
            origin=_COLOMBO,
            destination=_BADULLA,
        )
        # Matara is ~130 km south of the Colombo-Badulla corridor.
        self.assertGreater(deviation, 100_000,
                           f"Expected > 100 km deviation for south-coast route, got {deviation/1000:.1f} km")

    def test_direct_route_corridor_deviation_is_small(self) -> None:
        """The direct A9 corridor route must have a small perpendicular deviation."""
        deviation = max_corridor_deviation_m(
            _DIRECT_SAMPLED_POINTS,
            origin=_COLOMBO,
            destination=_BADULLA,
        )
        # A reasonable mountain route may deviate up to ~40 km.
        self.assertLess(deviation, 60_000,
                        f"Expected < 60 km deviation for direct route, got {deviation/1000:.1f} km")

    def test_recommended_route_has_sampled_points_for_frontend(self) -> None:
        """recommended_route must always carry sampled_points so the frontend
        map can render the real Google polyline."""
        service = RouteGenerationService(routes_client=fake_routes_client)
        result = service.generate(self._resolved_trip())
        self.assertIsNotNone(result.recommended_route)
        self.assertTrue(
            result.recommended_route.sampled_points,
            "recommended_route.sampled_points must be non-empty for the frontend map",
        )


if __name__ == "__main__":
    unittest.main()
