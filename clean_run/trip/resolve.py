from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, Field

from clean_run.integrations.google_places_client import resolve_place_query


class PlaceResolver(Protocol):
    def __call__(self, *, query: str) -> dict[str, Any]: ...


class ResolvedPlace(BaseModel):
    place_id: str | None = None
    name: str
    formatted_address: str
    lat: float
    lng: float
    types: list[str] = Field(default_factory=list)


class ResolvedTripContext(BaseModel):
    origin_text: str
    destination_text: str
    duration_text: str
    start_date: str
    trip_days: int
    trip_dates: list[str]
    origin_resolved: ResolvedPlace
    destination_resolved: ResolvedPlace


def parse_trip_days(duration_text: str) -> int:
    normalized = duration_text.strip().lower()
    day_match = re.search(r"(\d+)\s*day", normalized)
    if day_match:
        return max(int(day_match.group(1)), 1)

    week_match = re.search(r"(\d+)\s*week", normalized)
    if week_match:
        return max(int(week_match.group(1)) * 7, 1)

    number_match = re.search(r"\d+", normalized)
    if number_match:
        return max(int(number_match.group(0)), 1)

    raise ValueError(f"Could not understand duration: {duration_text}")


def build_trip_dates(start_date: str, trip_days: int) -> list[str]:
    start = date.fromisoformat(start_date)
    total_days = max(trip_days, 1)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(total_days)]


@dataclass
class ResolveTripService:
    place_resolver: PlaceResolver = resolve_place_query

    def resolve(
        self,
        *,
        origin_text: str,
        destination_text: str,
        duration_text: str,
        start_date: str,
    ) -> ResolvedTripContext:
        trip_days = parse_trip_days(duration_text)
        trip_dates = build_trip_dates(start_date, trip_days)
        origin_resolved = ResolvedPlace.model_validate(self.place_resolver(query=origin_text))
        destination_resolved = ResolvedPlace.model_validate(self.place_resolver(query=destination_text))
        return ResolvedTripContext(
            origin_text=origin_text,
            destination_text=destination_text,
            duration_text=duration_text,
            start_date=start_date,
            trip_days=trip_days,
            trip_dates=trip_dates,
            origin_resolved=origin_resolved,
            destination_resolved=destination_resolved,
        )
