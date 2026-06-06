from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROUTES_API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
DEFAULT_FIELD_MASK = ",".join(
    [
        "routes.routeLabels",
        "routes.distanceMeters",
        "routes.duration",
        "routes.polyline.encodedPolyline",
        "routes.legs.distanceMeters",
        "routes.legs.duration",
        "routes.legs.polyline.encodedPolyline",
    ]
)


def load_env_file(env_path: str | Path) -> None:
    """Load simple KEY=VALUE pairs from a local .env file if present."""
    path = Path(env_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def get_api_key() -> str:
    candidate_env_files = [
        Path(".env"),
        Path(__file__).resolve().parent / ".env",
    ]
    for env_path in candidate_env_files:
        load_env_file(env_path)

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing GOOGLE_MAPS_API_KEY. Add it to your environment or .env file."
        )
    return api_key


def _latlng(latitude: float, longitude: float) -> dict[str, Any]:
    return {
        "location": {
            "latLng": {
                "latitude": latitude,
                "longitude": longitude,
            }
        }
    }


def compute_routes(
    *,
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    travel_mode: str = "DRIVE",
    routing_preference: str = "TRAFFIC_AWARE",
    compute_alternative_routes: bool = True,
    departure_time: str | None = None,
    extra_computations: list[str] | None = None,
    field_mask: str = DEFAULT_FIELD_MASK,
    timeout: int = 30,
) -> dict[str, Any]:
    api_key = get_api_key()

    payload = {
        "origin": _latlng(origin_lat, origin_lng),
        "destination": _latlng(destination_lat, destination_lng),
        "travelMode": travel_mode,
        "routingPreference": routing_preference,
        "computeAlternativeRoutes": compute_alternative_routes,
    }
    if departure_time:
        payload["departureTime"] = departure_time
    if extra_computations:
        payload["extraComputations"] = extra_computations
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
    }

    response = requests.post(
        ROUTES_API_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def build_route_profiles(
    *,
    response_payload: dict[str, Any],
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
) -> dict[str, Any]:
    routes = response_payload.get("routes", [])
    route_profiles = []

    for index, route in enumerate(routes, start=1):
        route_profiles.append(
            {
                "route_id": f"route_{index}",
                "route_labels": route.get("routeLabels", []),
                "distance_meters": route.get("distanceMeters"),
                "duration": route.get("duration"),
                "polyline": route.get("polyline", {}).get("encodedPolyline"),
                "legs": route.get("legs", []),
                "raw_route": route,
            }
        )

    return {
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "origin": {"lat": origin_lat, "lng": origin_lng},
        "destination": {"lat": destination_lat, "lng": destination_lng},
        "route_count": len(route_profiles),
        "routes": route_profiles,
    }


def save_route_profiles(
    route_profiles: dict[str, Any],
    *,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(route_profiles, indent=2), encoding="utf-8")
    return path
