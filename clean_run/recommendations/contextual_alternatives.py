"""Read-only attraction alternatives based on trip weather and crowd context."""

from __future__ import annotations

import math
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from clean_run.emotion.places import fetch_overpass_query
from clean_run.postprocess.daily_briefing import build_daily_briefings


DEFAULT_RADIUS_METERS = 5_000
MAX_RADIUS_METERS = 8_000
CACHE_TTL_SECONDS = 30 * 60

INDOOR_CATEGORIES = {
    "museum",
    "gallery",
    "arts_centre",
    "library",
    "cinema",
    "cafe",
    "covered_market",
    "shopping_mall",
}
QUIET_CATEGORIES = {
    "park",
    "garden",
    "nature_reserve",
    "library",
    "gallery",
    "museum",
    "cafe",
}

INTEREST_CATEGORIES: dict[str, set[str]] = {
    "nature": {"park", "garden", "nature_reserve", "viewpoint", "beach", "waterfall"},
    "culture": {"museum", "gallery", "arts_centre", "historic", "library"},
    "food": {"cafe", "covered_market"},
    "photography": {"viewpoint", "garden", "park", "historic", "beach", "waterfall"},
    "sports": {"park", "nature_reserve", "beach"},
    "wellness": {"park", "garden", "nature_reserve", "beach"},
    "arts": {"gallery", "arts_centre", "museum", "cinema"},
    "shopping": {"shopping_mall", "covered_market"},
}

CATEGORY_LABELS = {
    "museum": "Museum",
    "gallery": "Gallery",
    "arts_centre": "Arts centre",
    "library": "Library",
    "cinema": "Cinema",
    "cafe": "Cafe",
    "covered_market": "Covered market",
    "shopping_mall": "Shopping centre",
    "park": "Park",
    "garden": "Garden",
    "nature_reserve": "Nature reserve",
    "viewpoint": "Viewpoint",
    "beach": "Beach",
    "waterfall": "Waterfall",
    "historic": "Historic place",
    "attraction": "Visitor attraction",
}

_CACHE: dict[tuple[float, float, int], tuple[float, list[dict[str, Any]]]] = {}
_CACHE_LOCK = threading.Lock()


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _level(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    return "unknown"


def _normalized_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _place_name(value: dict[str, Any]) -> str:
    return str(value.get("display_name") or value.get("name") or value.get("title") or "Attraction").strip()


def _coordinates(value: dict[str, Any]) -> tuple[float, float] | None:
    nested = value.get("location") if isinstance(value.get("location"), dict) else {}
    latitude = value.get("lat", value.get("latitude", nested.get("lat", nested.get("latitude"))))
    longitude = value.get(
        "lng",
        value.get("lon", value.get("longitude", nested.get("lng", nested.get("longitude")))),
    )
    latitude_value = _number(latitude)
    longitude_value = _number(longitude)
    if latitude_value is None or longitude_value is None:
        return None
    if not -90 <= latitude_value <= 90 or not -180 <= longitude_value <= 180:
        return None
    return latitude_value, longitude_value


def _selected_attractions(segment: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("gemini_selected_attractions", "selected_attractions", "top_attractions"):
        values = segment.get(key)
        if isinstance(values, list) and values:
            return [item for item in values if isinstance(item, dict)]
    return []


def _segments(plan: dict[str, Any]) -> list[dict[str, Any]]:
    recommended = plan.get("recommended_route") or {}
    values = recommended.get("segments") or (plan.get("route_data") or {}).get("segments") or []
    return [item for item in values if isinstance(item, dict)]


def _briefing_index(plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    briefings = plan.get("daily_briefings") or build_daily_briefings(plan)
    return {
        int(item.get("day") or index): item
        for index, item in enumerate(briefings, start=1)
        if isinstance(item, dict)
    }


def _attraction_context(
    attraction: dict[str, Any],
    briefing: dict[str, Any],
) -> dict[str, Any]:
    name = _place_name(attraction)
    keys = {
        _normalized_name(attraction.get("place_id")),
        _normalized_name(attraction.get("id")),
        _normalized_name(name),
    } - {""}
    for item in briefing.get("attractions") or []:
        item_keys = {
            _normalized_name(item.get("place_id")),
            _normalized_name(item.get("name")),
        } - {""}
        if keys & item_keys:
            return item
    return {
        "name": name,
        "crowd": briefing.get("crowd") or {},
        "weather_suitability": {},
    }


def _fallback_trigger(
    crowd: dict[str, Any],
    weather: dict[str, Any],
    *,
    force: bool,
) -> dict[str, Any]:
    crowd_level = _level(crowd.get("level") or crowd.get("risk_level"))
    weather_level = _level(weather.get("risk_level"))
    rain_probability = _number(weather.get("rain_probability_pct")) or 0
    reasons: list[str] = []

    if crowd_level == "high":
        reasons.append("The planned attraction has high estimated visitor pressure.")
    if weather_level == "high":
        reasons.append("The day has high weather disruption risk.")
    elif rain_probability >= 60:
        reasons.append(f"Rain probability is {rain_probability:.0f}%.")
    if crowd_level in {"medium", "high"} and weather_level in {"medium", "high"}:
        reasons.append("Crowd and weather conditions may combine to reduce comfort.")
    if force and not reasons:
        reasons.append("Alternatives were explicitly requested.")

    needed = bool(
        force
        or crowd_level == "high"
        or weather_level == "high"
        or rain_probability >= 60
        or (crowd_level in {"medium", "high"} and weather_level == "medium")
    )
    risk_level = "high" if "high" in {crowd_level, weather_level} else "medium" if needed else "low"
    return {
        "fallback_needed": needed,
        "risk_level": risk_level,
        "crowd": {
            "level": crowd_level,
            "score": _number(crowd.get("score")),
            "source": crowd.get("source") or "session_crowd_intelligence",
        },
        "weather": {
            "level": weather_level,
            "condition": weather.get("condition"),
            "rain_probability_pct": _number(weather.get("rain_probability_pct")),
            "rainfall_mm": _number(weather.get("rainfall_mm")),
        },
        "reasons": reasons,
    }


def _bbox(latitude: float, longitude: float, radius_meters: int) -> str:
    radius_km = radius_meters / 1000
    latitude_delta = radius_km / 111.32
    longitude_delta = radius_km / (111.32 * max(math.cos(math.radians(latitude)), 0.01))
    return ",".join(
        f"{value:.6f}"
        for value in (
            latitude - latitude_delta,
            longitude - longitude_delta,
            latitude + latitude_delta,
            longitude + longitude_delta,
        )
    )


def build_alternative_query(latitude: float, longitude: float, radius_meters: int) -> str:
    bbox = _bbox(latitude, longitude, radius_meters)
    selectors = [
        f'nwr["tourism"~"^(museum|gallery|viewpoint|attraction)$"]["name"]({bbox})',
        f'nwr["amenity"~"^(arts_centre|library|cinema|cafe|marketplace)$"]["name"]({bbox})',
        f'nwr["leisure"~"^(park|garden|nature_reserve)$"]["name"]({bbox})',
        f'nwr["natural"~"^(beach|waterfall)$"]["name"]({bbox})',
        f'nwr["historic"]["name"]({bbox})',
        f'nwr["shop"~"^(mall|department_store)$"]["name"]({bbox})',
    ]
    return "[out:json][timeout:25];(" + ";".join(selectors) + ";);out center tags 250;"


def _cached_overpass(latitude: float, longitude: float, radius_meters: int) -> list[dict[str, Any]]:
    key = (round(latitude, 4), round(longitude, 4), radius_meters)
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
    elements = fetch_overpass_query(build_alternative_query(latitude, longitude, radius_meters))
    with _CACHE_LOCK:
        _CACHE[key] = (now, elements)
    return elements


def _element_coordinates(element: dict[str, Any]) -> tuple[float, float] | None:
    center = element.get("center") if isinstance(element.get("center"), dict) else {}
    return _coordinates(
        {
            "latitude": element.get("lat", center.get("lat")),
            "longitude": element.get("lon", center.get("lon")),
        }
    )


def _category(tags: dict[str, Any]) -> str | None:
    tourism = tags.get("tourism")
    amenity = tags.get("amenity")
    leisure = tags.get("leisure")
    natural = tags.get("natural")
    shop = tags.get("shop")
    if tourism in {"museum", "gallery", "viewpoint", "attraction"}:
        return str(tourism)
    if amenity in {"arts_centre", "library", "cinema", "cafe"}:
        return str(amenity)
    if amenity == "marketplace":
        return "covered_market" if tags.get("covered") == "yes" or tags.get("indoor") == "yes" else None
    if leisure in {"park", "garden", "nature_reserve"}:
        return str(leisure)
    if natural in {"beach", "waterfall"}:
        return str(natural)
    if tags.get("historic"):
        return "historic"
    if shop in {"mall", "department_store"}:
        return "shopping_mall"
    return None


def _distance_km(origin_lat: float, origin_lng: float, latitude: float, longitude: float) -> float:
    earth_radius = 6371.0088
    lat1 = math.radians(origin_lat)
    lat2 = math.radians(latitude)
    delta_lat = lat2 - lat1
    delta_lng = math.radians(longitude - origin_lng)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    return earth_radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _interest_matches(category: str, interests: list[str]) -> list[str]:
    return [
        interest
        for interest in interests
        if category in INTEREST_CATEGORIES.get(interest.casefold(), set())
    ]


def _score_candidate(
    category: str,
    tags: dict[str, Any],
    distance_km: float,
    radius_meters: int,
    trigger: dict[str, Any],
    interests: list[str],
) -> tuple[float, dict[str, float], list[str], list[str], list[str]]:
    weather = trigger["weather"]
    crowd = trigger["crowd"]
    wet_weather = (
        weather["level"] in {"medium", "high"}
        or (weather.get("rain_probability_pct") or 0) >= 40
    )
    if wet_weather:
        weather_score = 35 if category in INDOOR_CATEGORIES else 8
    else:
        weather_score = 35 if category not in INDOOR_CATEGORIES else 25

    crowd_score = 20 if category in QUIET_CATEGORIES else 10
    distance_score = max(0.0, 20 * (1 - distance_km / (radius_meters / 1000)))
    matches = _interest_matches(category, interests)
    interest_score = 15 if matches else (7 if not interests else 0)
    metadata_fields = ("opening_hours", "website", "wikidata", "wikipedia", "addr:street")
    metadata_score = min(10, 2 + sum(2 for field in metadata_fields if tags.get(field)))
    breakdown = {
        "weather_suitability": round(weather_score, 1),
        "crowd_relief_proxy": round(crowd_score, 1),
        "distance": round(distance_score, 1),
        "interest_match": round(interest_score, 1),
        "metadata_quality": round(metadata_score, 1),
    }
    reasons: list[str] = []
    if wet_weather and category in INDOOR_CATEGORIES:
        reasons.append("Sheltered or indoor option for the forecast conditions.")
    elif not wet_weather and category not in INDOOR_CATEGORIES:
        reasons.append("Outdoor option suited to manageable weather.")
    if crowd["level"] == "high" and category in QUIET_CATEGORIES:
        reasons.append("Place type may offer a lower-pressure alternative to a major attraction.")
    if matches:
        reasons.append(f"Matches your interest in {', '.join(matches)}.")
    reasons.append(f"Located about {distance_km:.1f} km away in a straight line.")
    caveats = ["Overpass does not provide live crowd levels or reviews."]
    if not tags.get("opening_hours"):
        caveats.append("Opening hours are not available from OpenStreetMap; verify before visiting.")
    return sum(breakdown.values()), breakdown, reasons, caveats, matches


def _rank_candidates(
    elements: list[dict[str, Any]],
    latitude: float,
    longitude: float,
    radius_meters: int,
    trigger: dict[str, Any],
    interests: list[str],
    excluded_names: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for element in elements:
        tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
        name = str(tags.get("name") or "").strip()
        normalized = _normalized_name(name)
        coordinates = _element_coordinates(element)
        category = _category(tags)
        if not normalized or normalized in excluded_names or normalized in seen_names:
            continue
        if not coordinates or not category:
            continue
        place_latitude, place_longitude = coordinates
        distance = _distance_km(latitude, longitude, place_latitude, place_longitude)
        if distance > radius_meters / 1000:
            continue
        seen_names.add(normalized)
        score, breakdown, reasons, caveats, matches = _score_candidate(
            category,
            tags,
            distance,
            radius_meters,
            trigger,
            interests,
        )
        ranked.append(
            {
                "osm_type": element.get("type"),
                "osm_id": element.get("id"),
                "name": name,
                "category": category,
                "category_label": CATEGORY_LABELS[category],
                "latitude": place_latitude,
                "longitude": place_longitude,
                "distance_km": round(distance, 1),
                "distance_method": "straight_line",
                "map_url": (
                    f"https://www.openstreetmap.org/?mlat={place_latitude}&mlon={place_longitude}"
                    f"#map=16/{place_latitude}/{place_longitude}"
                ),
                "opening_hours": tags.get("opening_hours"),
                "opening_hours_confidence": "provided_by_osm" if tags.get("opening_hours") else "unknown",
                "interest_matches": matches,
                "score": round(score, 1),
                "score_breakdown": breakdown,
                "why_recommended": reasons,
                "caveats": caveats,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["distance_km"], item["name"]))
    return ranked[:limit]


def _guidance(name: str, trigger: dict[str, Any], alternatives: list[dict[str, Any]]) -> str:
    conditions: list[str] = []
    if trigger["crowd"]["level"] in {"medium", "high"}:
        conditions.append(f"{trigger['crowd']['level']} visitor pressure")
    if trigger["weather"]["level"] in {"medium", "high"}:
        conditions.append(f"{trigger['weather']['level']} weather risk")
    condition_text = " and ".join(conditions) or "current conditions"
    if not alternatives:
        return f"{name} may be less comfortable due to {condition_text}; no verified nearby alternative was found."
    top = alternatives[0]
    return (
        f"{name} may be less comfortable due to {condition_text}. "
        f"Consider {top['name']} first, then return when conditions improve."
    )


def build_contextual_alternatives(
    session_document: dict[str, Any],
    *,
    day: int | None = None,
    attraction_id: str | None = None,
    interests: list[str] | None = None,
    radius_meters: int = DEFAULT_RADIUS_METERS,
    limit_per_attraction: int = 3,
    max_attractions: int = 6,
    force: bool = False,
) -> dict[str, Any]:
    """Return temporary alternatives without mutating the session document."""
    plan = session_document.get("plan") if isinstance(session_document.get("plan"), dict) else session_document
    radius = max(1_000, min(int(radius_meters), MAX_RADIUS_METERS))
    limit = max(1, min(int(limit_per_attraction), 5))
    active_interests = [
        str(value).strip().title()
        for value in interests or []
        if str(value).strip().casefold() in INTEREST_CATEGORIES
    ]
    segments = _segments(plan)
    briefings = _briefing_index(plan)
    excluded_names = {
        _normalized_name(_place_name(attraction))
        for segment in segments
        for attraction in _selected_attractions(segment)
    }
    groups: list[dict[str, Any]] = []
    evaluated = 0

    for index, segment in enumerate(segments, start=1):
        segment_day = int(segment.get("day") or index)
        if day is not None and segment_day != day:
            continue
        briefing = briefings.get(segment_day, {})
        weather = briefing.get("weather") or {}
        for attraction in _selected_attractions(segment):
            identity = str(attraction.get("place_id") or attraction.get("id") or "")
            if attraction_id and attraction_id not in {identity, _place_name(attraction)}:
                continue
            context = _attraction_context(attraction, briefing)
            trigger = _fallback_trigger(context.get("crowd") or {}, weather, force=force)
            if not trigger["fallback_needed"]:
                continue
            if evaluated >= max_attractions:
                break
            evaluated += 1
            name = _place_name(attraction)
            coordinates = _coordinates(attraction)
            group: dict[str, Any] = {
                "day": segment_day,
                "date": briefing.get("date"),
                "original_attraction": {
                    "place_id": attraction.get("place_id") or attraction.get("id"),
                    "name": name,
                    "latitude": coordinates[0] if coordinates else None,
                    "longitude": coordinates[1] if coordinates else None,
                },
                "trigger": trigger,
                "alternatives": [],
                "status": "available",
                "error": None,
            }
            if coordinates is None:
                group["status"] = "unavailable"
                group["error"] = "The planned attraction does not have coordinates."
            else:
                try:
                    elements = _cached_overpass(coordinates[0], coordinates[1], radius)
                    group["alternatives"] = _rank_candidates(
                        elements,
                        coordinates[0],
                        coordinates[1],
                        radius,
                        trigger,
                        active_interests,
                        excluded_names,
                        limit,
                    )
                except (RuntimeError, OSError) as exc:
                    group["status"] = "unavailable"
                    group["error"] = f"Nearby places are temporarily unavailable ({type(exc).__name__})."
            group["guidance"] = _guidance(name, trigger, group["alternatives"])
            groups.append(group)

    if groups and all(group["status"] == "unavailable" for group in groups):
        status = "unavailable"
    elif groups and any(group["status"] == "unavailable" for group in groups):
        status = "partial"
    elif groups:
        status = "available"
    else:
        status = "not_needed"

    return {
        "session_id": session_document.get("session_id") or plan.get("session_id"),
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "temporary": True,
        "persisted": False,
        "filters": {
            "day": day,
            "attraction_id": attraction_id,
            "interests": active_interests,
            "radius_meters": radius,
        },
        "sources": {
            "places": "OpenStreetMap Overpass",
            "weather": "saved trip weather intelligence",
            "crowd": "saved SLTDA/Wikipedia trip pressure intelligence",
        },
        "recommendation_groups": groups,
        "message": (
            "No fallback is currently justified by the selected attraction conditions."
            if not groups
            else None
        ),
        "limitations": [
            "Alternatives are optional and do not modify the itinerary.",
            "Overpass does not provide live crowd levels, ratings, or guaranteed opening status.",
            "Distances are straight-line estimates until a routing provider verifies travel time.",
        ],
    }
