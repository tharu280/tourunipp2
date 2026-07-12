"""Deterministic mood and hobby based nearby-place recommendations."""

from __future__ import annotations

import json
import math
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


SEARCH_RADIUS_METERS = 3_000
OVERPASS_URLS = (
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
USER_AGENT = "TourUni-MoodTips/1.0 (university MVP)"

MOOD_PROFILES: dict[str, dict[str, Any]] = {
    "anger": {
        "preferred": ["park", "garden", "nature_reserve", "viewpoint", "waterfall", "cafe"],
        "intro": "A quieter outdoor setting may help you cool down and reset.",
    },
    "sad": {
        "preferred": ["garden", "park", "viewpoint", "waterfall", "cafe", "museum", "culture"],
        "intro": "A gentle, pleasant place may offer a small change of pace.",
    },
    "neutral": {
        "preferred": ["museum", "attraction", "historic", "garden", "viewpoint", "cafe", "culture"],
        "intro": "A light nearby activity could add some interest to your day.",
    },
    "happy": {
        "preferred": ["attraction", "viewpoint", "museum", "historic", "culture", "garden", "park"],
        "intro": "You seem upbeat, so these places can help you use that energy well.",
    },
    "surprise": {
        "preferred": ["park", "garden", "museum", "cafe", "viewpoint", "historic", "culture"],
        "intro": "A grounded but interesting stop may help you settle into the moment.",
    },
    "uncertain": {
        "preferred": ["park", "garden", "cafe", "museum", "viewpoint"],
        "intro": "Choose a low-pressure nearby stop and see what feels comfortable.",
    },
}

HOBBY_PROFILES: dict[str, list[str]] = {
    "Photography": ["viewpoint", "garden", "waterfall", "attraction", "historic"],
    "Nature": ["nature_reserve", "garden", "park", "waterfall", "viewpoint"],
    "Culture": ["museum", "historic", "attraction", "culture"],
    "Food": ["cafe", "restaurant"],
    "Sports": ["sport"],
    "Wellness": ["wellness", "garden", "park"],
    "Arts": ["museum", "culture"],
    "Shopping": ["shopping"],
}

CATEGORY_REASONS = {
    "park": "open green space for a calm walk",
    "garden": "a quiet landscaped setting",
    "nature_reserve": "a slower nature-focused break",
    "viewpoint": "fresh air and a change of perspective",
    "waterfall": "a refreshing natural environment",
    "cafe": "a comfortable place to pause and recharge",
    "museum": "a gentle indoor activity with something new to explore",
    "attraction": "an engaging local experience",
    "historic": "a meaningful cultural stop at an easy pace",
    "culture": "a creative local setting connected to arts or music",
    "restaurant": "a local food experience with time to recharge",
    "sport": "an active setting that can channel your energy",
    "wellness": "a slower wellbeing-focused break",
    "shopping": "a relaxed place to browse local finds",
}

CATEGORY_ACTIVITY_META = {
    "park": {"icon": "🌿", "activity_type": "Nature walk", "duration": "1–2 hrs", "best_time": "Morning"},
    "garden": {"icon": "🌺", "activity_type": "Garden escape", "duration": "1–2 hrs", "best_time": "Morning"},
    "nature_reserve": {"icon": "🦜", "activity_type": "Nature therapy", "duration": "2–3 hrs", "best_time": "Early morning"},
    "viewpoint": {"icon": "📸", "activity_type": "Scenic reset", "duration": "1–2 hrs", "best_time": "Late afternoon"},
    "waterfall": {"icon": "💧", "activity_type": "Nature therapy", "duration": "1–2 hrs", "best_time": "Morning"},
    "cafe": {"icon": "☕", "activity_type": "Slow break", "duration": "45–90 min", "best_time": "Flexible"},
    "museum": {"icon": "🏛️", "activity_type": "History & culture", "duration": "1–2 hrs", "best_time": "Late morning"},
    "attraction": {"icon": "✨", "activity_type": "Local experience", "duration": "1–2 hrs", "best_time": "Morning"},
    "historic": {"icon": "🏺", "activity_type": "Heritage discovery", "duration": "1–2 hrs", "best_time": "Morning"},
    "culture": {"icon": "🎶", "activity_type": "Arts & music", "duration": "1–2 hrs", "best_time": "Late afternoon"},
    "restaurant": {"icon": "🍜", "activity_type": "Food experience", "duration": "1–2 hrs", "best_time": "Lunch or dinner"},
    "sport": {"icon": "⚽", "activity_type": "Active break", "duration": "1–2 hrs", "best_time": "Late afternoon"},
    "wellness": {"icon": "🧘", "activity_type": "Wellness break", "duration": "1–2 hrs", "best_time": "Flexible"},
    "shopping": {"icon": "🛍️", "activity_type": "Local shopping", "duration": "1–2 hrs", "best_time": "Late morning"},
}

MOOD_PICK_META = {
    "anger": {"label": "Calm Pick", "headline": "Mood Recovery Activities", "mood_need": "a quieter pace and room to reset"},
    "sad": {"label": "Mood Booster", "headline": "Mood Recovery Activities", "mood_need": "a gentle change of scene without too much pressure"},
    "neutral": {"label": "Fresh Pick", "headline": "Smart Picks For You", "mood_need": "something engaging that adds interest to the day"},
    "happy": {"label": "Energy Match", "headline": "Smart Picks For You", "mood_need": "an activity that makes good use of your positive energy"},
    "surprise": {"label": "Grounding Pick", "headline": "Balanced Picks For You", "mood_need": "an interesting but grounded activity"},
    "uncertain": {"label": "Easy Pick", "headline": "Gentle Picks For You", "mood_need": "a flexible, low-pressure option"},
}


def _activity_copy(name: str, category: str, emotion: str, hobby_matches: list[str]) -> dict[str, Any]:
    activity = CATEGORY_ACTIVITY_META[category]
    mood = MOOD_PICK_META.get(emotion, MOOD_PICK_META["neutral"])
    why = f"This {activity['activity_type'].lower()} offers {mood['mood_need']}."
    if hobby_matches:
        why += f" It also matches your interest in {', '.join(hobby_matches)}."
    return {
        **activity,
        "recommendation_label": mood["label"],
        "description": f"Spend a little time at {name} for {CATEGORY_REASONS[category]}.",
        "why_for_you": why,
        "solo_friendly": True,
    }


def normalize_hobbies(hobbies: list[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    lookup = {name.casefold(): name for name in HOBBY_PROFILES}
    for value in hobbies or []:
        canonical = lookup.get(str(value).strip().casefold())
        if canonical and canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)
    return normalized


def _preferred_categories(emotion: str, hobbies: list[str]) -> set[str]:
    profile = MOOD_PROFILES.get(emotion, MOOD_PROFILES["neutral"])
    categories = set(profile["preferred"])
    for hobby in hobbies:
        categories.update(HOBBY_PROFILES[hobby])
    return categories


def build_overpass_query(
    latitude: float,
    longitude: float,
    emotion: str,
    hobbies: list[str] | None = None,
    radius_meters: int = SEARCH_RADIUS_METERS,
) -> str:
    """Build a bounded query; bounding boxes are faster on public mirrors."""
    radius_km = radius_meters / 1000
    latitude_delta = radius_km / 111.32
    longitude_delta = radius_km / (111.32 * max(math.cos(math.radians(latitude)), 0.01))
    bbox = ",".join(
        f"{value:.6f}"
        for value in (
            latitude - latitude_delta,
            longitude - longitude_delta,
            latitude + latitude_delta,
            longitude + longitude_delta,
        )
    )
    selected_hobbies = normalize_hobbies(hobbies)
    preferred = _preferred_categories(emotion, selected_hobbies)
    selectors: list[str] = []

    leisure = sorted(preferred & {"park", "garden", "nature_reserve"})
    tourism = sorted(preferred & {"attraction", "museum", "viewpoint"})
    natural = sorted(preferred & {"waterfall"})
    if leisure:
        selectors.append(f'nwr["leisure"~"^({"|".join(leisure)})$"]["name"]({bbox})')
    if tourism:
        selectors.append(f'nwr["tourism"~"^({"|".join(tourism)})$"]["name"]({bbox})')
    if natural:
        selectors.append(f'nwr["natural"~"^({"|".join(natural)})$"]["name"]({bbox})')
    if "cafe" in preferred:
        selectors.append(f'nwr["amenity"="cafe"]["name"]({bbox})')
    if "culture" in preferred:
        selectors.append(f'nwr["amenity"~"^(theatre|arts_centre|music_venue)$"]["name"]({bbox})')
    if "historic" in preferred:
        selectors.append(
            f'nwr["historic"~"^(monument|memorial|ruins|archaeological_site|castle)$"]["name"]({bbox})'
        )
    if "restaurant" in preferred:
        selectors.append(f'nwr["amenity"~"^(restaurant|fast_food)$"]["name"]({bbox})')
    if "sport" in preferred:
        selectors.append(f'nwr["leisure"~"^(sports_centre|stadium|pitch)$"]["name"]({bbox})')
    if "wellness" in preferred:
        selectors.append(f'nwr["leisure"~"^(fitness_centre|spa)$"]["name"]({bbox})')
    if "shopping" in preferred:
        selectors.append(f'nwr["shop"~"^(mall|department_store|gift|craft|clothes|books|jewelry|souvenir)$"]["name"]({bbox})')
    return "[out:json][timeout:25];(" + ";".join(selectors) + ";);out center tags 300;"


def fetch_overpass_places(
    latitude: float,
    longitude: float,
    emotion: str,
    hobbies: list[str] | None = None,
    radius_meters: int = SEARCH_RADIUS_METERS,
) -> list[dict[str, Any]]:
    query = build_overpass_query(latitude, longitude, emotion, hobbies, radius_meters)
    payload = urllib.parse.urlencode({"data": query}).encode()
    errors: list[str] = []
    for endpoint in OVERPASS_URLS:
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                elements = json.load(response).get("elements", [])
            if elements:
                return elements
            errors.append(f"{endpoint}: no places")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
            errors.append(f"{endpoint}: {exc}")
    raise RuntimeError("All Overpass mirrors failed. " + " | ".join(errors))


def _coordinates(element: dict[str, Any]) -> tuple[float, float] | None:
    center = element.get("center") or {}
    latitude = element.get("lat", center.get("lat"))
    longitude = element.get("lon", center.get("lon"))
    if latitude is None or longitude is None:
        return None
    return float(latitude), float(longitude)


def _category(tags: dict[str, str]) -> str | None:
    leisure = tags.get("leisure")
    tourism = tags.get("tourism")
    natural = tags.get("natural")
    amenity = tags.get("amenity")
    if leisure in {"park", "garden", "nature_reserve"}:
        return leisure
    if tourism in {"attraction", "museum", "viewpoint"}:
        return tourism
    if natural == "waterfall":
        return "waterfall"
    if amenity == "cafe":
        return "cafe"
    if amenity in {"restaurant", "fast_food"}:
        return "restaurant"
    if amenity in {"theatre", "arts_centre", "music_venue"}:
        return "culture"
    if leisure in {"sports_centre", "stadium", "pitch"}:
        return "sport"
    if leisure in {"fitness_centre", "spa"}:
        return "wellness"
    if tags.get("shop") in {"mall", "department_store", "gift", "craft", "clothes", "books", "jewelry", "souvenir"}:
        return "shopping"
    if tags.get("historic"):
        return "historic"
    return None


def _distance_km(origin_lat: float, origin_lng: float, latitude: float, longitude: float) -> float:
    earth_radius_km = 6371.0088
    lat1 = math.radians(origin_lat)
    lat2 = math.radians(latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(longitude - origin_lng)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return earth_radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def rank_places(
    elements: list[dict[str, Any]],
    latitude: float,
    longitude: float,
    emotion: str,
    hobbies: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    profile = MOOD_PROFILES.get(emotion, MOOD_PROFILES["neutral"])
    preference_order = profile["preferred"]
    selected_hobbies = normalize_hobbies(hobbies)
    ranked: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for element in elements:
        tags = element.get("tags") or {}
        name = str(tags.get("name", "")).strip()
        coordinates = _coordinates(element)
        category = _category(tags)
        osm_key = (str(element.get("type", "")), int(element.get("id", 0)))
        if not name or not coordinates or not category or osm_key in seen:
            continue
        seen.add(osm_key)
        place_lat, place_lng = coordinates
        distance = _distance_km(latitude, longitude, place_lat, place_lng)
        preference_rank = preference_order.index(category) if category in preference_order else len(preference_order)
        hobby_matches = [hobby for hobby in selected_hobbies if category in HOBBY_PROFILES[hobby]]
        # An explicit hobby is a strong preference, while mood suitability
        # still determines ordering among equally relevant places.
        score = 100 - preference_rank * 12 + min(len(hobby_matches), 2) * 75 - min(distance, 20) * 2
        reason = CATEGORY_REASONS[category]
        if hobby_matches:
            reason += f" and matches {', '.join(hobby_matches)}"
        activity_copy = _activity_copy(name, category, emotion, hobby_matches)
        ranked.append(
            {
                "name": name,
                "category": category.replace("_", " ").title(),
                "distance_km": round(distance, 1),
                "reason": reason,
                "hobby_matches": hobby_matches,
                "interest_match": bool(hobby_matches),
                "latitude": place_lat,
                "longitude": place_lng,
                "map_url": f"https://www.openstreetmap.org/?mlat={place_lat}&mlon={place_lng}#map=16/{place_lat}/{place_lng}",
                "score": round(score, 2),
                **activity_copy,
            }
        )
    # When the user selected interests, matching places must lead the result.
    # Mood-only places remain useful fallbacks after exact interest matches.
    ranked.sort(
        key=lambda place: (
            0 if place["interest_match"] or not selected_hobbies else 1,
            -place["score"],
            place["distance_km"],
            place["name"],
        )
    )
    selected = ranked[:limit]
    for index, place in enumerate(selected):
        place["top_pick"] = index == 0
    return selected


def _trip_start(session_document: dict[str, Any]) -> dict[str, Any] | None:
    plan = session_document.get("plan") or {}
    origin = plan.get("origin_resolved") or {}
    latitude = origin.get("lat", origin.get("latitude"))
    longitude = origin.get("lng", origin.get("longitude"))
    if latitude is None or longitude is None:
        return None
    return {
        "name": origin.get("name") or origin.get("display_name") or "Trip start",
        "latitude": float(latitude),
        "longitude": float(longitude),
        "source": "trip_start",
    }


def build_nearby_emotion_tips(
    session_document: dict[str, Any],
    emotion: str,
    hobbies: list[str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    selected_hobbies = normalize_hobbies(hobbies)
    location = _trip_start(session_document)
    if location is None:
        return {
            "status": "unavailable",
            "location": None,
            "hobbies": selected_hobbies,
            "recommendations": [],
            "message": "The trip start location does not have coordinates.",
        }

    profile = MOOD_PROFILES.get(emotion, MOOD_PROFILES["neutral"])
    try:
        elements = fetch_overpass_places(
            location["latitude"], location["longitude"], emotion, selected_hobbies
        )
        recommendations = rank_places(
            elements,
            location["latitude"],
            location["longitude"],
            emotion,
            selected_hobbies,
            limit,
        )
    except (RuntimeError, OSError) as exc:
        return {
            "status": "unavailable",
            "location": location,
            "hobbies": selected_hobbies,
            "recommendations": [],
            "message": "Nearby places are temporarily unavailable. Your travel-readiness advice is still valid.",
            "error_type": type(exc).__name__,
        }

    return {
        "status": "available",
        "location": location,
        "hobbies": selected_hobbies,
        "summary": profile["intro"],
        "headline": MOOD_PICK_META.get(emotion, MOOD_PICK_META["neutral"])["headline"],
        "recommendations": recommendations,
        "message": None if recommendations else "No suitable named places were found within 3 km.",
        "disclaimer": "These are wellbeing-oriented activity suggestions, not medical advice.",
    }
