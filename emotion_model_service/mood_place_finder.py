"""Classify a face image and suggest mood-supportive places near Kandy.

Usage:
    python mood_place_finder.py /path/to/photo.jpg

The emotion model runs locally. Only the hardcoded Kandy coordinates and an
OpenStreetMap query are sent to the public Overpass API; the image is not sent.
"""

from __future__ import annotations

import argparse
import json
import math
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from inference import classify_image_bytes


KANDY_LATITUDE = 7.2906
KANDY_LONGITUDE = 80.6337
SEARCH_RADIUS_METERS = 3_000
OVERPASS_URLS = (
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
USER_AGENT = "TourUni-MoodPlaceFinder/1.0 (university MVP)"

# These profiles are intentionally simple and deterministic. They recommend
# environments that may support comfort; they do not diagnose or treat moods.
MOOD_PROFILES: dict[str, dict[str, Any]] = {
    "anger": {
        "preferred": [
            "park",
            "garden",
            "nature_reserve",
            "viewpoint",
            "waterfall",
            "attraction",
        ],
        "intro": "A quieter outdoor setting may help you cool down and reset.",
    },
    "sad": {
        "preferred": [
            "garden",
            "park",
            "viewpoint",
            "waterfall",
            "cafe",
            "museum",
            "attraction",
        ],
        "intro": "A gentle, pleasant place may offer a small change of pace.",
    },
    "neutral": {
        "preferred": ["museum", "attraction", "historic", "garden", "viewpoint", "cafe"],
        "intro": "A light nearby activity could add some interest to your day.",
    },
    "happy": {
        "preferred": ["attraction", "viewpoint", "museum", "historic", "garden", "park"],
        "intro": "You seem upbeat, so these places can help you use that energy well.",
    },
    "surprise": {
        "preferred": [
            "park",
            "garden",
            "museum",
            "cafe",
            "viewpoint",
            "historic",
            "attraction",
        ],
        "intro": "A grounded but interesting stop may help you settle into the moment.",
    },
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
}


def build_overpass_query(emotion: str, radius_meters: int) -> str:
    """Build a compact query containing only categories useful for this mood."""
    radius_km = radius_meters / 1000
    latitude_delta = radius_km / 111.32
    longitude_delta = radius_km / (
        111.32 * math.cos(math.radians(KANDY_LATITUDE))
    )
    bbox = ",".join(
        f"{value:.6f}"
        for value in (
            KANDY_LATITUDE - latitude_delta,
            KANDY_LONGITUDE - longitude_delta,
            KANDY_LATITUDE + latitude_delta,
            KANDY_LONGITUDE + longitude_delta,
        )
    )
    preferred = set(MOOD_PROFILES.get(emotion, MOOD_PROFILES["neutral"])["preferred"])
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
    # Historic=* is intentionally avoided because it creates very expensive
    # city-wide queries. Named tourism attractions cover useful cultural stops.
    return "[out:json][timeout:25];(" + ";".join(selectors) + ";);out center tags 100;"


def fetch_overpass_places(
    emotion: str, radius_meters: int = SEARCH_RADIUS_METERS
) -> list[dict[str, Any]]:
    payload = urllib.parse.urlencode(
        {"data": build_overpass_query(emotion, radius_meters)}
    ).encode()
    errors: list[str] = []

    for endpoint in OVERPASS_URLS:
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                data = json.load(response)
            elements = data.get("elements", [])
            if elements:
                return elements
            errors.append(f"{endpoint}: returned no places")
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            socket.timeout,
            json.JSONDecodeError,
        ) as error:
            errors.append(f"{endpoint}: {error}")

    raise RuntimeError("All Overpass servers failed. " + " | ".join(errors))


def element_coordinates(element: dict[str, Any]) -> tuple[float, float] | None:
    latitude = element.get("lat")
    longitude = element.get("lon")
    if latitude is None or longitude is None:
        center = element.get("center") or {}
        latitude = center.get("lat")
        longitude = center.get("lon")
    if latitude is None or longitude is None:
        return None
    return float(latitude), float(longitude)


def haversine_km(latitude: float, longitude: float) -> float:
    earth_radius_km = 6371.0088
    lat1 = math.radians(KANDY_LATITUDE)
    lat2 = math.radians(latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(longitude - KANDY_LONGITUDE)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return earth_radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def place_category(tags: dict[str, str]) -> str | None:
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
    if natural == "peak":
        return "viewpoint"
    if amenity == "cafe":
        return "cafe"
    if "historic" in tags:
        return "historic"
    return None


def rank_places(
    elements: list[dict[str, Any]], emotion: str, limit: int = 5
) -> list[dict[str, Any]]:
    profile = MOOD_PROFILES.get(emotion, MOOD_PROFILES["neutral"])
    preference_order = profile["preferred"]
    ranked: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for element in elements:
        tags = element.get("tags") or {}
        name = str(tags.get("name", "")).strip()
        coordinates = element_coordinates(element)
        category = place_category(tags)
        osm_key = (str(element.get("type", "")), int(element.get("id", 0)))
        if not name or not coordinates or not category or osm_key in seen:
            continue
        seen.add(osm_key)

        latitude, longitude = coordinates
        distance_km = haversine_km(latitude, longitude)
        try:
            preference_rank = preference_order.index(category)
        except ValueError:
            preference_rank = len(preference_order)

        # Mood fit dominates, while distance breaks ties within a category.
        score = (100 - preference_rank * 12) - min(distance_km, 20) * 2
        ranked.append(
            {
                "name": name,
                "category": category.replace("_", " ").title(),
                "distance_km": round(distance_km, 1),
                "reason": CATEGORY_REASONS[category],
                "map_url": f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=16/{latitude}/{longitude}",
                "score": score,
            }
        )

    ranked.sort(key=lambda place: (-place["score"], place["distance_km"], place["name"]))
    return ranked[:limit]


def print_result(prediction: dict[str, Any], places: list[dict[str, Any]]) -> None:
    emotion = prediction["emotion_label"]
    confidence = prediction["emotion_confidence"] * 100
    profile = MOOD_PROFILES.get(emotion, MOOD_PROFILES["neutral"])

    print("\nMood result")
    print("-----------")
    print(f"Detected: {emotion.title()} ({confidence:.1f}% confidence)")
    print(profile["intro"])
    print("This is a wellbeing suggestion, not a mental-health diagnosis or treatment.\n")

    print("Nearby suggestions around Kandy")
    print("-------------------------------")
    if not places:
        print("No suitable named places were found within the search radius.")
        return

    for index, place in enumerate(places, start=1):
        print(f"{index}. {place['name']} ({place['category']}, {place['distance_km']:.1f} km)")
        print(f"   Why: {place['reason']}.")
        print(f"   Map: {place['map_url']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify an emotion locally and find supportive places near Kandy."
    )
    parser.add_argument("image", nargs="?", help="Path to a JPG, PNG, or WEBP face image")
    parser.add_argument("--limit", type=int, default=5, choices=range(1, 11))
    parser.add_argument("--radius", type=int, default=SEARCH_RADIUS_METERS, help="Search radius in metres")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image_value = args.image or input("Photo path: ").strip().strip("'\"")
    image_path = Path(image_value).expanduser().resolve()
    if not image_path.is_file():
        print(f"Image not found: {image_path}", file=sys.stderr)
        return 2

    try:
        prediction = classify_image_bytes(image_path.read_bytes())
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(
        f"Detected locally: {prediction['emotion_label'].title()} "
        f"({prediction['emotion_confidence'] * 100:.1f}% confidence)"
    )
    print("Searching OpenStreetMap places near Kandy...")

    try:
        elements = fetch_overpass_places(
            prediction["emotion_label"], radius_meters=args.radius
        )
        places = rank_places(elements, prediction["emotion_label"], limit=args.limit)
    except (RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        print("Your photo was classified successfully, but nearby places are temporarily unavailable.")
        return 1

    print_result(prediction, places)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
