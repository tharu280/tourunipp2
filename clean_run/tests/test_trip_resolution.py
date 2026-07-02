from __future__ import annotations

import unittest

from clean_run.trip.resolve import ResolveTripService, build_trip_dates, parse_trip_days


def fake_resolver(*, query: str) -> dict[str, object]:
    places = {
        "Colombo": {
            "place_id": "colombo-id",
            "name": "Colombo",
            "formatted_address": "Colombo, Sri Lanka",
            "lat": 6.9271,
            "lng": 79.8612,
            "types": ["locality", "political"],
        },
        "Kandy": {
            "place_id": "kandy-id",
            "name": "Kandy",
            "formatted_address": "Kandy, Sri Lanka",
            "lat": 7.2906,
            "lng": 80.6337,
            "types": ["locality", "political"],
        },
    }
    return places[query]


class TripResolutionTests(unittest.TestCase):
    def test_parse_trip_days_accepts_days(self) -> None:
        self.assertEqual(parse_trip_days("3 days"), 3)

    def test_parse_trip_days_accepts_weeks(self) -> None:
        self.assertEqual(parse_trip_days("2 weeks"), 14)

    def test_build_trip_dates_creates_full_range(self) -> None:
        self.assertEqual(
            build_trip_dates("2026-06-12", 3),
            ["2026-06-12", "2026-06-13", "2026-06-14"],
        )

    def test_resolve_trip_returns_structured_context(self) -> None:
        service = ResolveTripService(place_resolver=fake_resolver)
        result = service.resolve(
            origin_text="Colombo",
            destination_text="Kandy",
            duration_text="1 day",
            start_date="2026-06-12",
        )
        self.assertEqual(result.trip_days, 1)
        self.assertEqual(result.trip_dates, ["2026-06-12"])
        self.assertEqual(result.origin_resolved.name, "Colombo")
        self.assertEqual(result.destination_resolved.name, "Kandy")

    def test_invalid_duration_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_trip_days("sometime soon")


if __name__ == "__main__":
    unittest.main()
