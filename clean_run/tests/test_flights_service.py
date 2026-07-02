from __future__ import annotations

import unittest

from clean_run.flights.service import FlightSearchPreferences, FlightSearchService
from clean_run.integrations.flight_client import TravelPayoutsFlightClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class FlightSearchServiceTests(unittest.TestCase):
    def test_single_day_results_are_returned_without_fallback(self) -> None:
        def fake_get(url, *, params, headers, timeout):
            self.assertIn("/v1/prices/cheap", url)
            return FakeResponse(
                {
                    "data": {
                        "CMB": {
                            "0": {
                                "origin": "DXB",
                                "destination": "CMB",
                                "price": 220,
                                "currency": "USD",
                                "airline": "EK",
                                "departure_at": "2026-06-25T10:00:00+04:00",
                                "link": "/search/booking-1",
                            }
                        }
                    }
                }
            )

        client = TravelPayoutsFlightClient(request_get=fake_get)
        client._api_token = lambda: "token"
        service = FlightSearchService(client=client)

        payload = service.search(
            FlightSearchPreferences(
                origin="DXB",
                departure_date="2026-06-25",
                search_mode="single_day",
            )
        )

        self.assertEqual(payload["search_mode"], "single_day")
        self.assertFalse(payload["fallback_applied"])
        self.assertEqual(payload["results_count"], 1)
        self.assertEqual(payload["results"][0]["booking_link"], "https://www.aviasales.com/search/booking-1")
        self.assertEqual(payload["results"][0]["booking_link_source"], "provider_direct")

    def test_empty_single_day_results_fall_back_to_week_search(self) -> None:
        calls: list[str] = []

        def fake_get(url, *, params, headers, timeout):
            calls.append(url)
            if "/v1/prices/cheap" in url:
                return FakeResponse({"data": {"CMB": {}}})
            return FakeResponse(
                {
                    "data": [
                        {
                            "origin": "NRT",
                            "destination": "CMB",
                            "value": 540,
                            "currency": "USD",
                            "airline": "UL",
                            "departure_at": "2026-07-01T09:00:00+09:00",
                            "transfers": 1,
                            "link": "week-booking-1",
                        }
                    ]
                }
            )

        client = TravelPayoutsFlightClient(request_get=fake_get)
        client._api_token = lambda: "token"
        service = FlightSearchService(client=client)

        payload = service.search(
            FlightSearchPreferences(
                origin="NRT",
                departure_date="2026-07-01",
                search_mode="single_day",
                cabin_class="business",
                total_budget_lkr=300000,
            )
        )

        self.assertEqual(payload["search_mode"], "week")
        self.assertTrue(payload["fallback_applied"])
        self.assertEqual(payload["results_count"], 1)
        self.assertEqual(payload["results"][0]["booking_link"], "https://www.aviasales.com/week-booking-1")
        self.assertEqual(payload["results"][0]["booking_link_source"], "provider_direct")
        self.assertEqual(payload["cheapest_result"]["price"], 540)
        self.assertEqual(len(calls), 2)

    def test_week_fallback_generates_booking_search_link_when_provider_link_is_missing(self) -> None:
        def fake_get(url, *, params, headers, timeout):
            if "/v1/prices/cheap" in url:
                return FakeResponse({"data": {"CMB": {}}})
            return FakeResponse(
                {
                    "data": [
                        {
                            "origin": "DXB",
                            "destination": "CMB",
                            "value": 297,
                            "currency": "USD",
                            "transfers": 0,
                            "departure_at": "2026-07-20T06:30:00+04:00",
                        }
                    ]
                }
            )

        client = TravelPayoutsFlightClient(request_get=fake_get)
        client._api_token = lambda: "token"
        service = FlightSearchService(client=client)

        payload = service.search(
            FlightSearchPreferences(
                origin="DXB",
                departure_date="2026-07-20",
                search_mode="single_day",
                passengers=2,
                cabin_class="business",
            )
        )

        link = payload["results"][0]["booking_link"]
        self.assertEqual(payload["results"][0]["booking_link_source"], "generated_aviasales_search")
        self.assertIn("https://www.aviasales.com/search/DXB2007CMB1", link)
        self.assertIn("adults=2", link)
        self.assertIn("trip_class=2", link)
        self.assertEqual(payload["cheapest_result"]["booking_link"], link)


if __name__ == "__main__":
    unittest.main()
