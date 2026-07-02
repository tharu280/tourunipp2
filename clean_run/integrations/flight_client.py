from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


TRAVELPAYOUTS_BASE_URL = "https://api.travelpayouts.com"
BOOKING_BASE_URL = "https://www.aviasales.com"
DEFAULT_CURRENCY = "USD"
COLOMBO_IATA = "CMB"
CABIN_CLASS_TO_AVIASALES_TRIP_CLASS = {
    "economy": "0",
    "premium_economy": "1",
    "business": "2",
    "first": "3",
}
CLEAN_RUN_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(CLEAN_RUN_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env")


class FlightSearchError(RuntimeError):
    """Raised when the flight provider cannot satisfy the request."""


def build_aviasales_search_link(
    *,
    origin: str,
    destination: str = COLOMBO_IATA,
    departure_date: str,
    passengers: int = 1,
    cabin_class: str = "economy",
) -> str:
    depart = date.fromisoformat(departure_date)
    route_token = f"{origin.upper()}{depart:%d%m}{destination.upper()}1"
    params = {
        "adults": max(int(passengers or 1), 1),
        "children": 0,
        "infants": 0,
        "trip_class": CABIN_CLASS_TO_AVIASALES_TRIP_CLASS.get(cabin_class, "0"),
    }
    marker = os.getenv("TRAVELPAYOUTS_MARKER") or os.getenv("AVIASALES_MARKER")
    if marker:
        params["marker"] = marker
    return f"{BOOKING_BASE_URL}/search/{route_token}?{urlencode(params)}"


@dataclass
class TravelPayoutsFlightClient:
    request_get: Callable[..., Any] = requests.get

    def _api_token(self) -> str:
        token = (
            os.getenv("FLIGHT_API_TOKEN")
            or os.getenv("API_TOKEN")
            or ""
        ).strip().strip('"').strip("'")
        if not token:
            raise FlightSearchError("Missing FLIGHT_API_TOKEN in clean_run/.env or project environment.")
        return token

    def _request(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = self.request_get(
            f"{TRAVELPAYOUTS_BASE_URL}{path}",
            params=params,
            headers={"X-Access-Token": self._api_token(), "Accept": "application/json"},
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            raise FlightSearchError(payload.get("error") or "Flight provider returned an error.")
        return payload

    @staticmethod
    def _normalize_link(raw_link: Any) -> str | None:
        if not raw_link:
            return None
        link = str(raw_link).strip()
        if not link:
            return None
        if link.startswith("http://") or link.startswith("https://"):
            return link
        if link.startswith("/"):
            return f"{BOOKING_BASE_URL}{link}"
        return f"{BOOKING_BASE_URL}/{link}"

    @staticmethod
    def _parse_transfers(key: str, raw: dict[str, Any]) -> int:
        transfers = raw.get("transfers")
        if isinstance(transfers, int):
            return transfers
        try:
            return int(key)
        except (TypeError, ValueError):
            return 0

    def _normalize_v1_results(
        self,
        payload: dict[str, Any],
        *,
        destination: str,
        search_mode: str,
    ) -> list[dict[str, Any]]:
        data = payload.get("data", {})
        bucket = data.get(destination, {}) if isinstance(data, dict) else {}
        results: list[dict[str, Any]] = []

        items = bucket.items() if isinstance(bucket, dict) else []
        for key, raw in items:
            if not isinstance(raw, dict):
                continue
            results.append(
                {
                    "provider": "travelpayouts",
                    "search_mode": search_mode,
                    "origin": raw.get("origin"),
                    "destination": raw.get("destination", destination),
                    "price": raw.get("price"),
                    "currency": raw.get("currency", DEFAULT_CURRENCY),
                    "airline": raw.get("airline"),
                    "flight_number": raw.get("flight_number"),
                    "transfers": self._parse_transfers(str(key), raw),
                    "departure_at": raw.get("departure_at"),
                    "return_at": raw.get("return_at"),
                    "expires_at": raw.get("expires_at"),
                    "booking_link": self._normalize_link(raw.get("link")),
                    "booking_link_source": "provider_direct" if raw.get("link") else None,
                }
            )

        return sorted(
            [item for item in results if item.get("price") is not None],
            key=lambda item: item["price"],
        )

    def _normalize_v2_results(
        self,
        payload: dict[str, Any],
        *,
        origin: str,
        destination: str,
        search_mode: str,
    ) -> list[dict[str, Any]]:
        data = payload.get("data", [])
        results: list[dict[str, Any]] = []
        if not isinstance(data, list):
            return results

        for raw in data:
            if not isinstance(raw, dict):
                continue
            results.append(
                {
                    "provider": "travelpayouts",
                    "search_mode": search_mode,
                    "origin": raw.get("origin", origin),
                    "destination": raw.get("destination", destination),
                    "price": raw.get("value") or raw.get("price"),
                    "currency": raw.get("currency", DEFAULT_CURRENCY),
                    "airline": raw.get("airline"),
                    "flight_number": raw.get("flight_number"),
                    "transfers": raw.get("transfers", 0),
                    "departure_at": raw.get("departure_at"),
                    "return_at": raw.get("return_at"),
                    "expires_at": raw.get("expires_at"),
                    "booking_link": self._normalize_link(raw.get("link")),
                    "booking_link_source": "provider_direct" if raw.get("link") else None,
                }
            )

        return sorted(
            [item for item in results if item.get("price") is not None],
            key=lambda item: item["price"],
        )

    def search_exact_date(
        self,
        *,
        origin: str,
        departure_date: str,
        currency: str = DEFAULT_CURRENCY,
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "/v1/prices/cheap",
            params={
                "origin": origin.upper(),
                "destination": COLOMBO_IATA,
                "depart_date": departure_date,
                "currency": currency,
            },
        )
        return self._normalize_v1_results(
            payload,
            destination=COLOMBO_IATA,
            search_mode="single_day",
        )

    def search_week_window(
        self,
        *,
        origin: str,
        departure_date: str,
        currency: str = DEFAULT_CURRENCY,
    ) -> list[dict[str, Any]]:
        depart = date.fromisoformat(departure_date)
        return_date = depart + timedelta(days=7)
        payload = self._request(
            "/v2/prices/week-matrix",
            params={
                "origin": origin.upper(),
                "destination": COLOMBO_IATA,
                "depart_date": departure_date,
                "return_date": return_date.isoformat(),
                "currency": currency.lower(),
                "show_to_affiliates": "true",
            },
        )
        return self._normalize_v2_results(
            payload,
            origin=origin.upper(),
            destination=COLOMBO_IATA,
            search_mode="week",
        )
