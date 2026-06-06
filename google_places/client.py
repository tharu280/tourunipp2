from __future__ import annotations

from typing import Any

import requests

from google_routes.client import get_api_key

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.googleMapsUri",
        "places.primaryType",
        "places.types",
        "places.rating",
        "places.userRatingCount",
    ]
)
PLACE_RESOLVE_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.types",
    ]
)


def search_nearby_places(
    *,
    latitude: float,
    longitude: float,
    included_types: list[str],
    radius_m: int,
    max_result_count: int,
    rank_preference: str = "POPULARITY",
    field_mask: str = DEFAULT_FIELD_MASK,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    if max_result_count <= 0:
        return []

    payload = {
        "includedTypes": included_types,
        "maxResultCount": max_result_count,
        "rankPreference": rank_preference,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": float(radius_m),
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": get_api_key(),
        "X-Goog-FieldMask": field_mask,
    }

    response = requests.post(
        PLACES_NEARBY_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("places", [])


def search_text_places(
    *,
    text_query: str,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_m: int | None = None,
    max_result_count: int,
    rank_preference: str = "RELEVANCE",
    field_mask: str = DEFAULT_FIELD_MASK,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    if max_result_count <= 0:
        return []

    payload = {
        "textQuery": text_query,
        "pageSize": max_result_count,
        "rankPreference": rank_preference,
    }
    if latitude is not None and longitude is not None and radius_m is not None:
        payload["locationBias"] = {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": float(radius_m),
            }
        }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": get_api_key(),
        "X-Goog-FieldMask": field_mask,
    }

    response = requests.post(
        PLACES_TEXT_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("places", [])


def resolve_place_query(
    *,
    query: str,
    latitude: float = 7.8731,
    longitude: float = 80.7718,
    radius_m: int = 300_000,
    timeout: int = 30,
) -> dict[str, Any]:
    geocoded = _resolve_with_geocoding(query=query, timeout=timeout)
    if geocoded is not None:
        return geocoded

    try:
        places = search_text_places(
            text_query=f"{query}, Sri Lanka",
            max_result_count=1,
            rank_preference="RELEVANCE",
            field_mask=PLACE_RESOLVE_FIELD_MASK,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not resolve '{query}' with Google Geocoding or Places text search."
        ) from exc
    if not places:
        raise RuntimeError(f"Could not resolve place query: {query}")

    place = places[0]
    location = place.get("location") or {}
    resolved_lat = location.get("latitude")
    resolved_lng = location.get("longitude")
    if resolved_lat is None or resolved_lng is None:
        raise RuntimeError(f"Resolved place is missing coordinates: {query}")

    return {
        "place_id": place.get("id"),
        "name": place.get("displayName", {}).get("text") or query,
        "formatted_address": place.get("formattedAddress") or query,
        "lat": float(resolved_lat),
        "lng": float(resolved_lng),
        "types": place.get("types", []),
    }


def _resolve_with_geocoding(
    *,
    query: str,
    timeout: int,
) -> dict[str, Any] | None:
    try:
        response = requests.get(
            GEOCODING_URL,
            params={
                "address": query,
                "components": "country:LK",
                "key": get_api_key(),
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return None

    if payload.get("status") != "OK":
        return None

    results = payload.get("results") or []
    if not results:
        return None

    result = results[0]
    geometry = result.get("geometry", {}).get("location", {})
    resolved_lat = geometry.get("lat")
    resolved_lng = geometry.get("lng")
    if resolved_lat is None or resolved_lng is None:
        return None

    address_components = result.get("address_components") or []
    types = []
    for component in address_components:
        types.extend(component.get("types", []))

    return {
        "place_id": result.get("place_id"),
        "name": (result.get("address_components") or [{}])[0].get("long_name") or query,
        "formatted_address": result.get("formatted_address") or query,
        "lat": float(resolved_lat),
        "lng": float(resolved_lng),
        "types": sorted(set(types)),
    }
