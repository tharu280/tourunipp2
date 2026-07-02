from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from clean_run.integrations.google_places_client import search_nearby_places, search_text_places
from clean_run.routes.polyline import haversine_meters, summarize_geometry
from clean_run.routes.segments import build_day_segments, recommend_segment_query_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich saved Google routes with segmented Google Places candidates."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the saved route JSON created by google_routes.fetch_routes.",
    )
    parser.add_argument(
        "--trip-days",
        type=int,
        required=True,
        help="Trip duration in whole days for segmenting each route.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Defaults to outputs/enriched-routes-<timestamp>.json",
    )
    parser.add_argument(
        "--strategy",
        choices=["nearby", "text"],
        default="nearby",
        help="Place retrieval strategy. Defaults to nearby.",
    )
    parser.add_argument(
        "--lodging-budget-lkr",
        type=float,
        default=None,
        help="Optional nightly accommodation budget in LKR used only for lodging ranking.",
    )
    return parser.parse_args()


def parse_duration_seconds(duration_value: str | None) -> int | None:
    if not duration_value:
        return None
    if not duration_value.endswith("s"):
        return None
    try:
        return int(float(duration_value[:-1]))
    except ValueError:
        return None


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("outputs") / f"enriched-routes-{timestamp}.json"


def _dataset_path(filename: str) -> Path:
    clean_run_path = Path(__file__).resolve().parents[1] / "data" / filename
    if clean_run_path.exists():
        return clean_run_path
    return Path("data") / filename


@lru_cache(maxsize=1)
def load_curated_attractions() -> list[dict[str, Any]]:
    dataset_path = _dataset_path("sri_lanka_attractions.json")
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    attractions: list[dict[str, Any]] = []
    for district in payload.get("districts", []):
        attractions.extend(district.get("attractions", []))
    return attractions


@lru_cache(maxsize=1)
def load_curated_accommodations() -> list[dict[str, Any]]:
    dataset_path = _dataset_path("sri_lanka_accommodations.json")
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if isinstance(payload.get("accommodations"), list):
        return payload["accommodations"]

    accommodations: list[dict[str, Any]] = []
    for district in payload.get("districts", []):
        accommodations.extend(district.get("accommodations", []))
    return accommodations


def route_min_distance_m(
    *,
    path_points: list[dict[str, float]],
    attraction: dict[str, Any],
) -> float:
    return min(
        haversine_meters(
            point,
            {"lat": float(attraction["latitude"]), "lng": float(attraction["longitude"])},
        )
        for point in path_points
    )


def group_attractions_by_district(
    attractions: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for attraction in attractions:
        district = attraction.get("district")
        if not district:
            continue
        grouped.setdefault(district, []).append(attraction)
    return grouped


def normalize_place(
    *,
    place: dict[str, Any],
    category: str,
    anchor_point: dict[str, float],
) -> dict[str, Any]:
    location = place.get("location", {})
    place_lat = location.get("latitude")
    place_lng = location.get("longitude")
    distance_from_anchor_m = None

    if place_lat is not None and place_lng is not None:
        distance_from_anchor_m = round(
            haversine_meters(
                anchor_point,
                {"lat": float(place_lat), "lng": float(place_lng)},
            ),
            2,
        )

    return {
        "place_id": place.get("id"),
        "category": category,
        "display_name": place.get("displayName", {}).get("text"),
        "formatted_address": place.get("formattedAddress"),
        "location": {
            "lat": place_lat,
            "lng": place_lng,
        },
        "google_maps_uri": place.get("googleMapsUri"),
        "primary_type": place.get("primaryType"),
        "types": place.get("types", []),
        "rating": place.get("rating"),
        "user_rating_count": place.get("userRatingCount"),
        "distance_from_anchor_m": distance_from_anchor_m,
    }


def is_weak_attraction(place: dict[str, Any]) -> bool:
    name = (place.get("display_name") or "").strip().lower()
    primary_type = (place.get("primary_type") or "").strip().lower()
    user_rating_count = int(place.get("user_rating_count") or 0)

    if not name:
        return True

    weak_name_patterns = [
        r"\bjunction\b",
        r"\bclock tower\b",
        r"\bcar park\b",
        r"\bparking\b",
        r"\bturnout\b",
        r"\btravel(s)?\b",
        r"\btravels\b",
        r"\btours?\b",
        r"\btuktuk\b",
        r"\bhotel\b",
        r"\bresort\b",
        r"\breception hall\b",
        r"\bswimming pool\b",
        r"\bwalk way\b",
        r"\bjogging track\b",
    ]
    if any(re.search(pattern, name) for pattern in weak_name_patterns):
        return True

    weak_primary_types = {
        "lodging",
        "restaurant",
        "park",
        "parking",
    }
    if primary_type in weak_primary_types and user_rating_count < 25:
        return True

    return False


def normalize_curated_attraction(
    *,
    attraction: dict[str, Any],
    segment: dict[str, Any],
) -> dict[str, Any]:
    path_points = segment.get("segment_path_points") or [segment["mid_point"]]
    min_distance_m = min(
        haversine_meters(
            point,
            {"lat": float(attraction["latitude"]), "lng": float(attraction["longitude"])},
        )
        for point in path_points
    )

    return {
        "place_id": attraction.get("id"),
        "category": "attractions",
        "display_name": attraction.get("name"),
        "formatted_address": f'{attraction.get("district")}, {attraction.get("province")}',
        "location": {
            "lat": attraction.get("latitude"),
            "lng": attraction.get("longitude"),
        },
        "google_maps_uri": None,
        "primary_type": (attraction.get("categories") or [None])[0],
        "types": attraction.get("categories", []),
        "rating": attraction.get("importance_score"),
        "user_rating_count": None,
        "distance_from_anchor_m": round(min_distance_m, 2),
        "distance_from_route_m": round(min_distance_m, 2),
        "tier": attraction.get("tier"),
        "importance_score": attraction.get("importance_score"),
        "tags": attraction.get("tags", []),
        "summary": attraction.get("summary"),
        "district": attraction.get("district"),
        "province": attraction.get("province"),
        "estimated_visit_hours": attraction.get("estimated_visit_hours"),
        "source_urls": attraction.get("source_urls", []),
    }


def normalize_curated_accommodation(
    *,
    accommodation: dict[str, Any],
    segment: dict[str, Any],
) -> dict[str, Any]:
    end_point = segment["end_point"]
    distance_m = haversine_meters(
        end_point,
        {"lat": float(accommodation["latitude"]), "lng": float(accommodation["longitude"])},
    )
    return {
        "place_id": accommodation.get("id") or f"acc_{accommodation.get('name')}",
        "category": "lodging",
        "display_name": accommodation.get("name"),
        "formatted_address": accommodation.get("district"),
        "location": {
            "lat": accommodation.get("latitude"),
            "lng": accommodation.get("longitude"),
        },
        "estimated_nightly_cost_lkr": accommodation.get("estimated_nightly_cost_lkr"),
        "district": accommodation.get("district"),
        "distance_from_anchor_m": round(distance_m, 2),
        "distance_from_route_m": round(distance_m, 2),
    }


def build_route_attraction_pool(
    *,
    geometry_points: list[dict[str, float]],
    trip_days: int,
) -> dict[str, Any]:
    all_attractions = load_curated_attractions()
    grouped = group_attractions_by_district(all_attractions)

    route_district_limit_m = max(20_000, min(60_000, trip_days * 12_000))
    route_attraction_limit_m = min(route_district_limit_m, 35_000)
    district_min_distances: dict[str, float] = {}
    for district, attractions in grouped.items():
        district_min_distances[district] = min(
            route_min_distance_m(path_points=geometry_points, attraction=attraction)
            for attraction in attractions
        )

    included_districts = {
        district
        for district, distance in district_min_distances.items()
        if distance <= route_district_limit_m
    }
    if not included_districts:
        included_districts = {
            district
            for district, _distance in sorted(
                district_min_distances.items(),
                key=lambda item: item[1],
            )[:3]
        }

    pooled_attractions = [
        {
            **attraction,
            "distance_from_full_route_m": round(
                route_min_distance_m(
                    path_points=geometry_points,
                    attraction=attraction,
                ),
                2,
            ),
        }
        for attraction in all_attractions
        if attraction.get("district") in included_districts
    ]
    pooled_attractions = [
        attraction
        for attraction in pooled_attractions
        if float(attraction.get("distance_from_full_route_m") or 99_999)
        <= route_attraction_limit_m
    ]

    return {
        "included_districts": sorted(included_districts),
        "route_district_limit_m": route_district_limit_m,
        "route_attraction_limit_m": route_attraction_limit_m,
        "attractions": pooled_attractions,
    }


def assign_attractions_to_segments(
    *,
    route_attraction_pool: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    assignments: dict[int, list[dict[str, Any]]] = {
        segment["day"]: [] for segment in segments
    }

    for attraction in route_attraction_pool:
        best_match: dict[str, Any] | None = None
        best_distance = float("inf")

        for segment in segments:
            normalized = normalize_curated_attraction(
                attraction=attraction,
                segment=segment,
            )
            distance = float(normalized.get("distance_from_route_m") or 99_999)
            if distance < best_distance:
                best_distance = distance
                best_match = {
                    **normalized,
                    "assigned_day": segment["day"],
                }

        if best_match is not None:
            assignments[best_match["assigned_day"]].append(best_match)

    return assignments


def fetch_curated_attractions_for_segment(
    *,
    assigned_attractions: list[dict[str, Any]],
    query_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    corridor_limit_m = max(int(query_plan["attractions"]["radius_m"]), 8_000)
    expanded_limit_m = min(max(corridor_limit_m * 2, 18_000), 40_000)
    hard_cap_m = 45_000

    nearby = [
        attraction
        for attraction in assigned_attractions
        if float(attraction.get("distance_from_route_m") or 99_999) <= corridor_limit_m
    ]
    if len(nearby) < query_plan["attractions"]["max_results"]:
        nearby = [
            attraction
            for attraction in assigned_attractions
            if float(attraction.get("distance_from_route_m") or 99_999) <= expanded_limit_m
        ]

    if len(nearby) < query_plan["attractions"]["max_results"]:
        top_up = [
            attraction
            for attraction in sorted(
                assigned_attractions,
                key=lambda item: float(item.get("distance_from_route_m") or 99_999),
            )
            if float(attraction.get("distance_from_route_m") or 99_999) <= hard_cap_m
        ]
        seen = {item.get("place_id") for item in nearby}
        for attraction in top_up:
            if attraction.get("place_id") not in seen:
                nearby.append(attraction)
                seen.add(attraction.get("place_id"))
            if len(nearby) >= query_plan["attractions"]["max_results"]:
                break

    return nearby


def fetch_curated_lodging_for_segment(
    *,
    segment: dict[str, Any],
    query_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    if not segment.get("is_overnight_stop"):
        return []

    radius_m = max(int(query_plan["lodging"]["radius_m"]), 15_000)
    expanded_limit_m = min(max(radius_m * 2, 30_000), 60_000)
    normalized = [
        normalize_curated_accommodation(accommodation=item, segment=segment)
        for item in load_curated_accommodations()
    ]

    nearby = [
        item
        for item in normalized
        if float(item.get("distance_from_anchor_m") or 99_999) <= radius_m
    ]
    if len(nearby) < query_plan["lodging"]["max_results"]:
        nearby = [
            item
            for item in normalized
            if float(item.get("distance_from_anchor_m") or 99_999) <= expanded_limit_m
        ]
    nearby.sort(key=lambda item: float(item.get("distance_from_anchor_m") or 99_999))
    return nearby[: max(query_plan["lodging"]["max_results"], 3)]


def planning_geometry_for_route(
    route: dict[str, Any],
    geometry: dict[str, Any],
) -> tuple[list[dict[str, float]], list[float], float, dict[str, Any]]:
    origin = route.get("origin_point") or {}
    destination = route.get("destination_point") or {}
    route_distance_m = float(route.get("distance_meters") or geometry.get("total_geometry_distance_m") or 0.0)
    try:
        straight_distance_m = haversine_meters(origin, destination)
    except (KeyError, TypeError, ValueError):
        straight_distance_m = 0.0

    is_excessive_detour = (
        straight_distance_m > 0
        and route_distance_m > 0
        and route_distance_m / straight_distance_m > 2.05
        and route_distance_m - straight_distance_m > 85_000
    )
    if is_excessive_detour and origin.get("lat") and origin.get("lng") and destination.get("lat") and destination.get("lng"):
        return (
            [{"lat": origin["lat"], "lng": origin["lng"]}, {"lat": destination["lat"], "lng": destination["lng"]}],
            [0.0, straight_distance_m],
            straight_distance_m,
            {
                "used_direct_planning_corridor": True,
                "reason": "Google returned an excessive highway detour, so attractions and stays were selected along the direct trip corridor.",
                "route_distance_m": round(route_distance_m, 2),
                "straight_line_distance_m": round(straight_distance_m, 2),
            },
        )

    return (
        geometry["decoded_points"],
        geometry["cumulative_distances_m"],
        float(route.get("distance_meters") or geometry["total_geometry_distance_m"]),
        {"used_direct_planning_corridor": False},
    )


def score_place(place: dict[str, Any], *, segment: dict[str, Any]) -> float:
    category_weights = {
        "attractions": 30,
        "lodging": 25,
    }
    category = place.get("category", "attractions")
    base_weight = category_weights.get(category, 10)

    distance_m = float(place.get("distance_from_route_m") or place.get("distance_from_anchor_m") or 99_999)

    score = base_weight
    if category == "attractions":
        importance = float(place.get("importance_score") or place.get("rating") or 0.0)
        tier = place.get("tier")
        tier_weight = {
            "tier_1": 12,
            "tier_2": 6,
            "tier_3": 2,
        }.get(tier, 0)
        score += importance * 10
        score += tier_weight
        score -= min(distance_m / 1000 * 1.2, 18)
    else:
        rating = float(place.get("rating") or 0.0)
        user_ratings = int(place.get("user_rating_count") or 0)
        score += rating * 16
        score += min(math.log1p(user_ratings) * 8, 30)
        score -= min(distance_m / 1000 * 1.4, 14)
    return round(score, 2)


def score_lodging_place(
    place: dict[str, Any],
    *,
    lodging_budget_lkr: float | None,
) -> float:
    distance_m = float(place.get("distance_from_anchor_m") or place.get("distance_from_route_m") or 99_999)
    distance_km = distance_m / 1000
    distance_score = max(0.0, 24.0 - min(distance_km * 1.6, 24.0))

    if lodging_budget_lkr is None or lodging_budget_lkr <= 0:
        return round(distance_score, 2)

    nightly_cost = place.get("estimated_nightly_cost_lkr")
    if nightly_cost is None:
        return round(distance_score, 2)

    try:
        nightly_cost_value = float(nightly_cost)
    except (TypeError, ValueError):
        return round(distance_score, 2)

    budget_value = float(lodging_budget_lkr)
    cost_ratio = nightly_cost_value / budget_value
    if cost_ratio < 0.1:
        budget_score = -42.0
    elif cost_ratio < 0.2:
        budget_score = -30.0
    elif cost_ratio < 0.35:
        budget_score = -16.0
    elif cost_ratio < 0.55:
        budget_score = 4.0
    elif cost_ratio <= 0.8:
        budget_score = 22.0
    elif cost_ratio <= 1.0:
        budget_score = 34.0
    elif cost_ratio <= 1.15:
        budget_score = 14.0
    elif cost_ratio <= 1.3:
        budget_score = -2.0
    elif cost_ratio <= 1.5:
        budget_score = -20.0
    else:
        budget_score = -40.0

    cheap_floor_penalty = 0.0
    preferred_min_spend = min(40_000.0, max(10_000.0, budget_value * 0.25))
    if nightly_cost_value < preferred_min_spend:
        spend_gap_ratio = (preferred_min_spend - nightly_cost_value) / preferred_min_spend
        cheap_floor_penalty = spend_gap_ratio * 18.0

    return round(distance_score + budget_score - cheap_floor_penalty, 2)


def dedupe_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    anonymous_counter = 0

    for place in places:
        place_id = place.get("place_id") or (place.get("display_name") or "").strip().lower()
        if not place_id:
            anonymous_counter += 1
            place_id = f"anonymous_{anonymous_counter}"

        existing = deduped.get(place_id)
        if existing is None or float(place.get("score", 0)) > float(existing.get("score", 0)):
            deduped[place_id] = place

    return list(deduped.values())


def rank_places_for_segment(
    *,
    segment: dict[str, Any],
    fetched_places: dict[str, list[dict[str, Any]]],
    lodging_budget_lkr: float | None = None,
) -> dict[str, Any]:
    combined: list[dict[str, Any]] = []
    for category, places in fetched_places.items():
        for place in places:
            if category == "attractions":
                normalized = place
            elif place.get("display_name") and place.get("location"):
                normalized = place
            else:
                normalized = normalize_place(
                    place=place,
                    category=category,
                    anchor_point=segment["end_point"],
                )
            if category == "attractions" and is_weak_attraction(normalized):
                continue
            if category == "lodging":
                normalized["score"] = score_lodging_place(
                    normalized,
                    lodging_budget_lkr=lodging_budget_lkr,
                )
            else:
                normalized["score"] = score_place(normalized, segment=segment)
            combined.append(normalized)

    combined = dedupe_places(combined)
    combined.sort(key=lambda item: item.get("score", 0), reverse=True)

    top_attractions = [place for place in combined if place["category"] == "attractions"][:10]
    top_lodging = [place for place in combined if place["category"] == "lodging"][:3]

    return {
        "candidate_place_count": len(combined),
        "ranked_places": top_attractions + top_lodging,
        "top_attractions": top_attractions,
        "top_lodging": top_lodging,
        "recommended_lodging": top_lodging[0] if top_lodging else None,
    }


def fetch_places_for_segment(
    *,
    assigned_attractions: list[dict[str, Any]],
    segment: dict[str, Any],
    query_plan: dict[str, Any],
    strategy: str,
) -> dict[str, list[dict[str, Any]]]:
    attractions = fetch_curated_attractions_for_segment(
        assigned_attractions=assigned_attractions,
        query_plan=query_plan,
    )
    curated_lodging = fetch_curated_lodging_for_segment(
        segment=segment,
        query_plan=query_plan,
    )

    lodging: list[dict[str, Any]] = []
    if segment.get("is_overnight_stop") and not curated_lodging:
        try:
            if strategy == "nearby":
                lodging = search_nearby_places(
                    latitude=segment["end_point"]["lat"],
                    longitude=segment["end_point"]["lng"],
                    included_types=["lodging"],
                    radius_m=query_plan["lodging"]["radius_m"],
                    max_result_count=query_plan["lodging"]["max_results"],
                    rank_preference="POPULARITY",
                )
            else:
                lodging = search_text_places(
                    text_query="best hotels",
                    latitude=segment["end_point"]["lat"],
                    longitude=segment["end_point"]["lng"],
                    radius_m=query_plan["lodging"]["radius_m"],
                    max_result_count=query_plan["lodging"]["max_results"],
                    rank_preference="RELEVANCE",
                )
        except Exception:
            lodging = []

    return {
        "attractions": attractions,
        "lodging": curated_lodging + lodging,
    }


def segment_assignment_pool(
    *,
    segment_assignments: dict[int, list[dict[str, Any]]],
    day: int,
    trip_days: int,
) -> list[dict[str, Any]]:
    pooled = list(segment_assignments.get(day, []))
    if len(pooled) >= 5:
        return pooled

    for neighbor_day in (day - 1, day + 1):
        if 1 <= neighbor_day <= trip_days:
            pooled.extend(
                {
                    **item,
                    "neighbor_day_source": neighbor_day,
                }
                for item in segment_assignments.get(neighbor_day, [])
            )
        if len(pooled) >= 12:
            break
    return pooled


def enrich_route(
    route: dict[str, Any],
    *,
    trip_days: int,
    strategy: str,
    lodging_budget_lkr: float | None = None,
) -> dict[str, Any]:
    geometry = summarize_geometry(route["polyline"])
    planning_points, planning_distances, total_route_distance_m, planning_metadata = planning_geometry_for_route(
        route,
        geometry,
    )
    total_route_duration_seconds = parse_duration_seconds(route.get("duration"))
    route_pool_info = build_route_attraction_pool(
        geometry_points=planning_points,
        trip_days=trip_days,
    )

    segments = build_day_segments(
        decoded_points=planning_points,
        cumulative_distances_m=planning_distances,
        total_route_distance_m=total_route_distance_m,
        total_route_duration_seconds=total_route_duration_seconds,
        trip_days=trip_days,
    )
    segment_assignments = assign_attractions_to_segments(
        route_attraction_pool=route_pool_info["attractions"],
        segments=segments,
    )

    enriched_segments = []
    for segment in segments:
        query_plan = recommend_segment_query_plan(segment)
        assigned_pool = segment_assignment_pool(
            segment_assignments=segment_assignments,
            day=segment["day"],
            trip_days=trip_days,
        )
        fetched_places = fetch_places_for_segment(
            assigned_attractions=assigned_pool,
            segment=segment,
            query_plan=query_plan,
            strategy=strategy,
        )
        ranked = rank_places_for_segment(
            segment=segment,
            fetched_places=fetched_places,
            lodging_budget_lkr=lodging_budget_lkr,
        )
        enriched_segments.append(
            {
                **segment,
                "place_strategy": strategy,
                "query_plan": query_plan,
                "assigned_route_attraction_count": len(
                    segment_assignments.get(segment["day"], [])
                ),
                "assignment_pool_count": len(assigned_pool),
                "fetched_place_counts": {
                    category: len(places) for category, places in fetched_places.items()
                },
                **ranked,
            }
        )

    return {
        **route,
        "geometry_summary": {
            "point_count": geometry["point_count"],
            "total_geometry_distance_m": geometry["total_geometry_distance_m"],
            "sampled_points": geometry["sampled_points"],
            "planning_corridor": planning_metadata,
        },
        "trip_days": trip_days,
        "place_strategy": strategy,
        "route_attraction_pool_size": len(route_pool_info["attractions"]),
        "route_attraction_pool_districts": route_pool_info["included_districts"],
        "segments": enriched_segments,
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))

    enriched_routes = [
        enrich_route(
            route,
            trip_days=args.trip_days,
            strategy=args.strategy,
            lodging_budget_lkr=args.lodging_budget_lkr,
        )
        for route in data.get("routes", [])
    ]

    output = {
        **data,
        "trip_days": args.trip_days,
        "place_strategy": args.strategy,
        "lodging_budget_lkr": args.lodging_budget_lkr,
        "enriched_at_utc": datetime.now(timezone.utc).isoformat(),
        "routes": enriched_routes,
    }

    output_path = Path(args.output) if args.output else default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved enriched routes to {output_path}")


if __name__ == "__main__":
    main()
