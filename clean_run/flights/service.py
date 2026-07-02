from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from clean_run.integrations.flight_client import (
    COLOMBO_IATA,
    DEFAULT_CURRENCY,
    FlightSearchError,
    TravelPayoutsFlightClient,
    build_aviasales_search_link,
)


COMMON_ORIGIN_OPTIONS = [
    ("1", "MAA", "Chennai"),
    ("2", "BLR", "Bengaluru"),
    ("3", "HYD", "Hyderabad"),
    ("4", "DEL", "Delhi"),
    ("5", "BOM", "Mumbai"),
    ("6", "DXB", "Dubai"),
    ("7", "SIN", "Singapore"),
    ("8", "KUL", "Kuala Lumpur"),
    ("9", "BKK", "Bangkok"),
    ("10", "Custom", "Custom"),
]

CABIN_CLASS_OPTIONS = [
    ("1", "economy", "Economy"),
    ("2", "premium_economy", "Premium Economy"),
    ("3", "business", "Business"),
    ("4", "first", "First"),
]


@dataclass
class FlightSearchPreferences:
    origin: str
    departure_date: str
    search_mode: str = "single_day"
    passengers: int = 1
    cabin_class: str = "economy"
    total_budget_lkr: float | None = None
    currency: str = DEFAULT_CURRENCY
    destination: str = COLOMBO_IATA


class FlightSearchService:
    def __init__(self, client: TravelPayoutsFlightClient | None = None) -> None:
        self.client = client or TravelPayoutsFlightClient()

    @staticmethod
    def _effective_departure_date(flight: dict[str, Any], fallback_date: str) -> str:
        departure_at = str(flight.get("departure_at") or "")
        if len(departure_at) >= 10:
            candidate = departure_at[:10]
            try:
                # Validate before trusting provider text.
                from datetime import date

                date.fromisoformat(candidate)
                return candidate
            except ValueError:
                pass
        return fallback_date

    def _ensure_booking_links(
        self,
        results: list[dict[str, Any]],
        preferences: FlightSearchPreferences,
    ) -> list[dict[str, Any]]:
        linked: list[dict[str, Any]] = []
        for item in results:
            flight = dict(item)
            if flight.get("booking_link"):
                flight["booking_link_source"] = flight.get("booking_link_source") or "provider_direct"
                linked.append(flight)
                continue

            link_date = self._effective_departure_date(flight, preferences.departure_date)
            flight["booking_link"] = build_aviasales_search_link(
                origin=str(flight.get("origin") or preferences.origin),
                destination=str(flight.get("destination") or preferences.destination),
                departure_date=link_date,
                passengers=preferences.passengers,
                cabin_class=preferences.cabin_class,
            )
            flight["booking_link_source"] = "generated_aviasales_search"
            flight["booking_link_note"] = (
                "Provider did not return a direct ticket link, so this opens a matching Aviasales search page."
            )
            linked.append(flight)
        return linked

    def search(self, preferences: FlightSearchPreferences) -> dict[str, Any]:
        requested_search_mode = preferences.search_mode
        fallback_applied = False

        if preferences.search_mode == "week":
            results = self.client.search_week_window(
                origin=preferences.origin,
                departure_date=preferences.departure_date,
                currency=preferences.currency,
            )
            effective_search_mode = "week"
        else:
            results = self.client.search_exact_date(
                origin=preferences.origin,
                departure_date=preferences.departure_date,
                currency=preferences.currency,
            )
            effective_search_mode = "single_day"
            if not results:
                results = self.client.search_week_window(
                    origin=preferences.origin,
                    departure_date=preferences.departure_date,
                    currency=preferences.currency,
                )
                effective_search_mode = "week"
                fallback_applied = True

        results = self._ensure_booking_links(results, preferences)
        cheapest = results[0] if results else None

        return {
            "origin": preferences.origin.upper(),
            "destination": preferences.destination,
            "departure_date": preferences.departure_date,
            "search_mode": effective_search_mode,
            "requested_search_mode": requested_search_mode,
            "fallback_applied": fallback_applied,
            "passengers": preferences.passengers,
            "cabin_class": preferences.cabin_class,
            "currency": preferences.currency,
            "total_budget_lkr": preferences.total_budget_lkr,
            "results_count": len(results),
            "results": results[:12],
            "cheapest_result": cheapest,
            "preferences": asdict(preferences),
        }


def format_flights_table(flights: list[dict[str, Any]]) -> str:
    if not flights:
        return "No flights found for the selected route and date."

    header = (
        f"{'Price':<10} {'Airline':<10} {'Stops':<5} "
        f"{'Departure':<22} {'Link':<40}"
    )
    lines = [header, "-" * len(header)]
    for flight in flights[:10]:
        lines.append(
            f"{str(flight.get('price', 'N/A')):<10} "
            f"{str(flight.get('airline', 'N/A')):<10} "
            f"{str(flight.get('transfers', 'N/A')):<5} "
            f"{str(flight.get('departure_at', 'N/A')):<22} "
            f"{str(flight.get('booking_link', 'N/A')):<40}"
        )
    return "\n".join(lines)


__all__ = [
    "CABIN_CLASS_OPTIONS",
    "COLOMBO_IATA",
    "COMMON_ORIGIN_OPTIONS",
    "FlightSearchError",
    "FlightSearchPreferences",
    "FlightSearchService",
    "format_flights_table",
]
